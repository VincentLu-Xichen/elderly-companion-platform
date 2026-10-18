from __future__ import annotations

import json
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from cbt_course_llm_freeform.preview import PreviewClient
from daily_agent.azure_chat_client import ChatCompletionStreamChunk
from webapp.database import SessionLocal, init_database
from webapp.main import app
from webapp.models import Participant
from webapp.security import hash_secret


class CourseStreamApiTests(unittest.TestCase):
    def test_stream_auth_csrf_ownership_result_and_idempotency(self):
        init_database()
        codes = [uuid.uuid4().hex, uuid.uuid4().hex]
        with SessionLocal() as db:
            for code in codes:
                db.add(Participant(label=code, invite_hash=hash_secret(code)))
            db.commit()
        class Client(PreviewClient):
            def stream_with_metadata(self, messages, **kwargs):
                completion = self.complete_with_metadata(messages, **kwargs)
                for index in range(0, len(completion.text), 8):
                    yield ChatCompletionStreamChunk(delta=completion.text[index:index + 8])
                yield ChatCompletionStreamChunk(completion=completion)
        with TestClient(app) as browser, patch("cbt_course_llm_freeform.agent.FreeformCourseAgent._client_from_env", return_value=Client()):
            browser.post("/api/session/invite", json={"code": codes[0]})
            headers = {"X-CSRF-Token": browser.cookies.get("csrf_token")}
            browser.post("/api/consents", json={"agreed": True}, headers=headers)
            conversation_id = browser.post("/api/cbt-course/lessons/lesson-1/start", json={}, headers=headers).json()["id"]
            endpoint = f"/api/cbt-course/conversations/{conversation_id}/messages/stream"
            payload = {"content": "5", "idempotency_key": uuid.uuid4().hex, "expected_revision": 0}
            self.assertEqual(browser.post(endpoint, json=payload).status_code, 403)
            response = browser.post(endpoint, json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            self.assertEqual(events[0]["type"], "start")
            self.assertIn("reply_delta", [item["type"] for item in events])
            self.assertEqual(events[-1]["type"], "result")
            self.assertEqual(events[-1]["data"]["course"]["current_step"], "learn")
            replay = browser.post(endpoint, json=payload, headers=headers)
            replay_events = [json.loads(line[6:]) for line in replay.text.splitlines() if line.startswith("data: ")]
            self.assertTrue(replay_events[-1]["data"]["deduplicated"])
            browser.post("/api/session/invite", json={"code": codes[1]})
            other_headers = {"X-CSRF-Token": browser.cookies.get("csrf_token")}
            self.assertEqual(browser.post(endpoint, json=payload, headers=other_headers).status_code, 404)
