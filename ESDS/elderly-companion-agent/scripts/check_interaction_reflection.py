"""Three bounded, fictional DeepSeek reflection checks; no production records."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


def main():
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    load_dotenv(project / ".env", encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"] = "deepseek"
    if "--persistence-only" in sys.argv:
        return persistence_check(project)
    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform.interaction import validate
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
    cases = [("feedback", "以后每节课都别一直追问我为什么，真的很烦"),
             ("not_feedback", "我没有嫌你一直追问，你现在的讲法挺合适的"),
             ("not_feedback", "今天推销员一直追问我为什么不买，我觉得很烦")]
    output = {"provider": "deepseek", "fictional_input": True, "cases": []}
    for index, (expected, text) in enumerate(cases):
        agent = FreeformCourseAgent()
        state = new_course_state("lesson-1", reflection_policy="none")
        state["stage"] = "practice"
        state["draft_record"] = {"situation": {"value": "今天下雨", "source_message_id": "fictional-story"}}
        latest = {"id": f"fictional-feedback-{index}", "role": "learner", "content": text}
        history = [{"id": "fictional-guide", "role": "agent", "content": "您当时脑中想到什么？为什么这样想？"}, latest]
        row = {"expected": expected}
        result = None
        try:
            result = agent.reflect_interaction(history, context=FreeformCourseRuntime(agent=agent)._context(state))
            note = validate(result.decision, latest)
            row.update(verdict=note["verdict"], passed=note["verdict"] == expected, scope=note["scope"],
                       reply=note["reply"], usage=result.completion.usage, model=result.completion.model,
                       latency_ms=agent.call_log[-1]["latency_ms"])
        except Exception as exc:
            row.update(passed=False, error_type=type(exc).__name__)
            if type(exc) is ValueError:
                row["validation_reason"] = str(exc)
            if result is not None:
                row["synthetic_output"] = result.decision.model_dump()
        output["cases"].append(row)
        print(json.dumps(row, ensure_ascii=True), flush=True)
    output["passed"] = all(row["passed"] for row in output["cases"])
    target = project / "test-results" / "interaction-reflection-smoke.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if output["passed"] else 1


def persistence_check(project):
    import tempfile
    import uuid
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn
    from cbt_course_llm_freeform.interaction_memory import load_memories
    from webapp.database import Base
    from webapp.models import InteractionReflectionMemory, Participant, TurnEvent
    from webapp.security import decrypt_json, encrypt_json, hash_secret
    output = {"fictional_input": True, "temporary_database": True, "passed": False}
    with tempfile.TemporaryDirectory(prefix="real-interaction-memory-") as directory:
        engine = create_engine("sqlite:///" + (Path(directory) / "memory.db").as_posix())
        try:
            Base.metadata.create_all(engine)
            with sessionmaker(bind=engine, expire_on_commit=False)() as db:
                person = Participant(label="fictional-reflection-check", invite_hash=hash_secret(uuid.uuid4().hex))
                db.add(person); db.commit()
                first = create_or_resume_course(db, participant_id=person.id, lesson_id="lesson-1")[0]
                state = decrypt_json(first.agent_state_encrypted)
                state["stage"] = "practice"
                first.agent_state_encrypted = encrypt_json(state); db.commit()
                text = "以后每节课都别一直追问我为什么，真的很烦"
                key = uuid.uuid4().hex
                result = process_course_turn(db, first, content=text, idempotency_key=key)
                row = db.scalar(select(InteractionReflectionMemory))
                if row is None:
                    raise AssertionError("No accepted memory")
                event = db.get(TurnEvent, row.turn_event_id)
                replay = process_course_turn(db, first, content=text, idempotency_key=key)
                second = create_or_resume_course(db, participant_id=person.id, lesson_id="lesson-2")[0]
                loaded = load_memories(db, second)
                assert replay["deduplicated"] and len(db.scalars(select(InteractionReflectionMemory)).all()) == 1
                assert loaded and loaded[0]["id"] == row.id
                assert text not in row.payload_encrypted
                assert decrypt_json(first.agent_state_encrypted)["draft_record"] == {}
                output.update(passed=True, model=event.model, usage={"total_tokens": event.total_tokens},
                    reply=result["reply"], encrypted_memory=True, deduplicated=True, next_lesson_memory=True,
                    model_call_count=len(decrypt_json(event.trace_encrypted)["model_calls"]))
        except Exception as exc:
            output["error_type"] = type(exc).__name__
        finally:
            engine.dispose()
    target = project / "test-results" / "interaction-memory-integration.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True))
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
