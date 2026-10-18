"""Bridge synchronous course processing to bounded SSE events with an owned DB session."""
from __future__ import annotations

import logging
from queue import Empty, Full, Queue
from threading import Event, Thread

from cbt_course_llm_freeform.services import get_owned_course, process_course_turn
from cbt_course_llm_freeform.reflection import generate_course_reflection
from webapp.database import SessionLocal
from webapp.services import has_current_consent

logger = logging.getLogger("roleplay-chat.cbt-course-stream")


def failure_code(exc):
    """Log only predefined categories, never exception text or learner content."""
    return {
        "课程记录的字段或原话来源无效，本轮进度未改变。": "invalid_evidence",
        "课程模型的结构化回复无效，本轮学习记录未更新。": "invalid_json_schema",
        "课程模型未完整返回结果，本轮进度没有改变。": "incomplete_model_output",
        "课程模型流式回复未完整结束，本轮进度没有改变。": "incomplete_stream",
        "同一字段不能在一轮中提交多个不同摘录。": "duplicate_evidence_field",
        "Streamed reply changed unexpectedly.": "unstable_reply_projection",
        "DeepSeek stream ended before completion.": "upstream_stream_incomplete",
    }.get(str(exc), "other")


def stream_course_turn(*, conversation_id, participant_id, content, idempotency_key, action="chat",
                       expected_revision=None, session_factory=None, runtime_factory=None):
    queue, disconnected = Queue(maxsize=32), Event()
    factory = session_factory or SessionLocal

    def publish(item):
        while not disconnected.is_set():
            try:
                queue.put(item, timeout=0.1)
                return
            except Full:
                continue

    def work():
        try:
            with factory() as db:
                conversation = get_owned_course(db, conversation_id=conversation_id, participant_id=participant_id)
                if conversation is None or not has_current_consent(db, participant_id):
                    raise ValueError("当前会话不可用，请刷新后重试。")
                kwargs = {"content": content, "idempotency_key": idempotency_key, "action": action,
                          "expected_revision": expected_revision,
                          "on_reply": lambda text: publish({"type": "reply_delta", "text": text})}
                if runtime_factory is not None:
                    kwargs["runtime_factory"] = runtime_factory
                result = process_course_turn(db, conversation, **kwargs)
            publish({"type": "result", "data": result})
        except Exception as exc:
            logger.warning("course_stream_failed participant=%s conversation=%s type=%s code=%s cause_type=%s", participant_id, conversation_id, type(exc).__name__, failure_code(exc), type(exc.__cause__).__name__)
            publish({"type": "error", "message": str(exc) if isinstance(exc, ValueError) else "课程回复暂时不可用，本轮进度没有改变，请稍后重试。"})
            return
        if result["course"]["completed"] and result["course"]["reflection"].get("status") == "pending":
            try:
                generate_course_reflection(conversation_id, session_factory=factory)
            except Exception as exc:
                logger.warning("course_reflection_failed conversation=%s type=%s", conversation_id, type(exc).__name__)

    Thread(target=work, daemon=True, name="cbt-course-stream").start()
    try:
        yield {"type": "start"}
        while True:
            try:
                item = queue.get(timeout=10)
            except Empty:
                yield {"type": "heartbeat"}
                continue
            yield item
            if item["type"] in {"result", "error"}:
                break
    finally:
        # A lost browser does not roll back a completed turn. Same-key retry replays it.
        disconnected.set()
