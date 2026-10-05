from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    type: str
    audio: bytes | None = None
    text: str | None = None
    item_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class RealtimeProvider(Protocol):
    manual_audio_commit: bool

    async def connect(self) -> None: ...

    async def send_audio(self, pcm: bytes) -> None: ...

    async def finish_audio_turn(self) -> None: ...

    async def cancel(
        self, *, item_id: str | None, played_ms: int, cancel_response: bool = True
    ) -> None: ...

    async def update_instructions(self, instructions: str) -> None: ...

    async def create_response(self, instructions: str) -> None: ...

    def events(self) -> AsyncIterator[ProviderEvent]: ...

    async def close(self) -> None: ...
