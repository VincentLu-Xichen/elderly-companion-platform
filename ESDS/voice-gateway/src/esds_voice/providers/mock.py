from __future__ import annotations

import asyncio
from typing import AsyncIterator

from .base import ProviderEvent


class MockRealtimeProvider:
    """Offline provider for protocol development and deterministic tests."""

    manual_audio_commit = False

    def __init__(self) -> None:
        self.connected = False
        self.audio_bytes_received = 0
        self.cancel_count = 0
        self.truncate_count = 0
        self.response_count = 0
        self.scripted_responses: list[tuple[str, str]] = []
        self.remembered_scripted_responses: list[str] = []
        self.instructions = ""
        self._events: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()

    async def connect(self) -> None:
        self.connected = True

    async def send_audio(self, pcm: bytes) -> None:
        self.audio_bytes_received += len(pcm)

    async def finish_audio_turn(self) -> None:
        return

    async def cancel(
        self, *, item_id: str | None, played_ms: int, cancel_response: bool = True
    ) -> None:
        self.cancel_count += int(cancel_response)
        self.truncate_count += int(item_id is not None)
        await self._events.put(
            ProviderEvent("response.cancelled", item_id=item_id, data={"played_ms": played_ms})
        )

    async def update_instructions(self, instructions: str) -> None:
        self.instructions = instructions

    async def create_response(self, instructions: str) -> None:
        self.instructions = instructions
        self.response_count += 1

    async def create_scripted_response(
        self,
        text: str,
        instructions: str,
        *,
        remember: bool = False,
    ) -> None:
        self.instructions = instructions
        self.response_count += 1
        self.scripted_responses.append((text, instructions))
        if remember:
            self.remembered_scripted_responses.append(text)

    async def emit(self, event: ProviderEvent) -> None:
        await self._events.put(event)

    async def events(self) -> AsyncIterator[ProviderEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def close(self) -> None:
        self.connected = False
        await self._events.put(None)
