"""Run eight fictional lessons offline and export a trace for reading the code."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import uuid


def main():
    parser = argparse.ArgumentParser(description="隔离运行八课，导出真实状态机轨迹；不调用外部模型")
    parser.add_argument("--policy", choices=("none", "per_turn", "per_task_step", "event_driven"), default="event_driven")
    parser.add_argument("--output", help="输出JSON路径，默认test-results/course-workflow-策略.json")
    parser.add_argument("--activity-path", choices=("activation", "exposure"), default="activation")
    parser.add_argument("--wellbeing-path", choices=("sleep", "relaxation"), default="sleep")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    with tempfile.TemporaryDirectory(prefix="course-code-trace-") as directory:
        os.environ.update({"APP_ENV": "development", "DATABASE_URL": "sqlite:///" + (Path(directory) / "trace.db").as_posix(),
            "APP_SECRET": secrets.token_urlsafe(48), "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "INVITE_CODES": "trace:trace", "ADMIN_PASSWORD": secrets.token_urlsafe(32), "COOKIE_SECURE": "false",
            "VOICE_BRIDGE_ENABLED": "false", "VERCEL": "false", "CBT_REFLECTION_POLICY": args.policy,
            "DASHSCOPE_API_KEY": "", "AZURE_OPENAI_API_KEY": "", "AZURE_OPENAI_ENDPOINT": "", "AZURE_OPENAI_DEPLOYMENT": ""})
        from sqlalchemy import select
        from cbt_course_llm_freeform.agent import FreeformCourseAgent
        from cbt_course_llm_freeform.design import PATHS, preview_examples
        from cbt_course_llm_freeform.preview import PreviewClient
        from cbt_course_llm_freeform.prompt import prompt_for_lesson
        from cbt_course_llm_freeform.reflection import generate_course_reflection
        from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, can_reuse_case
        from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn
        from webapp.database import Base, engine, SessionLocal
        from webapp.models import Participant, TurnEvent
        from webapp.security import decrypt_json, hash_secret

        Base.metadata.create_all(engine)
        client = PreviewClient()
        report = {"mode": "offline-rule-demonstration", "policy": args.policy, "activity_path": args.activity_path, "wellbeing_path": args.wellbeing_path,
                  "limitation": "固定虚构回答和规则客户端，仅用于代码流程演示，不是模型质量或策略效果实验。", "turns": [], "artifacts": []}
        try:
            with SessionLocal() as db:
                person = Participant(label="fictional-code-walkthrough", invite_hash=hash_secret("offline-trace"))
                db.add(person); db.commit()

                def turn(conversation, text="", action="chat"):
                    key = uuid.uuid4().hex
                    response = process_course_turn(db, conversation, content=text, action=action, idempotency_key=key,
                        expected_revision=decrypt_json(conversation.agent_state_encrypted)["revision"],
                        runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=client, system_prompt=prompt_for_lesson(conversation.lesson_id))))
                    event = db.scalar(select(TurnEvent).where(TurnEvent.conversation_id == conversation.id, TurnEvent.idempotency_key == key))
                    trace = decrypt_json(event.trace_encrypted)
                    item = {"lesson_id": conversation.lesson_id, "path": response["course"].get("path"), "action": action, "input": text,
                            "reply": response["reply"], "stage_from": trace["stage_from"], "stage_to": trace["stage_to"],
                            "task_step_id": trace["task_step_id"], "observations": trace.get("observations", []),
                            "trigger": trace.get("trigger", response["course"]["workflow"]["last_trigger"]),
                            "model_calls": trace["model_calls"], "guidance_reflection": trace.get("guidance_reflection"),
                            "record": response["course"]["record"],
                            "revision": response["course"]["revision"]}
                    report["turns"].append(item)
                    print(f'{conversation.lesson_id} | {action:18} | {trace["stage_from"]:9} -> {trace["stage_to"]:9} | calls={len(trace["model_calls"])} | trigger={item["trigger"]["reason_codes"]}')
                    return response

                for lesson in (f"lesson-{number}" for number in range(1, 9)):
                    conversation, _ = create_or_resume_course(db, participant_id=person.id, lesson_id=lesson)
                    state = decrypt_json(conversation.agent_state_encrypted)
                    if state["carryover"]["status"] == "offered":
                        turn(conversation, action="accept_carryover")
                    turn(conversation, action="skip_checkin")
                    if lesson in PATHS:
                        selected = args.activity_path if lesson == "lesson-5" else args.wellbeing_path
                        turn(conversation, action=PATHS[lesson][selected]["action"])
                    if lesson == "lesson-1":
                        turn(conversation, "刚才这段没听懂，可以换个说法吗？")
                    state = decrypt_json(conversation.agent_state_encrypted)
                    turn(conversation, preview_examples(state)["learn"])
                    state = decrypt_json(conversation.agent_state_encrypted)
                    if can_reuse_case(state):
                        turn(conversation, action="reuse_case")
                    for _ in range(8):
                        state = decrypt_json(conversation.agent_state_encrypted)
                        if state["stage"] != "practice":
                            break
                        sample = preview_examples(state)["practice"]
                        if lesson == "lesson-1":
                            sample = sample.replace("她是不是", "她肯定")
                        turn(conversation, sample)
                    if decrypt_json(conversation.agent_state_encrypted)["stage"] != "review":
                        raise RuntimeError("固定示例未能到达核对阶段：" + lesson)
                    if lesson == "lesson-3":
                        turn(conversation, action="unsure_pattern")
                    turn(conversation, action="confirm_record")
                    if lesson == "lesson-1":
                        for answer in ("邻居向他问好", "他怕对方觉得自己没礼貌", "紧张", "低下头，没有回话"):
                            turn(conversation, answer)
                        turn(conversation, action="continue_after_check")
                        turn(conversation, "我希望先分清事情和自己的猜测。")
                        turn(conversation, action="confirm_learning_goal")
                    turn(conversation, action="decline_practice")
                    turn(conversation, "例子帮助我梳理了自己的说法，后面想继续慢慢练习。")
                    turn(conversation, action="finish")
                    generate_course_reflection(conversation.id, session_factory=SessionLocal, client=client)
                    db.refresh(conversation)
                    final = decrypt_json(conversation.agent_state_encrypted)
                    report["artifacts"].append({**final["artifact"], "post_lesson_reflection_status": final["reflection"]["status"]})
            destination = Path(args.output).resolve() if args.output else project / "test-results" / f"course-workflow-{args.policy}.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n八课完成；轨迹：{destination}")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
