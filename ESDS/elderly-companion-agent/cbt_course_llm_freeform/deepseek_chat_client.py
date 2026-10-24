"""DeepSeek Chat Completions transport; credentials remain server-side."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from cbt_course.azure_chat_client import _verified_urlopen
from daily_agent.azure_chat_client import (
    ChatCompletionResult,
    ChatCompletionStreamChunk,
    iter_sse_data,
)


class DeepSeekChatCompletionsClient:
    def __init__(self, *, api_key, model="deepseek-flash", timeout=20, opener=_verified_urlopen):
        self.api_key, self.model, self.timeout, self.opener = api_key, model, timeout, opener

    def _request(
        self, messages, *, temperature, max_completion_tokens, response_format, stream=False
    ):
        # Keep historical replies as data, not assistant-format examples to imitate.
        # Preserve every speaker and ID, including agent sources for reflection.
        wire_messages, history = [], []
        for message in messages:
            adapted = dict(message)
            if (
                response_format
                and response_format.get("type") == "json_object"
                and message.get("role") in {"assistant", "user"}
            ):
                try:
                    prior = json.loads(message["content"])
                    if (
                        isinstance(prior, dict)
                        and set(prior) == {"id", "text"}
                        and isinstance(prior["text"], str)
                    ):
                        history.append(
                            {
                                "id": prior["id"],
                                "role": "agent" if message["role"] == "assistant" else "learner",
                                "content": prior["text"],
                            }
                        )
                        continue
                except (ValueError, TypeError):
                    pass
            wire_messages.append(adapted)
        if history:
            wire_messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {"kind": "course_history", "messages": history}, ensure_ascii=False
                    ),
                }
            )
        payload = {
            "model": self.model,
            "messages": wire_messages,
            "max_tokens": max_completion_tokens,
            "thinking": {"type": "disabled"},
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if response_format:
            payload["response_format"] = response_format
        if stream:
            payload.update(stream=True, stream_options={"include_usage": True})
        return urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
            },
            method="POST",
        )

    def _result(self, text, body, request_id, finish_reason):
        usage = body.get("usage") or {}
        return ChatCompletionResult(
            text=text,
            model=str(body.get("model") or self.model),
            deployment=self.model,
            api_version="deepseek-course-json-v1",
            request_id=request_id,
            finish_reason=finish_reason,
            usage={
                key: usage[key]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if isinstance(usage.get(key), int)
            },
        )

    def complete_with_metadata(
        self, messages, *, temperature=None, max_completion_tokens=1200, response_format=None
    ):
        request = self._request(
            messages,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            response_format=response_format,
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                request_id = response.headers.get("x-request-id", "")
            first = body["choices"][0]
            text = first["message"].get("content")
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError("DeepSeek returned empty content.")
            return self._result(text, body, request_id, str(first.get("finish_reason") or ""))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"DeepSeek API request failed (HTTP {exc.code}).") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("DeepSeek API connection failed.") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("DeepSeek API returned an invalid response.") from exc

    def stream_with_metadata(
        self, messages, *, temperature=None, max_completion_tokens=1200, response_format=None
    ):
        request = self._request(
            messages,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            response_format=response_format,
            stream=True,
        )
        parts, metadata, finish_reason, done = [], {}, "", False
        try:
            with self.opener(request, timeout=self.timeout) as response:
                request_id = response.headers.get("x-request-id", "")
                for data in iter_sse_data(response):
                    if data == "[DONE]":
                        done = True
                        break
                    body = json.loads(data)
                    if body.get("error"):
                        raise RuntimeError("DeepSeek stream returned an error.")
                    if body.get("model"):
                        metadata["model"] = body["model"]
                    if isinstance(body.get("usage"), dict):
                        metadata["usage"] = body["usage"]
                    choices = body.get("choices") or []
                    if not choices:
                        continue
                    first = choices[0]
                    finish_reason = str(first.get("finish_reason") or finish_reason)
                    text = (first.get("delta") or {}).get("content")
                    if isinstance(text, str) and text:
                        parts.append(text)
                        yield ChatCompletionStreamChunk(delta=text)
                if not done or not finish_reason or not parts:
                    raise RuntimeError("DeepSeek stream ended before completion.")
                yield ChatCompletionStreamChunk(
                    completion=self._result("".join(parts), metadata, request_id, finish_reason)
                )
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"DeepSeek API request failed (HTTP {exc.code}).") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("DeepSeek API connection failed.") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("DeepSeek API returned an invalid stream.") from exc
