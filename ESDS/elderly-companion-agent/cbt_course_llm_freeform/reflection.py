"""One independent, auditable post-lesson reflection. Never edits learner facts."""
from __future__ import annotations

import json
import hashlib
import time
import uuid
from datetime import timedelta

from sqlalchemy import select, update, or_

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.prompt import LEARNING_REFLECTION_PROMPT, REFLECTION_PROMPT
from cbt_course_llm_freeform import learning_check
from cbt_course_llm_freeform.schemas import ReflectionDecision, TurnResult
from cbt_course_llm_freeform.services import AGENT_VERSION, _completion_metadata, _model_history
from webapp.database import SessionLocal
from webapp.models import Conversation, InteractionReflectionMemory, TurnEvent, utcnow
from webapp.security import decrypt_json, encrypt_json, encrypt_text


def generate_course_reflection(conversation_id: str, *, session_factory=None, client=None) -> None:
    """Background task, also injectable for deterministic tests. Errors stay auditable."""
    with (session_factory or SessionLocal)() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None or conversation.agent_version != AGENT_VERSION or conversation.status != "completed":
            return
        state = decrypt_json(conversation.agent_state_encrypted)
        if state.get("reflection", {}).get("status") == "ready":
            return
        token = str(uuid.uuid4())
        acquired = db.execute(update(Conversation).where(
            Conversation.id == conversation_id,
            or_(Conversation.active_request_id.is_(None), Conversation.processing_started_at < utcnow() - timedelta(minutes=2)),
        ).values(active_request_id=token, processing_started_at=utcnow())).rowcount
        db.commit()
        if acquired != 1:
            return
        db.refresh(conversation)
        state = decrypt_json(conversation.agent_state_encrypted)
        if state.get("reflection", {}).get("status") == "ready":
            db.execute(update(Conversation).where(Conversation.id == conversation_id, Conversation.active_request_id == token).values(active_request_id=None, processing_started_at=None))
            db.commit()
            return
        attempt = int(state.get("reflection", {}).get("attempt", 0)) + 1
        state["reflection"] = {"status": "running", "attempt": attempt, "applied": False}
        conversation.agent_state_encrypted = encrypt_json(state)
        event = TurnEvent(conversation_id=conversation_id, idempotency_key=f"reflection:{attempt}", status="pending", agent_version=AGENT_VERSION, agent_prompt_hash=hashlib.sha256(REFLECTION_PROMPT.encode()).hexdigest())
        db.add(event)
        db.commit()
        started = time.perf_counter()
        try:
            history = _model_history(conversation)
            enhanced = learning_check.enabled(state)
            prompt = REFLECTION_PROMPT + ("\n" + LEARNING_REFLECTION_PROMPT + "\n本次 observations、suggestions、hypotheses 各最多一项。\n" + json.dumps(ReflectionDecision.model_json_schema(), ensure_ascii=False) if enhanced else "")
            prompt += "\npractice_source.kind=fictional时，练习回答只表示对虚构案例的辨认，不能描述成用户生活经历、用户思维习惯或实际计划。互动记忆status=pending表示尚未确认，不得声称是跨课长期偏好。"
            event.agent_prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
            references = set()
            interaction_rows = db.scalars(select(InteractionReflectionMemory).where(
                InteractionReflectionMemory.conversation_id == conversation_id,
                InteractionReflectionMemory.participant_id == conversation.participant_id,
            ).order_by(InteractionReflectionMemory.created_at.desc()).limit(3)).all()
            interaction_notes = [decrypt_json(row.payload_encrypted) for row in interaction_rows]
            for row in interaction_rows:
                references.add(row.source_message_id)
                position = next((i for i, item in enumerate(history) if item["id"] == row.source_message_id), None)
                if position is not None and position > 0:
                    references.add(history[position - 1]["id"])
            if enhanced:
                aligned = state.get("blueprint", {})
                references.update(item.get("source_message_id") for item in aligned.get("ratings", {}).values())
                if aligned.get("relationship"):
                    references.add(aligned["relationship"]["source_message_id"])
                references.update(item.get("source_message_id") for item in state.get("learning_goal", {}).get("items", []))
                if state.get("learning_goal", {}).get("confirmation_message_id"):
                    references.add(state["learning_goal"]["confirmation_message_id"])
                for check_attempt in (state["learning_check"], state["learning_check"]["retry"]):
                    references.update(item["source_message_id"] for item in check_attempt["answers"])
                references.update(item.get("source_message_id") for item in (state.get("confirmed_record") or {}).get("fields", {}).values())
                for item in (state.get("confirmed_record") or {}).get("deferred_fields", {}).values():
                    references.update(item.get("source_message_ids", []))
                interaction = state.get("practice_flow", {}).get("interaction_feedback") or {}
                references.update(source for source in (interaction.get("source_message_id"), (interaction.get("choice") or {}).get("source_message_id")) if source)
            recent_ids = {item["id"] for item in history[-40:]}
            selected = [item for item in history if item["id"] in recent_ids | references]
            data = {"history": selected, "learner_feedback": state.get("feedback"), "practice_choice": state["practice_plan"]["status"]}
            data["interaction_reflections"] = interaction_notes
            data["practice_source"] = state.get("practice_source", {"kind": "personal"})
            if data["practice_source"]["kind"] == "fictional":
                data["source_notice"] = "本课练习来自虚构案例。用户回答是辨认表现，不是其生活经历；不能形成用户心理或个人生活结论。"
            if enhanced:
                data.update(learning_result=state.get("learning_result"), learner_record=state.get("confirmed_record"), learning_goal=state.get("learning_goal"), blueprint=state.get("blueprint"))
            model_client = client or FreeformCourseAgent._client_from_env()
            completion = model_client.complete_with_metadata([
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ], temperature=1.0, max_completion_tokens=1200 if enhanced else 600, response_format={"type": "json_object"})
            if completion.finish_reason not in {"", "stop"}:
                raise ValueError("Reflection output is incomplete")
            decision = ReflectionDecision.model_validate_json(completion.text)
            sources = {item["id"] for item in selected}
            for note in decision.observations + decision.suggestions:
                if not set(note.source_message_ids).issubset(sources):
                    raise ValueError("Reflection contains an unknown message source")
                if any(label in note.text for label in ("诊断为", "人格障碍", "认知障碍", "理解能力差", "智力低", "不配合的", "抑郁症患者")):
                    raise ValueError("Reflection contains an unsupported personal label")
            learner_sources = {item["id"] for item in selected if item["role"] == "learner"}
            if not enhanced and decision.hypotheses:
                raise ValueError("This lesson does not support learning hypotheses")
            for hypothesis in decision.hypotheses:
                if not set(hypothesis.source_message_ids).issubset(sources) or not learner_sources.intersection(hypothesis.source_message_ids):
                    raise ValueError("Learning hypothesis lacks learner evidence")
                combined = " ".join([hypothesis.text, hypothesis.context, hypothesis.alternative_explanation, hypothesis.next_action, hypothesis.verification])
                if any(label in combined for label in ("诊断为", "人格障碍", "认知障碍", "理解能力差", "智力低", "不配合的", "抑郁症患者")):
                    raise ValueError("Learning hypothesis contains an unsupported personal label")
            state["reflection"] = {"status": "ready", "attempt": attempt, "applied": False, **decision.model_dump()}
            event.status = "success"
            event.trace_encrypted = encrypt_json({"kind": "post_lesson_reflection", "output": decision.model_dump(), "applied": False})
            for key, value in _completion_metadata(TurnResult(reply="", state={}, trace={}, completion=completion)).items():
                setattr(event, key, value)
        except Exception as exc:
            db.rollback()
            conversation = db.get(Conversation, conversation_id)
            event = db.get(TurnEvent, event.id)
            if conversation is None or event is None:
                return
            state = decrypt_json(conversation.agent_state_encrypted)
            state["reflection"] = {"status": "failed", "attempt": attempt, "applied": False, "error": "课后复盘暂时不可用，您可稍后重试；已完成的课程和本人记录不受影响。"}
            event.status = "error"
            event.error_type = type(exc).__name__
            event.error_encrypted = encrypt_text(str(exc)[:1000])
            event.trace_encrypted = encrypt_json({"kind": "post_lesson_reflection", "applied": False})
        finally:
            if conversation is not None and event is not None:
                saved = db.execute(update(Conversation).where(Conversation.id == conversation_id, Conversation.active_request_id == token).values(agent_state_encrypted=encrypt_json(state), active_request_id=None, processing_started_at=None)).rowcount
                if saved != 1:
                    event.status = "error"
                    event.error_type = "ReflectionLeaseLost"
                event.completed_at = utcnow()
                event.latency_ms = int((time.perf_counter() - started) * 1000)
                db.commit()
