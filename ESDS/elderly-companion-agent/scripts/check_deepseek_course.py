"""Two explicitly requested real-model smoke calls, using only fictional course input."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv


def main():
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    load_dotenv(project / ".env", encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"] = "deepseek"
    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
    from cbt_course_llm_freeform.prompt import prompt_for_lesson

    output = {"provider": "deepseek", "fictional_input": True, "status": "not_started"}
    started, arrivals = time.perf_counter(), []
    try:
        agent = FreeformCourseAgent(system_prompt=prompt_for_lesson("lesson-1"), on_reply=lambda text: arrivals.append(time.perf_counter() - started))
        runtime = FreeformCourseRuntime(agent=agent)
        result = runtime.process(new_course_state("lesson-1", reflection_policy="none"), [{"id": "fictional-checkin", "role": "learner", "content": "6"}])
        output.update(status="stream_success", model=result.completion.model, finish_reason=result.completion.finish_reason,
            usage=result.completion.usage, reply_delta_count=len(arrivals),
            first_reply_ms=round(arrivals[0] * 1000) if arrivals else None,
            total_ms=round((time.perf_counter() - started) * 1000), current_stage=result.state["stage"],
            structured_record_validated=True)
        check = agent.evaluate_answer([{"id": "fictional-answer", "role": "learner", "content": "紧张"}], context={
            "story": "老陈看到邻居，有些紧张，低下头。", "question": "老陈是什么心情？", "field": "emotion", "expected": "紧张", "retry": False})
        if check.decision.source_message_id != "fictional-answer":
            raise RuntimeError("The judgment did not preserve the fictional source ID.")
        output.update(status="success", judgment=check.decision.verdict, judgment_usage=check.completion.usage)
    except Exception as exc:
        output.update(status="failed", error_type=type(exc).__name__, error=str(exc))
    path = project / "test-results" / "deepseek-course-smoke.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True))
    return 0 if output["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
