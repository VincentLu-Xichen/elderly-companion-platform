"""Only confirmed, owned, current-version lesson artifacts may cross lessons."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from cbt_course_llm_freeform.catalog import lesson_version
from cbt_course_llm_freeform.design import FIELD_LABELS, PREDECESSORS, required_fields
from cbt_course_llm_freeform.state import IMPLEMENTATION
from cbt_course_llm_freeform import practice_flow
from webapp.models import Conversation, Message
from webapp.security import decrypt_json, decrypt_text


def _summary(
    source: Conversation, participant_id: str, agent_version: str, target_lesson: str = "lesson-2"
) -> dict | None:
    if (
        source.participant_id != participant_id
        or source.lesson_id not in PREDECESSORS.get(target_lesson, ())
        or source.status != "completed"
        or source.agent_version != agent_version
        or source.lesson_version != lesson_version(source.lesson_id)
    ):
        return None
    state = decrypt_json(source.agent_state_encrypted)
    record = state.get("confirmed_record")
    if record and record.get("source_kind", "personal") != "personal":
        return None  # Fictional exercise answers are never imported as personal context.
    if state.get("implementation") != IMPLEMENTATION or not state.get("completed") or not record:
        return None
    if not practice_flow.confirmed_ready(state, record):
        return None
    # Goals are only supplementary. Missing/deleted goal evidence removes goals,
    # without inventing permission or making the confirmed case unreadable.
    goals = []
    goal = state.get("learning_goal", {})
    if goal.get("status") == "confirmed":
        session = object_session(source)
        ids = {item.get("source_message_id") for item in goal.get("items", [])} | {
            goal.get("confirmation_message_id")
        }
        messages = (
            {
                item.id: item
                for item in session.scalars(
                    select(Message).where(
                        Message.conversation_id == source.id,
                        Message.id.in_(ids),
                        Message.role == "learner",
                    )
                )
            }
            if session
            else {}
        )
        if goal.get("confirmation_message_id") in messages:
            goals = [
                {
                    "value": item["value"][:180],
                    "truncated": len(item["value"]) > 180,
                    "source_message_id": item["source_message_id"],
                    "confirmation_message_id": goal["confirmation_message_id"],
                }
                for item in goal.get("items", [])
                if item.get("source_message_id") in messages
                and item["value"]
                in decrypt_text(messages[item["source_message_id"]].content_encrypted)
            ]
    from cbt_course_llm_freeform.homework import entries

    diaries = (
        entries(source)[-3:]
        if target_lesson == "lesson-2" and source.lesson_id == "lesson-1"
        else []
    )
    return {
        "lesson_id": source.lesson_id,
        "lesson_version": source.lesson_version,
        "participation_scope": {
            "deferred_fields": record.get("deferred_fields", {}),
            "application_status": "not_measured",
        },
        "artifact_kind": (state.get("artifact") or {}).get("kind", "learning_record"),
        "application_status": (state.get("artifact") or {}).get(
            "application_status", "not_measured"
        ),
        "path": state.get("path"),
        "path_label": None,
        "artifact_id": (state.get("artifact") or {}).get(
            "artifact_id", f"{source.id}:record:{record.get('revision', 0)}"
        ),
        "record": record["fields"],
        "record_order": list(required_fields(state)),
        "deferred_fields": record.get("deferred_fields", {}),
        "practice_scope": record.get("practice_scope"),
        "record_labels": {key: FIELD_LABELS[key] for key in required_fields(state)},
        "practice_plan": state.get("practice_plan", {}),
        "learning_evidence": state.get("learning_evidence", []),
        "course_goals": goals,
        "homework_entries": diaries,
    }


def offer_previous_summary(
    db: Session, participant_id: str, agent_version: str, target_lesson: str = "lesson-2"
) -> dict:
    for predecessor in PREDECESSORS.get(target_lesson, ()):
        sources = db.scalars(
            select(Conversation)
            .where(
                Conversation.participant_id == participant_id,
                Conversation.lesson_id == predecessor,
                Conversation.status == "completed",
                Conversation.agent_version == agent_version,
            )
            .order_by(Conversation.ended_at.desc())
        ).all()
        for source in sources:
            summary = _summary(source, participant_id, agent_version, target_lesson)
            if summary:
                return {
                    "status": "offered",
                    "source_conversation_id": source.id,
                    "summary": summary,
                }
    return {"status": "unavailable"}


def refresh_carryover(db: Session, state: dict, participant_id: str, agent_version: str) -> None:
    memory = state.get("carryover", {})
    if memory.get("status") not in {"offered", "accepted"}:
        return
    source = db.scalar(
        select(Conversation)
        .where(Conversation.id == memory.get("source_conversation_id"))
        .execution_options(populate_existing=True)
    )
    summary = (
        _summary(source, participant_id, agent_version, state.get("lesson_id", ""))
        if source
        else None
    )
    if not summary:
        state["carryover"] = {"status": "unavailable"}
        state["workflow"]["active_reflection"] = None
        # An unconfirmed imported draft still depends on its source. A confirmed
        # record is a separate learner-attested snapshot and stays historical.
        if not state.get("confirmed_record"):
            removed = [
                key
                for key, item in state.get("draft_record", {}).items()
                if item.get("source_artifact_id")
            ]
            for key in removed:
                del state["draft_record"][key]
            if removed:
                from cbt_course_llm_freeform import lesson2_flow

                if lesson2_flow.enabled(state):
                    state["lesson2_flow"]["case_review"] = None
                    state["lesson2_flow"]["relationship"] = None
                    if state["lesson2_flow"]["step"] == "model":
                        lesson2_flow.go(state, "personal")
                state["workflow"]["active_reflection"] = None
                if state["stage"] == "review":
                    state["stage"] = "practice"
    else:
        memory["summary"] = summary
