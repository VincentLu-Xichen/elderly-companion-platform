"""Azure OpenAI Chat Completions client for the CBT course."""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import certifi


def _verified_urlopen(request: urllib.request.Request, *, timeout: int):
    """Open HTTPS using certifi's maintained CA bundle (needed by python.org macOS builds)."""
    context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.urlopen(request, timeout=timeout, context=context)


@dataclass
class ChatCompletionResult:
    text: str
    model: str = ""
    deployment: str = ""
    api_version: str = ""
    request_id: str = ""
    finish_reason: str = ""
    usage: Dict[str, int] = field(default_factory=dict)


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
        opener: Callable = _verified_urlopen,
        max_attempts: int = 3,
        retry_delay_seconds: float = 0.5,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        self.timeout = timeout
        self.opener = opener
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self.sleeper = sleeper

    @classmethod
    def from_env(cls, *, opener: Callable = _verified_urlopen) -> "AzureChatCompletionsClient":
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
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    request_id = response.headers.get("x-request-id", "")
                break
            except urllib.error.HTTPError as error:
                retryable = error.code in {408, 409, 429, 500, 502, 503, 504}
                if retryable and attempt < self.max_attempts:
                    error.close()
                    self.sleeper(self.retry_delay_seconds * attempt)
                    continue
                detail = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Azure OpenAI API request failed: {error.code} {detail}") from error
            except urllib.error.URLError as error:
                if attempt < self.max_attempts:
                    self.sleeper(self.retry_delay_seconds * attempt)
                    continue
                raise RuntimeError(f"Azure OpenAI API request failed after {self.max_attempts} attempts: {error.reason}") from error

        return self._extract_result(body, request_id=request_id)

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
