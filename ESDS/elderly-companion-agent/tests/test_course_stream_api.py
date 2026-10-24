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
    def test_only_two_lessons_start_and_retired_history_is_read_only(self):
        from cbt_course_llm_freeform.services import AGENT_VERSION
        from cbt_course_llm_freeform.tests.test_two_lesson_scope import historical_state
        from webapp.models import Conversation, Message
        from webapp.security import encrypt_json, encrypt_text

        init_database()
        codes = [uuid.uuid4().hex, uuid.uuid4().hex]
        with SessionLocal() as db:
            people = [Participant(label=code, invite_hash=hash_secret(code)) for code in codes]
            db.add_all(people)
            db.flush()
            state = historical_state(3)
            row = Conversation(participant_id=people[0].id, mode="cbt", agent_version=AGENT_VERSION,
                agent_prompt_hash="historical", lesson_id="lesson-3", lesson_version=state["lesson_version"],
                status="completed", agent_state_encrypted=encrypt_json(state))
            db.add(row)
            db.flush()
            db.add(Message(conversation_id=row.id, role="learner", sequence=1, content_encrypted=encrypt_text("合成历史案例")))
            db.commit()
            cid = row.id
        with TestClient(app) as browser, patch("cbt_course_llm_freeform.agent.FreeformCourseAgent._client_from_env") as model:
            browser.post("/api/session/invite", json={"code": codes[0]})
            headers = {"X-CSRF-Token": browser.cookies.get("csrf_token")}
            browser.post("/api/consents", json={"agreed": True}, headers=headers)
            self.assertEqual(browser.get("/cbt-course").status_code, 200)
            for number in range(3, 9):
                self.assertEqual(browser.post(f"/api/cbt-course/lessons/lesson-{number}/start", json={}, headers=headers).status_code, 400)
            endpoint = f"/api/cbt-course/conversations/{cid}"
            saved = browser.get(endpoint)
            self.assertEqual(saved.status_code, 200)
            self.assertTrue(saved.json()["read_only"])
            self.assertTrue(saved.json()["course"]["archived"])
            self.assertEqual(browser.get(f"/cbt-course/conversations/{cid}").status_code, 200)
            self.assertEqual(browser.post(endpoint+"/messages", json={"content": "继续", "idempotency_key": uuid.uuid4().hex}, headers=headers).status_code, 400)
            stream = browser.post(endpoint+"/messages/stream", json={"content": "继续", "idempotency_key": uuid.uuid4().hex}, headers=headers)
            events = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
            self.assertEqual(events[-1]["type"], "error")
            self.assertEqual(browser.post(endpoint+"/reflection", json={}, headers=headers).status_code, 400)
            self.assertEqual(browser.post(endpoint+"/homework", json={"idempotency_key": uuid.uuid4().hex, "source_kind": "personal", "situation": "不新增"}, headers=headers).status_code, 409)
            model.assert_not_called()
            browser.post("/api/session/invite", json={"code": codes[1]})
            self.assertEqual(browser.get(endpoint).status_code, 404)
            browser.post("/api/session/invite", json={"code": codes[0]})
            headers = {"X-CSRF-Token": browser.cookies.get("csrf_token")}
            self.assertEqual(browser.delete(f"/api/conversations/{cid}", headers=headers).status_code, 400)
            self.assertEqual(browser.post("/api/admin/login", json={"password": "test-admin-password"}).status_code, 200)
            headers = {"X-CSRF-Token": browser.cookies.get("csrf_token")}
            self.assertEqual(browser.delete(f"/api/admin/conversations/{cid}", headers=headers).status_code, 200)
            self.assertEqual(browser.get(endpoint).status_code, 404)

    def test_goal_statement_at_post_check_streams_result_and_replays_once(self):
        from webapp.models import Conversation
        from webapp.security import decrypt_json,encrypt_json
        from cbt_course_llm_freeform.tests.test_goal_handoff import post_check
        init_database();code=uuid.uuid4().hex
        with SessionLocal() as db:
            db.add(Participant(label=code,invite_hash=hash_secret(code)));db.commit()
        with TestClient(app) as browser:
            browser.post('/api/session/invite',json={'code':code})
            headers={'X-CSRF-Token':browser.cookies.get('csrf_token')}
            browser.post('/api/consents',json={'agreed':True},headers=headers)
            cid=browser.post('/api/cbt-course/lessons/lesson-1/start',json={},headers=headers).json()['id']
            with SessionLocal() as db:
                row=db.get(Conversation,cid);row.agent_state_encrypted=encrypt_json(post_check());db.commit()
            endpoint=f'/api/cbt-course/conversations/{cid}/messages/stream'
            payload=dict(content='我的练习目标就是想减少焦虑 更积极的面对生活',idempotency_key=uuid.uuid4().hex)
            with patch('cbt_course_llm_freeform.agent.FreeformCourseAgent._client_from_env',return_value=PreviewClient()):
                first=browser.post(endpoint,json=payload,headers=headers)
                events=[json.loads(line[6:]) for line in first.text.splitlines() if line.startswith('data: ')]
                self.assertEqual(events[-1]['type'],'result',first.text)
                self.assertEqual(events[-1]['data']['course']['current_step'],'learning_goal')
                second=browser.post(endpoint,json=payload,headers=headers)
                events=[json.loads(line[6:]) for line in second.text.splitlines() if line.startswith('data: ')]
                self.assertTrue(events[-1]['data']['deduplicated'])
            with SessionLocal() as db:
                state=decrypt_json(db.get(Conversation,cid).agent_state_encrypted)
                self.assertIsNotNone(state['blueprint']['goal_direction'])
                self.assertNotIn('learning_goal',state)

    def test_diary_api_requires_consent_csrf_owner_and_current_version(self):
        from webapp.models import Conversation, CourseHomeworkEntry, TurnEvent
        from webapp.security import decrypt_json, encrypt_json
        from sqlalchemy import select
        init_database()
        codes = [uuid.uuid4().hex, uuid.uuid4().hex]
        with SessionLocal() as db:
            for code in codes:
                db.add(Participant(label=code,invite_hash=hash_secret(code)))
            db.commit()
        with TestClient(app) as browser:
            browser.post("/api/session/invite",json={"code":codes[0]})
            headers={"X-CSRF-Token":browser.cookies.get("csrf_token")}
            browser.post("/api/consents",json={"agreed":True},headers=headers)
            cid=browser.post("/api/cbt-course/lessons/lesson-1/start",json={},headers=headers).json()["id"]
            endpoint=f"/api/cbt-course/conversations/{cid}/homework"
            payload=dict(idempotency_key=uuid.uuid4().hex,source_kind="personal",situation="散步时下雨",thought="先回家吧",emotion="失望",behavior="回家")
            self.assertEqual(browser.post(endpoint,json=payload).status_code,403)
            self.assertEqual(browser.post(endpoint,json=payload,headers=headers).status_code,409)
            with SessionLocal() as db:
                row=db.get(Conversation,cid);state=decrypt_json(row.agent_state_encrypted)
                state["completed"]=True;row.status="completed";row.agent_state_encrypted=encrypt_json(state);db.commit()
            saved=browser.post(endpoint,json=payload,headers=headers)
            self.assertEqual(saved.status_code,200,saved.text)
            replay=browser.post(endpoint,json=payload,headers=headers)
            self.assertEqual(replay.json()["id"],saved.json()["id"])
            self.assertEqual(len(replay.json()["entries"]),1)
            self.assertEqual(browser.post(endpoint,json={**payload,"emotion":"平静"},headers=headers).status_code,409)
            with SessionLocal() as db:
                diary=db.get(CourseHomeworkEntry,saved.json()["id"])
                self.assertNotIn("散步",diary.payload_encrypted)
                events=db.scalars(select(TurnEvent).where(TurnEvent.conversation_id==cid)).all()
                self.assertEqual(len(events),1)
                self.assertEqual(events[0].total_tokens,0)
                row=db.get(Conversation,cid);row.lesson_version="old";db.commit()
            self.assertEqual(browser.post(endpoint,json={**payload,"idempotency_key":uuid.uuid4().hex},headers=headers).status_code,409)
            browser.post("/api/session/invite",json={"code":codes[1]})
            other={"X-CSRF-Token":browser.cookies.get("csrf_token")}
            self.assertEqual(browser.post(endpoint,json=payload,headers=other).status_code,404)
            browser.post("/api/consents",json={"agreed":True},headers=other)
            own_cid=browser.post("/api/cbt-course/lessons/lesson-2/start",json={},headers=other).json()["id"]
            with SessionLocal() as db:
                from webapp.models import Consent
                person=db.scalar(select(Participant).where(Participant.label==codes[1]))
                for consent in db.scalars(select(Consent).where(Consent.participant_id==person.id)):
                    db.delete(consent)
                db.commit()
            self.assertEqual(browser.post(f"/api/cbt-course/conversations/{own_cid}/homework",json=payload,headers=other).status_code,403)
            with SessionLocal() as db:
                row=db.get(Conversation,cid);db.delete(row);db.commit()
                self.assertIsNone(db.get(CourseHomeworkEntry,saved.json()["id"]))

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
            from webapp.models import Conversation
            from cbt_course_llm_freeform.tests.shared_turn_fixture import shared_state
            from webapp.security import encrypt_json
            with SessionLocal() as db:
                conversation = db.get(Conversation, conversation_id)
                state = shared_state(reflection_policy="none")
                state["conversation_id"] = conversation_id
                conversation.agent_state_encrypted = encrypt_json(state)
                db.commit()
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
