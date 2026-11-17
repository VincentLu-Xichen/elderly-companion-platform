"""Public notices contain no exception strings, learner text or model output."""
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError


class SavedTurnUnavailable(RuntimeError):
    """The main transaction committed, but its response could not be assembled."""


# notice -> (HTTP status, safe message, next action, main-turn outcome)
NOTICES = {
    "refresh": (409, "记录已更新，请刷新后继续；原输入会保留。", "refresh", "unknown"),
    "processing": (409, "上一轮仍在处理中，请稍后刷新查看。", "check", "unknown"),
    "read_only": (409, "这份历史记录仅供查看，请从课程入口继续。", "stop", "unchanged"),
    "edit": (422, "这次输入暂时无法提交，请检查内容后重新发送。", "edit", "unchanged"),
    "turn_failed": (502, "这轮暂时没能完成，请保留原输入，稍后重试。", "retry", "unchanged"),
    "result_unknown": (502, "暂时没能取得本轮结果，请先刷新记录确认。", "check", "unknown"),
    "saved": (503, "本轮已经保存，页面暂未更新，请刷新查看。", "check", "saved"),
    "load_failed": (503, "记录暂时无法读取，请稍后刷新重试。", "refresh", "unknown"),
    "sign_in": (401, "请先使用邀请码登录，再继续查看。", "stop", "unchanged"),
    "forbidden": (403, "请刷新页面，并确认已完成数据记录告知。", "refresh", "unchanged"),
    "not_found": (404, "暂时找不到这份记录，请返回课程入口查看。", "stop", "unchanged"),
    "too_long": (413, "这条消息较长，请缩短后再发送。", "edit", "unchanged"),
    "slow_down": (429, "操作有些频繁，请稍后再试。", "retry", "unchanged"),
}


def public_notice(error, *, is_turn=False):
    from .contracts import DialogueError
    if isinstance(error, SavedTurnUnavailable):
        return "saved"
    if isinstance(error, RequestValidationError):
        return "edit"
    if isinstance(error, HTTPException):
        return {401:"sign_in",403:"forbidden",404:"not_found",413:"too_long",429:"slow_down"}.get(
            error.status_code, "result_unknown" if is_turn else "load_failed")
    if isinstance(error, PermissionError):
        return "forbidden"
    if isinstance(error, DialogueError):
        if error.code == "conversation_busy": return "processing"
        if error.code in {"historical_version_read_only", "active_version_conflict"}: return "read_only"
        if error.code in {"invalid_input", "control_content_must_be_empty", "idempotency_conflict"}: return "edit"
        if error.code in {"revision_conflict", "old_failed_turn", "another_session_active",
                          "control_not_available", "session_closed", "lease_expired"}: return "refresh"
        return "turn_failed" if is_turn else "load_failed"
    return "result_unknown" if is_turn else "load_failed"
