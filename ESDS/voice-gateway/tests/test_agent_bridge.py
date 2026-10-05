from __future__ import annotations

import json
import unittest

import httpx
from esds_voice.contracts import EmotionSnapshot

from esds_voice.providers.agent_bridge import (
    AgentBridgeChatClient,
    CbtAgentBridgeChatClient,
)


class AgentBridgeChatClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_emotion_survives_reopen_retry_but_not_next_turn(self):
        payloads = []
        def handler(request):
            if request.url.path.endswith("/sessions/open"):
                return httpx.Response(200, json={"conversation_id": "daily-1"})
            payloads.append(json.loads(request.content))
            if len(payloads) == 1:
                return httpx.Response(404)
            return httpx.Response(200, json={"reply": "我在听。"})
        client = AgentBridgeChatClient(base_url="http://test", token="test", device_id="test", transport=httpx.MockTransport(handler))
        try:
            messages = [{"role": "system", "content": "do not forward"}, {"role": "user", "content": "我很难过"}]
            hint = EmotionSnapshot(-.2, 0, "low", .45, ("negative_words",))
            self.assertEqual("".join([x async for x in client.stream_reply_with_emotion(messages, hint)]), "我在听。")
            self.assertEqual(payloads[0]["emotion"], {"label": "low", "confidence": .45, "evidence": ["negative_words"]})
            self.assertEqual(payloads[0], payloads[1])
            self.assertNotIn("do not forward", json.dumps(payloads))
            _ = [x async for x in client.stream_reply(messages)]
            self.assertNotIn("emotion", payloads[-1])
        finally:
            await client.close()

    async def test_cbt_does_not_forward_daily_emotion(self):
        payloads = []
        def handler(request):
            if request.url.path.endswith("/sessions/open"):
                return httpx.Response(200, json={"conversation_id": "cbt-1"})
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"reply": "继续练习。"})
        client = CbtAgentBridgeChatClient(base_url="http://test", token="test", device_id="test", lesson_id="lesson-1", transport=httpx.MockTransport(handler))
        try:
            _ = [x async for x in client.stream_reply_with_emotion(
                [{"role": "user", "content": "我很难过"}], EmotionSnapshot(0, 0, "low", .45, ()),
            )]
            self.assertNotIn("emotion", payloads[0])
        finally:
            await client.close()

    async def test_persistent_session_turn_returns_agent_reply(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/healthz"):
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path.endswith("/sessions/open"):
                return httpx.Response(
                    200,
                    json={
                        "conversation_id": "conversation-1",
                        "resumed": True,
                    },
                )
            if request.url.path.endswith("/turns"):
                payload = json.loads(request.content)
                self.assertEqual(payload["transcript"], "孩子给我打电话了。")
                self.assertTrue(payload["idempotency_key"].startswith("voice-"))
                return httpx.Response(
                    200,
                    json={"reply": "那挺好啊，聊了些什么？"},
                )
            return httpx.Response(404)

        client = AgentBridgeChatClient(
            base_url="http://agent.local",
            token="bridge-token",
            device_id="esds-pi-test",
            transport=httpx.MockTransport(handler),
        )
        await client.warmup()
        reply = "".join(
            [
                part
                async for part in client.stream_reply(
                    [
                        {"role": "system", "content": "not forwarded"},
                        {"role": "user", "content": "孩子给我打电话了。"},
                    ]
                )
            ]
        )
        await client.close()

        self.assertEqual(reply, "那挺好啊，聊了些什么？")
        self.assertEqual(len(requests), 3)
        self.assertTrue(
            all(
                request.headers["authorization"] == "Bearer bridge-token"
                for request in requests
            )
        )

    async def test_missing_user_transcript_is_rejected(self) -> None:
        client = AgentBridgeChatClient(
            base_url="http://agent.local",
            token="bridge-token",
            device_id="esds-pi-test",
        )
        with self.assertRaisesRegex(RuntimeError, "no user transcript"):
            async for _ in client.stream_reply(
                [{"role": "system", "content": "instructions"}]
            ):
                pass

    async def test_cbt_bridge_uses_cbt_endpoints(self) -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            if request.url.path.endswith("/healthz"):
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path.endswith("/sessions/open"):
                payload = json.loads(request.content)
                self.assertEqual(payload["lesson_id"], "lesson-1")
                return httpx.Response(200, json={"conversation_id": "cbt-1"})
            if request.url.path.endswith("/turns"):
                return httpx.Response(200, json={"reply": "继续说说最近的困扰。"})
            return httpx.Response(404)

        client = CbtAgentBridgeChatClient(
            base_url="http://agent.local",
            token="bridge-token",
            device_id="esds-pi-test",
            lesson_id="lesson-1",
            transport=httpx.MockTransport(handler),
        )
        await client.warmup()
        reply = "".join(
            [
                part
                async for part in client.stream_reply(
                    [{"role": "user", "content": "我最近心情大概三分。"}]
                )
            ]
        )
        await client.close()

        self.assertEqual(reply, "继续说说最近的困扰。")
        self.assertEqual(paths[0], "/internal/voice/v1/healthz")
        self.assertEqual(paths[1], "/internal/voice/v1/cbt/sessions/open")
        self.assertEqual(paths[2], "/internal/voice/v1/cbt/sessions/cbt-1/turns")


if __name__ == "__main__":
    unittest.main()
