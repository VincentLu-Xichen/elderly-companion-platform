"""Azure OpenAI Chat Completions client for Daily Chat."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional


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


class AzureChatCompletionsClient:
    """Small stdlib Azure OpenAI Chat Completions client."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-12-01-preview",
        timeout: int = 60,
        opener: Callable = urllib.request.urlopen,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        self.timeout = timeout
        self.opener = opener

    @classmethod
    def from_env(cls, *, opener: Callable = urllib.request.urlopen) -> "AzureChatCompletionsClient":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        if not endpoint:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT is not set.")

        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("AZURE_OPENAI_API_KEY is not set.")

        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        if not deployment:
            raise RuntimeError("AZURE_OPENAI_DEPLOYMENT is not set.")

        return cls(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
            opener=opener,
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_completion_tokens: int = 1200,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.complete_with_metadata(
            messages,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            response_format=response_format,
        ).text

    def complete_with_metadata(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_completion_tokens: int = 1200,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> ChatCompletionResult:
        payload = {
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
        }
        if temperature == 1.0:
            payload["temperature"] = temperature
        if response_format:
            payload["response_format"] = response_format

        request = urllib.request.Request(
            self._chat_completions_url(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "api-key": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                request_id = response.headers.get("x-request-id", "")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Azure OpenAI API request failed: {error.code} {detail}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Azure OpenAI API request failed: {error.reason}") from error

        return self._extract_result(body, request_id=request_id)

    def stream_with_metadata(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_completion_tokens: int = 1200,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Iterator[ChatCompletionStreamChunk]:
        payload = {
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
            "stream": True,
        }
        if temperature == 1.0:
            payload["temperature"] = temperature
        if response_format:
            payload["response_format"] = response_format
        request = urllib.request.Request(
            self._chat_completions_url(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        parts: list[str] = []
        usage: Dict[str, int] = {}
        finish_reason = ""
        model = self.deployment
        try:
            with self.opener(request, timeout=self.timeout) as response:
                request_id = response.headers.get("x-request-id", "")
                for data in iter_sse_data(response):
                    if data == "[DONE]":
                        break
                    try:
                        body = json.loads(data)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if not isinstance(body, dict):
                        continue
                    model = str(body.get("model") or model)
                    raw_usage = body.get("usage")
                    if isinstance(raw_usage, dict):
                        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                            value = raw_usage.get(key)
                            if isinstance(value, int):
                                usage[key] = value
                    choices = body.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    first = choices[0]
                    if not isinstance(first, dict):
                        continue
                    finish_reason = str(first.get("finish_reason") or finish_reason)
                    delta = first.get("delta") or {}
                    text = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(text, str) and text:
                        parts.append(text)
                        yield ChatCompletionStreamChunk(delta=text)
                full_text = "".join(parts).strip()
                if not full_text:
                    raise RuntimeError("Azure OpenAI stream returned no message content.")
                yield ChatCompletionStreamChunk(
                    completion=ChatCompletionResult(
                        text=full_text,
                        model=model,
                        deployment=self.deployment,
                        api_version=self.api_version,
                        request_id=request_id,
                        finish_reason=finish_reason,
                        usage=usage,
                    )
                )
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Azure OpenAI API request failed: {error.code} {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Azure OpenAI API request failed: {error.reason}") from error

    def _chat_completions_url(self) -> str:
        deployment = urllib.parse.quote(self.deployment, safe="")
        query = urllib.parse.urlencode({"api-version": self.api_version})
        return f"{self.endpoint}/openai/deployments/{deployment}/chat/completions?{query}"

    def _extract_text(self, body: Dict[str, object]) -> str:
        return self._extract_result(body).text

    def _extract_result(self, body: Dict[str, object], *, request_id: str = "") -> ChatCompletionResult:
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        usage = body.get("usage")
                        normalized_usage: Dict[str, int] = {}
                        if isinstance(usage, dict):
                            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                                value = usage.get(key)
                                if isinstance(value, int):
                                    normalized_usage[key] = value
                        return ChatCompletionResult(
                            text=content.strip(),
                            model=str(body.get("model", "")),
                            deployment=self.deployment,
                            api_version=self.api_version,
                            request_id=request_id,
                            finish_reason=str(first_choice.get("finish_reason", "")),
                            usage=normalized_usage,
                        )
        raise RuntimeError("Azure OpenAI API response did not contain message content.")
