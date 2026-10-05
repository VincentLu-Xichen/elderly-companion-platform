from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from daily_agent.azure_chat_client import ChatCompletionResult


@dataclass
class AgentTurnResult:
    """Serializable result for one Daily Chat turn."""

    reply: str
    mode: str
    trace: Dict[str, Any] = field(default_factory=dict)
    runtime_state: Dict[str, Any] = field(default_factory=dict)
    safety_event: Optional[str] = None
    completion: Optional[ChatCompletionResult] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def complete_with_metadata_compat(client: Any, messages, **kwargs) -> ChatCompletionResult:
    """Use rich completion metadata when supported without breaking test clients."""

    if hasattr(client, "complete_with_metadata"):
        return client.complete_with_metadata(messages, **kwargs)
    return ChatCompletionResult(text=client.complete(messages, **kwargs))
