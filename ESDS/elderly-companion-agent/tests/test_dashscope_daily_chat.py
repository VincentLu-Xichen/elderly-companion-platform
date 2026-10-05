from __future__ import annotations

import json
import unittest

from daily_agent.dashscope_chat_client import DashScopeChatCompletionsClient


class FakeResponse:
    def __init__(self, body: dict, headers: dict[str, str] | None = None) -> None:
        self.body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.body, ensure_ascii=False).encode("utf-8")


class DashScopeDailyChatTests(unittest.TestCase):
    def test_completion_uses_openai_compatible_contract_and_metadata(self) -> None:
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(
                {
                    "model": "qwen-plus-build",
                    "choices": [
                        {
                            "message": {"content": "那挺好啊，聊了些什么？"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 8,
                        "total_tokens": 17,
                    },
                },
                {"x-request-id": "dashscope-request-id"},
            )

        client = DashScopeChatCompletionsClient(
            api_key="test-key",
            model="qwen-plus",
            opener=opener,
        )
        result = client.complete_with_metadata(
            [{"role": "user", "content": "孩子来电话了。"}],
            temperature=0.8,
            max_completion_tokens=200,
        )

        self.assertEqual(
            captured["url"],
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        )
        self.assertEqual(captured["payload"]["model"], "qwen-plus")
        self.assertEqual(captured["payload"]["max_tokens"], 200)
        self.assertEqual(captured["payload"]["temperature"], 0.8)
        self.assertEqual(result.text, "那挺好啊，聊了些什么？")
        self.assertEqual(result.request_id, "dashscope-request-id")
        self.assertEqual(result.usage["total_tokens"], 17)


if __name__ == "__main__":
    unittest.main()
