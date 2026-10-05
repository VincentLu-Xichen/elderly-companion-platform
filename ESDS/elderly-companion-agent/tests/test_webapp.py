from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch


TEST_DB = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
TEST_DB.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB.name}")
os.environ.setdefault("APP_SECRET", "test-app-secret")
os.environ.setdefault("INVITE_CODES", "student-test:test-invite")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("COOKIE_SECURE", "false")

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from daily_agent.agent_runtime import AgentTurnResult
from daily_agent.azure_chat_client import AzureChatCompletionsClient
from webapp.config import _database_url
from webapp.database import Base, engine_options_for
from webapp.main import app, format_utc8, startup
from webapp.models import Conversation, Participant, RateLimitBucket, TurnEvent
from webapp.rate_limit import _increment_bucket, _key_hash, enforce_rate_limit
from webapp.security import decrypt_text, encrypt_json, hash_secret
from webapp.services import (
    conversation_payload,
    create_conversation,
    dialogue_history_payload,
    full_export_payload,
    process_turn,
)


HISTORICAL_SCENARIO = {
    "id": "loneliness",
    "version": "2.0",
    "title": "独居与孤独",
    "age": 72,
    "background": "你是一位独居老人，老伴已经去世，平时生活基本能够自理。",
    "recent_event": "最近几天很少有人来家里，也没有接到熟人的电话。",
    "automatic_thought": "大概已经没人惦记我了。",
    "deeper_meaning": "最担心的是自己已经不重要，慢慢被大家忘了。",
    "intermediate_belief": "别人如果惦记自己就会主动联系。",
    "emotion": "觉得家里冷清、心里空落落。",
    "behavior": "常常躺着听收音机，不太想下楼活动。",
    "coping_strategy": "不主动打电话，也不下楼。",
    "resources": "楼下有见面会打招呼的邻居。",
    "opening": "这两天家里静得很，也没人跟我说说话。",
    "rules": ["每轮只透露一到两个信息。"],
}


class FakeDailyAgent:
    def reply_turn(self, history):
        return AgentTurnResult(reply="我在听呢。", mode="daily_chat")


class ErrorDailyAgent:
    def reply_turn(self, history):
        raise RuntimeError("simulated provider failure")


class WebAppServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.participant = Participant(label=f"student-{uuid.uuid4()}", invite_hash=hash_secret("code"))
        self.db.add(self.participant)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_historical_cbt_scenario_is_persistent_exportable_and_read_only(self):
        scenario = dict(HISTORICAL_SCENARIO)
        conversation = Conversation(
            participant_id=self.participant.id,
            mode="cbt",
            agent_version="cbt-v1",
            agent_prompt_hash="a" * 64,
            scenario_id=scenario["id"],
            scenario_version=scenario["version"],
            scenario_snapshot_encrypted=encrypt_json(scenario),
        )
        self.db.add(conversation)
        self.db.commit()
        self.assertEqual(conversation.agent_version, "cbt-v1")
        first_payload = conversation_payload(conversation)
        self.assertTrue(conversation.scenario_id)
        self.assertEqual(conversation.scenario_version, "2.0")
        self.assertNotIn(first_payload["scenario"]["opening"], conversation.scenario_snapshot_encrypted)

        self.db.expire_all()
        reloaded = self.db.get(Conversation, conversation.id)
        self.assertEqual(conversation_payload(reloaded)["scenario"], first_payload["scenario"])

        with self.assertRaisesRegex(ValueError, "已归档"):
            process_turn(
                self.db,
                reloaded,
                content="这两天心里很难受。",
                idempotency_key="idem-scenario-001",
            )

        self.db.expire_all()
        exported = full_export_payload(self.db.get(Conversation, conversation.id))
        self.assertEqual(exported["scenario"]["id"], first_payload["scenario"]["id"])
        self.assertEqual(exported["turn_events"], [])
        self.assertEqual(dialogue_history_payload(self.db.get(Conversation, conversation.id)), [])

    def test_legacy_scenario_routes_are_removed(self):
        route_paths = {route.path for route in app.routes}
        self.assertNotIn("/api/conversations/{conversation_id}/scenario", route_paths)
        self.assertNotIn("/api/conversations/{conversation_id}/scenario/confirm", route_paths)

    def test_daily_chat_has_no_scenario(self):
        conversation = create_conversation(self.db, self.participant.id, "daily_chat")
        payload = conversation_payload(conversation)
        self.assertIsNone(payload["scenario_id"])
        self.assertEqual(payload["scenario"], {})
        result = process_turn(
            self.db,
            conversation,
            content="今天天气不错。",
            idempotency_key="idem-daily-0001",
            daily_factory=FakeDailyAgent,
        )
        self.assertEqual(result["reply"], "我在听呢。")

    def test_conversation_time_is_displayed_in_utc8(self):
        self.assertEqual(
            format_utc8("2026-07-23T02:03:00+00:00"),
            "2026-07-23 10:03",
        )

    def test_provider_failure_is_audited_without_plaintext(self):
        conversation = create_conversation(self.db, self.participant.id, "daily_chat")
        with self.assertRaisesRegex(RuntimeError, "simulated provider failure"):
            process_turn(
                self.db,
                conversation,
                content="请制造一个测试错误。",
                idempotency_key="idem-error-0001",
                daily_factory=ErrorDailyAgent,
            )
        event = self.db.scalar(select(TurnEvent).where(TurnEvent.conversation_id == conversation.id))
        self.assertEqual(event.status, "error")
        self.assertEqual(event.error_type, "RuntimeError")
        self.assertNotIn("simulated provider failure", event.error_encrypted)
        self.assertEqual(decrypt_text(event.error_encrypted), "simulated provider failure")

    def test_idempotency_returns_same_reply_without_extra_messages(self):
        conversation = create_conversation(self.db, self.participant.id, "daily_chat")
        first = process_turn(
            self.db,
            conversation,
            content="你好。",
            idempotency_key="idem-repeat-001",
            daily_factory=FakeDailyAgent,
        )
        second = process_turn(
            self.db,
            conversation,
            content="这条内容不会再次保存。",
            idempotency_key="idem-repeat-001",
            daily_factory=FakeDailyAgent,
        )
        self.assertEqual(first["reply"], second["reply"])
        self.assertTrue(second["deduplicated"])
        self.db.expire_all()
        self.assertEqual(len(self.db.get(Conversation, conversation.id).messages), 2)

    def test_azure_result_keeps_deployment_api_version_and_usage(self):
        client = AzureChatCompletionsClient(
            endpoint="https://example.invalid",
            api_key="test",
            deployment="gpt-test",
            api_version="2026-test",
        )
        result = client._extract_result(
            {
                "model": "model-build-1",
                "choices": [{"message": {"content": "回复"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
            request_id="azure-request-id",
        )
        self.assertEqual(result.text, "回复")
        self.assertEqual(result.deployment, "gpt-test")
        self.assertEqual(result.api_version, "2026-test")
        self.assertEqual(result.request_id, "azure-request-id")
        self.assertEqual(result.usage["total_tokens"], 5)

    def test_database_rate_limit_is_shared_and_hashes_the_key(self):
        raw_key = "invite:203.0.113.8"
        key_hash = _key_hash(raw_key)
        window_start = datetime.now(timezone.utc).replace(second=0, microsecond=0)

        self.assertNotIn(raw_key, key_hash)
        self.assertEqual(_increment_bucket(self.db, key_hash, window_start), 1)
        self.assertEqual(_increment_bucket(self.db, key_hash, window_start), 2)
        self.assertEqual(self.db.get(RateLimitBucket, key_hash).request_count, 2)

        next_window = window_start + timedelta(minutes=1)
        self.assertEqual(_increment_bucket(self.db, key_hash, next_window), 1)

    def test_database_rate_limit_rejects_requests_over_limit(self):
        rate_settings = SimpleNamespace(app_secret="rate-test-secret", rate_limit_per_minute=1)
        with patch("webapp.rate_limit.settings", rate_settings):
            enforce_rate_limit(self.db, "admin-login:203.0.113.9")
            with self.assertRaises(HTTPException) as raised:
                enforce_rate_limit(self.db, "admin-login:203.0.113.9")
        self.assertEqual(raised.exception.status_code, 429)


class VercelDeploymentTest(unittest.TestCase):
    def test_supabase_postgres_url_uses_psycopg_driver(self):
        with patch.dict(os.environ, {"POSTGRES_URL": "postgres://user:pass@pooler.invalid:6543/postgres"}):
            os.environ.pop("DATABASE_URL", None)
            self.assertEqual(
                _database_url(),
                "postgresql+psycopg://user:pass@pooler.invalid:6543/postgres",
            )

    def test_supabase_postgres_url_removes_platform_only_query_options(self):
        url = (
            "postgres://user:pass@pooler.invalid:6543/postgres"
            "?supa=base-pooler.x&workaround=supabase-pooler.vercel&sslmode=require"
        )
        with patch.dict(os.environ, {"POSTGRES_URL": url}):
            os.environ.pop("DATABASE_URL", None)
            self.assertEqual(
                _database_url(),
                "postgresql+psycopg://user:pass@pooler.invalid:6543/postgres?sslmode=require",
            )

    def test_transaction_pool_disables_client_pool_and_prepared_statements(self):
        options = engine_options_for("postgresql+psycopg://example.invalid/postgres", "transaction")
        self.assertIs(options["poolclass"], NullPool)
        self.assertIsNone(options["connect_args"]["prepare_threshold"])

    def test_vercel_startup_does_not_run_schema_or_invite_bootstrap(self):
        vercel_settings = SimpleNamespace(is_production=False, is_vercel=True)
        with (
            patch("webapp.main.settings", vercel_settings),
            patch("webapp.main.init_database") as init_database,
            patch("webapp.main.bootstrap_invites") as bootstrap_invites,
        ):
            startup()
        init_database.assert_not_called()
        bootstrap_invites.assert_not_called()

    def test_root_entrypoint_exports_fastapi_app(self):
        from app import app as vercel_app

        self.assertIs(vercel_app, app)


class WebAppApiFlowTest(unittest.TestCase):
    def test_home_navigation_and_participant_logout(self):
        with TestClient(app) as client:
            login = client.post("/api/session/invite", json={"code": "test-invite"})
            self.assertEqual(login.status_code, 200)
            csrf = client.cookies.get("csrf_token")

            home = client.get("/app")
            self.assertEqual(home.status_code, 200)
            self.assertIn('href="#conversation-history"', home.text)
            self.assertIn('id="conversation-history"', home.text)
            self.assertIn('id="logout-button"', home.text)
            self.assertIn("/static/app.js?v=20260723-9", home.text)

            rejected = client.post("/api/session/logout")
            self.assertEqual(rejected.status_code, 403)
            logged_out = client.post(
                "/api/session/logout",
                json={},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(logged_out.status_code, 200)
            self.assertTrue(logged_out.json()["ok"])
            self.assertIsNone(client.cookies.get("participant_session"))
            self.assertIsNone(client.cookies.get("csrf_token"))
            self.assertEqual(client.get("/app").status_code, 401)
            self.assertIn("输入你的实验邀请码", client.get("/").text)

    def test_invite_consent_and_freeform_course_flow(self):
        with TestClient(app) as client:
            landing = client.get("/")
            self.assertEqual(landing.status_code, 200)
            self.assertIn("输入你的实验邀请码", landing.text)
            login = client.post("/api/session/invite", json={"code": "test-invite"})
            self.assertEqual(login.status_code, 200)
            csrf = client.cookies.get("csrf_token")
            headers = {"X-CSRF-Token": csrf}

            denied = client.post("/api/cbt-course/lessons/lesson-1/start", json={}, headers=headers)
            self.assertEqual(denied.status_code, 403)
            consent = client.post("/api/consents", json={"agreed": True}, headers=headers)
            self.assertEqual(consent.status_code, 200)

            legacy_creation = client.post("/api/conversations", json={"mode": "cbt"}, headers=headers)
            self.assertEqual(legacy_creation.status_code, 400)
            self.assertIn("课程目录", legacy_creation.json()["detail"])

            catalog = client.get("/cbt-course")
            self.assertEqual(catalog.status_code, 200)
            self.assertEqual(catalog.text.count('class="course-tile '), 8)
            self.assertIn("认知行为三角", catalog.text)
            self.assertIn("看见情境、想法和心情", catalog.text)
            self.assertEqual(catalog.text.count("内容准备中"), 6)
            self.assertIn("/static/cbt_course/course.css", catalog.text)
            self.assertEqual(client.get("/static/cbt_course/course.css").status_code, 200)
            course_asset = client.get("/cbt-course-assets/lesson_1/course-overview.svg")
            self.assertEqual(course_asset.status_code, 200)
            self.assertIn("image/svg+xml", course_asset.headers["content-type"])

            created = client.post("/api/cbt-course/lessons/lesson-1/start", json={}, headers=headers)
            self.assertEqual(created.status_code, 200)
            conversation_id = created.json()["id"]
            self.assertEqual(created.json()["lesson_id"], "lesson-1")
            self.assertFalse(created.json()["resumed"])
            resumed = client.post("/api/cbt-course/lessons/lesson-1/start", json={}, headers=headers)
            self.assertTrue(resumed.json()["resumed"])
            self.assertEqual(resumed.json()["id"], conversation_id)
            lesson_2_created = client.post("/api/cbt-course/lessons/lesson-2/start", json={}, headers=headers)
            self.assertEqual(lesson_2_created.status_code, 200)
            lesson_2_id = lesson_2_created.json()["id"]
            lesson_2_payload = client.get(f"/api/cbt-course/conversations/{lesson_2_id}").json()
            self.assertEqual(lesson_2_payload["course"]["current_step"], "freeform")
            self.assertEqual(lesson_2_payload["course"]["lesson"]["id"], "lesson-2")
            self.assertEqual(lesson_2_payload["messages"][0]["attachment"], {})
            lesson_2_page = client.get(f"/cbt-course/conversations/{lesson_2_id}")
            self.assertIn("LESSON 02", lesson_2_page.text)
            self.assertIn("看见情境、想法和心情", lesson_2_page.text)

            unavailable = client.post("/api/cbt-course/lessons/lesson-3/start", json={}, headers=headers)
            self.assertEqual(unavailable.status_code, 400)

            course_page = client.get(f"/cbt-course/conversations/{conversation_id}")
            self.assertEqual(course_page.status_code, 200)
            self.assertIn("认知行为三角", course_page.text)
            self.assertIn('id="course-message-input"', course_page.text)
            self.assertIn('class="conversation-send"', course_page.text)
            self.assertIn("course-overview.svg", course_page.text)
            self.assertEqual(course_page.text.count("<button"), 1)
            self.assertNotIn('type="radio"', course_page.text)
            self.assertNotIn('type="range"', course_page.text)
            self.assertNotIn("继续按钮", course_page.text)

            initial_payload = client.get(f"/api/cbt-course/conversations/{conversation_id}")
            self.assertEqual(initial_payload.status_code, 200)
            self.assertEqual(initial_payload.json()["course"]["current_step"], "freeform")
            self.assertEqual(initial_payload.json()["messages"][0]["attachment"]["kind"], "image")
            legacy_message = client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"content": "不能走旧接口", "idempotency_key": "old-route-course-001"},
                headers=headers,
            )
            self.assertEqual(legacy_message.status_code, 400)
            class FakeFreeformAgent:
                def __init__(self, *args, **kwargs):
                    pass

                def reply(self, history):
                    return SimpleNamespace(
                        reply="谢谢你告诉我。最近发生过哪一件让你困扰的事？",
                        completion=None,
                    )

            with patch("cbt_course_llm_freeform.runtime.FreeformCourseAgent", FakeFreeformAgent):
                mood = client.post(
                    f"/api/cbt-course/conversations/{conversation_id}/messages",
                    json={"content": "我觉得上周大概六分", "idempotency_key": "api-course-mood-001"},
                    headers=headers,
                )
            self.assertEqual(mood.status_code, 200)
            self.assertEqual(mood.json()["course"]["current_step"], "freeform")
            restored = client.get(f"/api/cbt-course/conversations/{conversation_id}").json()
            self.assertEqual(len(restored["messages"]), 3)
            self.assertEqual(restored["course"]["current_step"], "freeform")
            redirected = client.get(f"/conversations/{conversation_id}")
            self.assertEqual(redirected.status_code, 200)
            self.assertIn("/cbt-course/conversations/", str(redirected.url))

            daily_created = client.post("/api/conversations", json={"mode": "daily_chat"}, headers=headers)
            self.assertEqual(daily_created.status_code, 200)
            daily_conversation_id = daily_created.json()["id"]
            client.post(f"/api/conversations/{daily_conversation_id}/end", json={}, headers=headers)
            self.assertIn(f"/cbt-course/conversations/{conversation_id}", client.get("/app").text)

            admin_login = client.post("/api/admin/login", json={"password": "test-admin-password"})
            self.assertEqual(admin_login.status_code, 200)
            admin_list = client.get("/admin")
            self.assertEqual(admin_list.status_code, 200)
            self.assertIn("实验会话数据", admin_list.text)
            self.assertIn("导出全部已结束会话 JSON", admin_list.text)
            self.assertIn('formaction="/admin/exports/bulk/ended.json"', admin_list.text)
            self.assertIn("导出对话 JSON", admin_list.text)
            self.assertIn(
                'formaction="/admin/exports/bulk/ended-dialogues.json"',
                admin_list.text,
            )
            admin_detail = client.get(f"/admin/conversations/{conversation_id}")
            self.assertEqual(admin_detail.status_code, 200)
            self.assertIn("运行审计", admin_detail.text)
            self.assertIn("课程 lesson-1", admin_detail.text)
            json_export = client.get(f"/admin/exports/{conversation_id}.json")
            self.assertEqual(json_export.status_code, 200)
            self.assertEqual(len(json_export.json()), 3)
            self.assertIn("dialogue-history-", json_export.headers["content-disposition"])
            full_json_export = client.get(f"/admin/exports/{conversation_id}/full.json")
            self.assertEqual(full_json_export.status_code, 200)
            self.assertEqual(full_json_export.json()["lesson_id"], "lesson-1")
            self.assertEqual(full_json_export.json()["messages"][0]["attachment"]["kind"], "image")
            self.assertEqual(full_json_export.json()["course_homework_entries"], [])
            self.assertTrue(full_json_export.json()["agent_prompt_hash"])
            csv_export = client.get(f"/admin/exports/{conversation_id}.csv")
            self.assertEqual(csv_export.status_code, 200)
            self.assertIn("conversation_id", csv_export.text)
            self.assertIn("agent_version", csv_export.text)
            self.assertIn("turn_agent_version", csv_export.text)
            self.assertIn("lesson_id", csv_export.text)
            self.assertIn("lesson-1", csv_export.text)
            daily_dialogue_json_export = client.get(
                "/admin/exports/bulk/ended-dialogues.json",
                params={
                    "mode": "daily_chat",
                    "agent_version": daily_created.json()["agent_version"],
                },
            )
            self.assertEqual(daily_dialogue_json_export.status_code, 200)
            self.assertEqual(
                daily_dialogue_json_export.json(),
                [{"history_dialogue_daily_chat": []}],
            )

            admin_headers = {"X-CSRF-Token": client.cookies.get("csrf_token")}
            deleted = client.delete(f"/api/admin/conversations/{conversation_id}", headers=admin_headers)
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(client.get(f"/admin/conversations/{conversation_id}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
