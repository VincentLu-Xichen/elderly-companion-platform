from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webapp.database import Base
from webapp.models import Conversation, Consent, Participant
from webapp.voice_bridge import (
    CbtVoiceSessionOpen,
    CbtVoiceTurnCreate,
    VoiceSessionOpen,
    VoiceTurnCreate,
    create_cbt_voice_turn,
    create_voice_turn,
    open_cbt_voice_session,
    open_voice_session,
    require_voice_bridge,
)


class VoiceBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.settings = SimpleNamespace(
            voice_bridge_enabled=True,
            voice_bridge_token="voice-test-token",
            voice_device_id="esds-pi-test",
            voice_participant_label="voice-user-test",
            voice_consent_acknowledged=True,
            max_message_chars=2000,
        )

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_authentication_rejects_wrong_token(self) -> None:
        with patch("webapp.voice_bridge.settings", self.settings):
            with self.assertRaises(HTTPException) as raised:
                require_voice_bridge("Bearer wrong")
        self.assertEqual(raised.exception.status_code, 401)

    def test_open_creates_consent_and_resumes_daily_conversation(self) -> None:
        request = VoiceSessionOpen(device_id="esds-pi-test")
        with patch("webapp.voice_bridge.settings", self.settings):
            first = open_voice_session(request, self.db)
            second = open_voice_session(request, self.db)

        self.assertFalse(first["resumed"])
        self.assertTrue(second["resumed"])
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        self.assertEqual(self.db.query(Participant).count(), 1)
        self.assertEqual(self.db.query(Consent).count(), 1)
        self.assertEqual(self.db.query(Conversation).count(), 1)

    def test_turn_uses_persistent_conversation_service(self) -> None:
        with patch("webapp.voice_bridge.settings", self.settings):
            opened = open_voice_session(
                VoiceSessionOpen(device_id="esds-pi-test"), self.db
            )
            with patch(
                "webapp.voice_bridge.process_turn",
                return_value={
                    "reply": "那挺好啊，聊了些什么？",
                    "status": "success",
                    "trace": {},
                    "safety_event": None,
                    "deduplicated": False,
                },
            ) as process:
                result = create_voice_turn(
                    str(opened["conversation_id"]),
                    VoiceTurnCreate(
                        transcript="孩子给我打电话了。",
                        idempotency_key="voice-idempotency-001",
                    ),
                    self.db,
                )

        self.assertEqual(result["reply"], "那挺好啊，聊了些什么？")
        self.assertEqual(result["mode"], "daily_chat")
        self.assertEqual(
            process.call_args.kwargs["content"], "孩子给我打电话了。"
        )

    def test_cbt_voice_session_and_turn_use_course_service(self) -> None:
        request = CbtVoiceSessionOpen(device_id="esds-pi-test")
        with patch("webapp.voice_bridge.settings", self.settings):
            opened = open_cbt_voice_session(request, self.db)
            with patch(
                "webapp.voice_bridge.process_course_turn",
                return_value={
                    "reply": "我们继续做一个小练习。",
                    "attachment": {},
                    "status": "success",
                    "safety_event": None,
                    "deduplicated": False,
                    "course": {"completed": False},
                },
            ) as process:
                result = create_cbt_voice_turn(
                    str(opened["conversation_id"]),
                    CbtVoiceTurnCreate(
                        transcript="我最近心情大概三分。",
                        idempotency_key="cbt-voice-idempotency-001",
                    ),
                    self.db,
                )

        self.assertEqual(opened["mode"], "cbt")
        self.assertEqual(opened["lesson_id"], "lesson-1")
        self.assertEqual(result["mode"], "cbt")
        self.assertFalse(result["completed"])
        self.assertEqual(process.call_args.kwargs["content"], "我最近心情大概三分。")


if __name__ == "__main__":
    unittest.main()
