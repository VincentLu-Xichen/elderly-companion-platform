from __future__ import annotations
from dataclasses import dataclass,field
from typing import Dict,Iterator,Optional
import ssl
import urllib.request
import certifi

@dataclass
class ChatCompletionResult:
    text: str
    model: str = ""
    deployment: str = ""
    api_version: str = ""
    request_id: str = ""
    finish_reason: str = ""
    usage: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatCompletionStreamChunk:
    delta: str = ""
    completion: Optional[ChatCompletionResult] = None


def iter_sse_data(response) -> Iterator[str]:
    """Yield data fields from an SSE response without retaining the whole body."""

    data_lines: list[str] = []
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.rstrip("\r\n")
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines.clear()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield "\n".join(data_lines)


def _verified_urlopen(request: urllib.request.Request, *, timeout: int):
    """Open HTTPS using certifi's maintained CA bundle (needed by python.org macOS builds)."""
    context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.urlopen(request, timeout=timeout, context=context)

