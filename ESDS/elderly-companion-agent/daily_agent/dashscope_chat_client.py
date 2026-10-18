"""Alibaba Model Studio OpenAI-compatible client for Daily Chat."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Iterator, List, Optional

from daily_agent.azure_chat_client import (
    ChatCompletionResult,
    ChatCompletionStreamChunk,
    iter_sse_data,
)


class DashScopeChatCompletionsClient:
    """Small stdlib client matching the Daily Chat completion interface."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "qwen-plus",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout: int = 60,
        opener: Callable = urllib.request.urlopen,
        enable_thinking: bool | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = opener
        self.enable_thinking = enable_thinking

    @classmethod
    def from_env(
        cls,
        *,
        opener: Callable = urllib.request.urlopen,
    ) -> "DashScopeChatCompletionsClient":
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not set.")
        return cls(
            api_key=api_key,
            model=os.getenv("DASHSCOPE_CHAT_MODEL", "qwen-plus"),
            base_url=os.getenv(
                "DASHSCOPE_CHAT_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
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
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_completion_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if response_format:
            payload["response_format"] = response_format
        if self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
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
            raise RuntimeError(
                f"DashScope API request failed: {error.code} {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(
                f"DashScope API request failed: {error.reason}"
            ) from error
        return self._extract_result(body, request_id=request_id)

    def stream_with_metadata(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_completion_tokens: int = 1200,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Iterator[ChatCompletionStreamChunk]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_completion_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
        if temperature is not None:
            payload["temperature"] = temperature
        if response_format:
            payload["response_format"] = response_format
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        parts: list[str] = []
        usage: Dict[str, int] = {}
        finish_reason = ""
        model = self.model
        request_id = ""
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
                    raise RuntimeError("DashScope stream returned no message content.")
                yield ChatCompletionStreamChunk(
                    completion=ChatCompletionResult(
                        text=full_text,
                        model=model,
                        deployment=self.model,
                        api_version="dashscope-openai-compatible-v1",
                        request_id=request_id,
                        finish_reason=finish_reason,
                        usage=usage,
                    )
                )
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"DashScope API request failed: {error.code} {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"DashScope API request failed: {error.reason}") from error

    def _extract_result(
        self,
        body: Dict[str, object],
        *,
        request_id: str = "",
    ) -> ChatCompletionResult:
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        usage = body.get("usage")
                        normalized_usage: Dict[str, int] = {}
                        if isinstance(usage, dict):
                            for key in (
                                "prompt_tokens",
                                "completion_tokens",
                                "total_tokens",
                            ):
                                value = usage.get(key)
                                if isinstance(value, int):
                                    normalized_usage[key] = value
                        return ChatCompletionResult(
                            text=content.strip(),
                            model=str(body.get("model", self.model)),
                            deployment=self.model,
                            api_version="dashscope-openai-compatible-v1",
                            request_id=request_id,
                            finish_reason=str(first.get("finish_reason", "")),
                            usage=normalized_usage,
                        )
        raise RuntimeError(
            "DashScope API response did not contain message content."
        )
