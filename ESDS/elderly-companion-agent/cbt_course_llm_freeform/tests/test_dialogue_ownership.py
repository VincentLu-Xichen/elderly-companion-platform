"""User-visible dialogue choices and their persisted teaching consequences."""

import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform import blueprint, dialogue, learning_check
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, next_question
from cbt_course_llm_freeform.schemas import TeachingDecision
from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn
from cbt_course_llm_freeform.tests.test_blueprint import ready_state
from daily_agent.azure_chat_client import ChatCompletionResult
from scripts.run_a1_style_eval import fixture
from webapp.database import Base
from webapp.models import Conversation, Message, Participant
from webapp.security import decrypt_json, encrypt_json, encrypt_text, hash_secret


class DialogueClient:
    def __init__(self, kind="concept_question", reply="这两部分可以慢慢分清。", *, fields=None,
                 quote=None, source=None, extra=None, attempted_field=None):
        self.kind, self.reply = kind, reply
        self.fields, self.quote, self.source = fields or {}, quote, source
        self.extra, self.calls = extra or {}, []
        self.attempted_field = attempted_field

    def complete_with_metadata(self, messages, **parameters):
        self.calls.append((copy.deepcopy(messages), parameters))
        if "COURSE_CASE_REVIEW" in messages[0]["content"]:
            fields = json.loads(messages[1]["content"])["data"]["fields"]
            output = dict(summary="这次您提到：" + "；".join(item["value"] for item in fields.values()) + "。",
                          source_message_ids=list(dict.fromkeys(item["source_message_id"] for item in fields.values())))
            return ChatCompletionResult(text=json.dumps(output, ensure_ascii=False), model="scripted", finish_reason="stop")
        latest = json.loads(messages[-1]["content"])
        if messages[0]["content"].startswith("你是课程互动反馈"):
            output = dict(verdict="not_feedback", source_message_id=latest["id"], quote=latest["text"],
                          observation="合成本轮判读", hypothesis="待核对", alternative_explanation="待核对",
                          scope="lesson", reply_length="standard", follow_up="standard", reply="继续判读本轮诉求。",
                          personal_intent="none", task_action="continue")
            return ChatCompletionResult(text=json.dumps(output, ensure_ascii=False), model="scripted", finish_reason="stop")
        output = dict(reply=self.reply,
                      turn_intent=dict(kind=self.kind, source_message_id=self.source or latest["id"],
                                       quote=self.quote if self.quote is not None else latest["text"],
                                       attempted_field=self.attempted_field),
                      observations=[dict(field=k, value=v, source_message_id=latest["id"])
                                    for k, v in self.fields.items()], **self.extra)
        return ChatCompletionResult(text=json.dumps(output, ensure_ascii=False), model="scripted",
                                    finish_reason="stop")


def starting():
    return fixture(dict(id="DIALOGUE-031", lesson="lesson-1", fixture="first-belief-rating"))


def turn(state, text, client, history=None):
    history = copy.deepcopy(history or [])
    history.append(dict(id=uuid.uuid4().hex, role="learner", content=text))
    result = FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)).process(state, history)
    history.append(dict(id=uuid.uuid4().hex, role="agent", content=result.reply))
    return result, history


class DialogueOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.state, self.history = starting()

    def detour(self):
        return turn(self.state, "我现在还很难受，想先说一会儿。",
                    DialogueClient("conversation", "嗯，可以慢慢说。"), self.history)

    def test_teaching_receives_facts_not_a_prebuilt_next_question(self):
        client = DialogueClient()
        result, _ = turn(self.state, "为什么想法和事情要分开？", client, self.history)
        context = json.loads(client.calls[0][0][1]["content"])["data"]
        self.assertNotIn("next_question", context)
        task = context["pending_task"]
        self.assertEqual(task["pending_fields"], ["thought_belief", "emotion_intensity"])
        self.assertFalse(task["question_required"])
        self.assertEqual(task["rating_target"]["value"], self.state["draft_record"]["thought"]["value"])
        self.assertEqual(task["scale"], dict(minimum=0, maximum=10, meaning="相信程度", optional=True))
        self.assertEqual(result.reply, client.reply)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("多相信", next_question(self.state))  # Existing task/button renderer remains.

    def test_multiple_concept_questions_do_not_consume_attempts_or_mark_fields_deferred(self):
        state, history = copy.deepcopy(self.state), self.history
        for text in ("事实和想法怎么分？", "为什么要这样分开？", "解释和感受有什么区别？"):
            result, history = turn(state, text, DialogueClient(), history)
            state = result.state
            self.assertEqual(state["practice_flow"], self.state["practice_flow"])
            self.assertEqual(state["stage"], "practice")
            self.assertEqual(state["draft_record"], self.state["draft_record"])
            self.assertFalse(result.trace["trigger"]["triggered"])
            self.assertEqual(result.trace["trigger"]["observed_events"], [])

    def test_validated_old_confusion_json_is_replayed_as_help_without_an_extra_call(self):
        class OldClient:
            def complete_with_metadata(self, messages, **parameters):
                latest = json.loads(messages[-1]["content"])
                output = dict(reply="我们先解释区别。", observations=[], assessment=dict(signals=[
                    dict(kind="confusion", quote=latest["text"], source_message_id=latest["id"])]))
                return ChatCompletionResult(text=json.dumps(output, ensure_ascii=False), finish_reason="stop")
        result, _ = turn(self.state, "为什么要分开？", OldClient(), self.history)
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})
        self.assertEqual(result.trace["teaching_turn"]["origin"], "legacy_signal")
        self.assertEqual([c["phase"] for c in result.trace["model_calls"]], ["teaching"])

    def test_help_does_not_consume_attempts_while_selecting_a_case(self):
        state = copy.deepcopy(self.state)
        state.update(stage="learn", draft_record={})
        result, _ = turn(state, "什么样的事情能拿来练习？", DialogueClient())
        self.assertEqual(result.state["stage"], "learn")
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})
        self.assertEqual(result.state["teacher_flow"]["cards"], state["teacher_flow"]["cards"])

    def test_actual_failed_answers_still_have_the_existing_bounded_exit(self):
        first, history = turn(self.state, "不知道", DialogueClient("answer", attempted_field="thought_belief"), self.history)
        self.assertEqual(len(first.state["practice_flow"]["unanswered"]["thought_belief"]), 1)
        second, _ = turn(first.state, "还是想不起", DialogueClient("answer", attempted_field="thought_belief"), history)
        self.assertEqual(second.state["practice_flow"]["deferred"]["thought_belief"]["status"], "not_observed")
        self.assertNotIn("emotion_intensity", second.state["practice_flow"]["deferred"])

    def test_current_pending_field_is_not_automatically_an_attempted_question(self):
        result, _ = turn(self.state, "我想先说想法这一部分。", DialogueClient("answer"), self.history)
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})
        client = DialogueClient("answer", fields=dict(behavior="后来继续散步"), attempted_field="behavior")
        result, _ = turn(self.state, "后来继续散步。", client, self.history)
        self.assertEqual(result.state["draft_record"]["behavior"]["value"], "后来继续散步")
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})

    def test_completed_records_can_progress_without_a_new_answer_attempt(self):
        state = ready_state()
        state["stage"] = "practice"
        result, _ = turn(state, "我们回看刚才已经整理好的内容吧。", DialogueClient("answer", "好，我们一起回看。"))
        self.assertEqual(result.state["stage"], "review")
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})
        self.assertIsNone(result.state["confirmed_record"])
        self.assertEqual(result.reply, "好，我们一起回看。")
        result, _ = turn(state, "想法和情绪的联系我还没明白。", DialogueClient("concept_question", "我们先看两者的联系。"))
        self.assertEqual(result.state["stage"], "practice")
        self.assertIsNone(result.state["confirmed_record"])

    def test_non_answer_cannot_claim_it_attempted_a_rating(self):
        with self.assertRaises(ValueError):
            turn(self.state, "相信程度是什么意思？", DialogueClient("concept_question", attempted_field="thought_belief"), self.history)

    def test_short_and_long_replies_are_preserved_without_an_appended_question(self):
        for reply in ("嗯。", "可以慢慢说。", "这件事的具体经过和我们对它的解释可以分开看。" * 8):
            result, _ = turn(self.state, "我还想聊一会儿。", DialogueClient("conversation", reply), self.history)
            self.assertEqual(result.reply, reply)
            self.assertEqual(result.state["practice_flow"], self.state["practice_flow"])
            self.assertEqual(result.state["classroom_dialogue"]["mode"], "conversation")

    def test_another_topic_stays_in_the_conversation_not_the_old_case(self):
        result, _ = turn(self.state, "今天室友外放视频让我很烦。",
                         DialogueClient("conversation", extra=dict(practice_origin="different_case")), self.history)
        self.assertEqual(result.state["draft_record"], self.state["draft_record"])
        self.assertEqual(result.state["case_id"], self.state["case_id"])

    def test_source_and_non_answer_record_combinations_are_atomic(self):
        for client in (DialogueClient(source="another-user"), DialogueClient(quote="不存在的原话"),
                       DialogueClient(fields=dict(emotion="很难受")),
                       DialogueClient(extra=dict(advance=True)),
                       DialogueClient(extra=dict(case_options=["很难受"]))):
            before = copy.deepcopy(self.state)
            with self.assertRaises((ValueError, RuntimeError)):
                turn(self.state, "现在很难受。", client, self.history)
            self.assertEqual(self.state, before)

    def test_another_case_cannot_be_written_even_with_a_faithful_quote(self):
        with self.assertRaisesRegex(ValueError, "Another event"):
            turn(self.state, "室友在外放视频", DialogueClient("answer", fields=dict(situation="室友在外放视频"),
                 extra=dict(practice_origin="different_case")), self.history)

    def test_return_invitation_can_occur_before_ten_turns_without_resuming(self):
        detour, history = self.detour()
        invited, _ = turn(detour.state, "说出来以后好多了，想说的也差不多了。",
                          DialogueClient("invite_return", "我们可以接着看刚才的练习，您愿意吗？"), history)
        flow = invited.state["classroom_dialogue"]
        self.assertEqual(flow["mode"], "conversation")
        self.assertEqual(flow["invitation"]["status"], "pending")
        self.assertEqual(flow["return_to"], dict(stage="practice", case_id=self.state["case_id"]))
        self.assertEqual(invited.state["practice_flow"], self.state["practice_flow"])
        self.assertLess(invited.state["turn_count"], 10)
        self.assertFalse(invited.state["completed"])

    def invited(self):
        detour, history = self.detour()
        return turn(detour.state, "现在好一些了。", DialogueClient("invite_return", "愿意接着练习吗？"), history)

    def test_pending_invitation_cannot_be_repeated_without_an_answer(self):
        invited, history = self.invited()
        before = copy.deepcopy(invited.state)
        with self.assertRaisesRegex(ValueError, "already awaiting"):
            turn(invited.state, "我再想想。", DialogueClient("invite_return", "再问一次，愿意吗？"), history)
        self.assertEqual(invited.state, before)

    def test_declining_invitation_keeps_talking_and_preserves_the_lesson(self):
        invited, history = self.invited()
        declined, history = turn(invited.state, "我还想先聊一会儿。", DialogueClient("decline_return", "好，先听您说。"), history)
        self.assertEqual(declined.state["classroom_dialogue"]["invitation"]["status"], "declined")
        result, _ = turn(declined.state, "今天回去之后又想到这件事。", DialogueClient("conversation", "嗯，这件事还牵挂着您。"), history)
        self.assertEqual(result.state["classroom_dialogue"]["mode"], "conversation")
        self.assertEqual(result.state["draft_record"], self.state["draft_record"])
        self.assertEqual(result.state["practice_flow"], self.state["practice_flow"])

    def test_explicit_consent_resumes_while_feelings_can_remain(self):
        invited, history = self.invited()
        result, _ = turn(invited.state, "我还是难过，但想继续刚才的练习。", DialogueClient("resume_course"), history)
        self.assertEqual(result.state["classroom_dialogue"]["mode"], "course")
        self.assertIsNone(result.state["classroom_dialogue"]["return_to"])
        self.assertEqual(result.state["classroom_dialogue"]["invitation"]["status"], "accepted")
        self.assertEqual(result.state["practice_flow"], self.state["practice_flow"])

    def test_short_consent_only_works_in_an_actual_invitation_context(self):
        invited, history = self.invited()
        result, _ = turn(invited.state, "好的。", DialogueClient("resume_course"), history)
        self.assertEqual(result.state["classroom_dialogue"]["mode"], "course")
        detour, history = self.detour()
        with self.assertRaisesRegex(ValueError, "Feeling better"):
            turn(detour.state, "好的。", DialogueClient("resume_course"), history)

    def test_model_inferred_improvement_negation_and_reports_are_not_consent(self):
        for text, quote in (("好多了。", None), ("我不想继续课程。", None),
                            ("我不想继续课程。", "继续课程"),
                            ("朋友说继续课程。", "继续课程")):
            invited, history = self.invited()
            before = copy.deepcopy(invited.state)
            with self.assertRaises(ValueError):
                turn(invited.state, text, DialogueClient("resume_course", quote=quote), history)
            self.assertEqual(invited.state, before)

    def test_spontaneous_return_and_new_zero_rating_share_one_call(self):
        detour, history = self.detour()
        client = DialogueClient("resume_course", "好，照您的意思继续。", fields=dict(thought_belief="相信程度0分"))
        result, _ = turn(detour.state, "我想继续练习，这条想法相信程度0分。", client, history)
        self.assertEqual(result.state["blueprint"]["ratings"]["thought_belief"]["value"], 0)
        self.assertEqual(result.state["classroom_dialogue"]["mode"], "course")
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})
        self.assertEqual(len(client.calls), 1)

    def test_direct_sourced_answer_can_express_willingness_to_resume(self):
        detour, history = self.detour()
        client = DialogueClient("resume_course", "好，按您给的分数整理。", fields=dict(thought_belief="相信程度0分"),
                                attempted_field="thought_belief")
        result, _ = turn(detour.state, "相信程度0分。", client, history)
        self.assertEqual(result.state["classroom_dialogue"]["mode"], "course")
        self.assertEqual(result.state["blueprint"]["ratings"]["thought_belief"]["value"], 0)
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})

    def test_case_changes_invalidate_the_old_return_point(self):
        invited, history = self.invited()
        invited.state["case_id"] = "a-different-case"
        with self.assertRaisesRegex(ValueError, "return point"):
            turn(invited.state, "我愿意继续课程。", DialogueClient("resume_course"), history)

    def test_explicit_control_clears_a_stale_invitation(self):
        invited, history = self.invited()
        result = FreeformCourseRuntime().process(invited.state, history, action="pause")
        resumed = FreeformCourseRuntime().process(result.state, history, action="resume")
        self.assertEqual(resumed.state["classroom_dialogue"]["mode"], "course")
        self.assertIsNone(resumed.state["classroom_dialogue"]["invitation"])

    def test_navigation_uses_model_words_while_program_executes_the_action(self):
        class NavigationClient:
            def complete_with_metadata(self, messages, **kwargs):
                latest = json.loads(messages[-1]["content"])
                out = dict(intent="actions", reply="好，这次先不安排课后练习，我们回看今天的内容。",
                           actions=[dict(action="decline_practice", source_message_id=latest["id"], quote=latest["text"])])
                return ChatCompletionResult(text=json.dumps(out, ensure_ascii=False), finish_reason="stop")
        state = ready_state()
        state["stage"] = "plan"
        result, _ = turn(state, "这次先不安排课后练习。", NavigationClient())
        self.assertEqual(result.reply, "好，这次先不安排课后练习，我们回看今天的内容。")
        self.assertEqual(result.state["stage"], "summary")
        self.assertEqual(result.state["practice_plan"]["status"], "declined")

    def test_learning_check_preserves_model_feedback_before_the_next_task_material(self):
        class CheckClient:
            def complete_with_metadata(self, messages, **kwargs):
                latest = json.loads(messages[-1]["content"])
                out = dict(verdict="matches", reason="对应本题的事件", source_message_id=latest["id"],
                           reply="您抓住了材料里实际发生的事，这正是情境。")
                return ChatCompletionResult(text=json.dumps(out, ensure_ascii=False), finish_reason="stop")
        state = ready_state()
        learning_check.begin(state)
        result, _ = turn(state, "别人和我打招呼", CheckClient())
        self.assertTrue(result.reply.startswith("您抓住了材料里实际发生的事，这正是情境。\n"))
        self.assertEqual(result.state["learning_check"]["index"], 1)
        self.assertEqual(result.state["learning_check"]["answers"][0]["verdict"], "matches")

    def test_prompt_has_adaptive_length_and_no_fixed_return_round_threshold(self):
        prompt = prompt_for_lesson("lesson-1")
        self.assertNotIn("约30—80", prompt)
        self.assertNotIn("practice每轮沿学习者的话只补问", prompt)
        self.assertIn("不要求每轮推进课程", prompt)
        self.assertIn("无需等10轮或20轮", prompt)
        self.assertIn("简单陪伴回应可以结束一轮", prompt)
        self.assertIn("不是要求你学习开发设计文档", prompt)

    def test_dialogue_and_return_are_preserved_in_later_lesson_phases(self):
        class PhaseClient:
            def __init__(self, kind, reply):
                self.kind, self.reply = kind, reply

            def complete_with_metadata(self, messages, **kwargs):
                latest = json.loads(messages[-1]["content"])
                action = dict(kind=self.kind, source_message_id=latest["id"], quote=latest["text"])
                if "COURSE_NAVIGATION" in messages[0]["content"]:
                    out = dict(intent="clarify", actions=[], reply=self.reply, turn_intent=action)
                else:
                    out = dict(verdict="not_answer", reason="本轮在交流而非作答", source_message_id=latest["id"],
                               reply=self.reply, turn_intent=action)
                return ChatCompletionResult(text=json.dumps(out, ensure_ascii=False), finish_reason="stop")

        for phase in ("assessment", "check_feedback", "learning_goal", "plan", "summary"):
            with self.subTest(phase=phase):
                state = ready_state()
                if phase == "assessment":
                    learning_check.begin(state)
                else:
                    state["stage"] = phase
                original_check = copy.deepcopy(state["learning_check"])
                original_record = copy.deepcopy(state["draft_record"])
                detour, history = turn(state, "又想到一件伤心事，我还想说一会儿。", PhaseClient("conversation", "嗯，可以慢慢说。"))
                self.assertEqual(detour.reply, "嗯，可以慢慢说。")
                self.assertEqual(detour.state["stage"], phase)
                invited, history = turn(detour.state, "想说的差不多了。", PhaseClient("invite_return", "愿意接着看刚才那一步吗？"), history)
                self.assertEqual(invited.state["classroom_dialogue"]["mode"], "conversation")
                resumed, _ = turn(invited.state, "我愿意继续刚才的学习。", PhaseClient("resume_course", "我们按您愿意的节奏接着看。"), history)
                self.assertEqual(resumed.state["classroom_dialogue"]["mode"], "course")
                self.assertEqual(resumed.state["stage"], phase)
                self.assertEqual(resumed.state["learning_check"], original_check)
                self.assertEqual(resumed.state["draft_record"], original_record)
                self.assertFalse(resumed.state["completed"])

    def test_second_lesson_check_keeps_its_existing_contract(self):
        class Client:
            def complete_with_metadata(self, messages, **kwargs):
                self.prompt = messages[0]["content"]
                return ChatCompletionResult(text='{"verdict":"matches","reason":"对应想法","source_message_id":"u"}', finish_reason="stop")
        client = Client()
        result = FreeformCourseAgent(client=client).evaluate_answer(
            [dict(id="u", role="learner", content="想法")], context=dict(lesson2_review=True))
        self.assertEqual(result.decision.verdict, "matches")
        self.assertNotIn("第一课的优先交流规则", client.prompt)
        schema = json.loads(client.prompt.split("\nJSON输出契约：\n", 1)[1])
        self.assertNotIn("turn_intent", schema["properties"])
        self.assertNotIn("reply", schema["properties"])

    def test_existing_per_turn_reflection_uses_the_same_dialogue_context(self):
        class ReflectedClient(DialogueClient):
            def complete_with_metadata(self, messages, **kwargs):
                prompt = messages[0]["content"]
                if "COURSE_GUIDANCE_REFLECTION" in prompt:
                    self.calls.append((copy.deepcopy(messages), kwargs))
                    latest = json.loads(messages[-1]["content"])
                    out = dict(reflection=dict(update="replace", brief="本轮需要先听表达。", strategy="continue_current",
                        focus_field=None, source_message_ids=[latest["id"]], open_items=[], previous_strategy_result="unknown"))
                elif "COURSE_GUIDANCE_ACTOR" in prompt:
                    self.calls.append((copy.deepcopy(messages), kwargs))
                    self.actor_context = json.loads(messages[1]["content"])["data"]
                    out = dict(reply="嗯，我们先停在这里听您说。")
                else:
                    return super().complete_with_metadata(messages, **kwargs)
                return ChatCompletionResult(text=json.dumps(out, ensure_ascii=False), finish_reason="stop")
        state = copy.deepcopy(self.state)
        state["workflow"]["policy"] = "per_turn"
        client = ReflectedClient("conversation")
        result, _ = turn(state, "又想到些难过的事，想说一会儿。", client, self.history)
        self.assertEqual([c["phase"] for c in result.trace["model_calls"]], ["teaching", "guidance_reflection", "guidance_actor"])
        self.assertEqual(result.reply, "嗯，我们先停在这里听您说。")
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})
        self.assertNotIn("next_question", client.actor_context)
        self.assertEqual(client.actor_context["current_teaching_turn"]["kind"], "conversation")
        self.assertEqual(client.actor_context["classroom_dialogue"]["mode"], "conversation")


class DialoguePersistenceTests(unittest.TestCase):
    def test_invitation_survives_restart_is_encrypted_and_retry_is_idempotent(self):
        client = DialogueClient("invite_return", "愿意接着看刚才的练习吗？")
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///" + str(Path(directory) / "dialogue.db"))
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine)
            state, history = starting()
            dialogue.enter_listening(state, history[0])
            with factory() as db:
                person = Participant(label="031-synthetic", invite_hash=hash_secret("test"))
                db.add(person); db.commit()
                course = create_or_resume_course(db, participant_id=person.id, lesson_id="lesson-1")[0]
                course.agent_state_encrypted = encrypt_json(state)
                for sequence, item in enumerate(history, start=2):
                    db.add(Message(id=item["id"], conversation_id=course.id, role=item["role"],
                                   sequence=sequence, content_encrypted=encrypt_text(item["content"])))
                db.commit()
                kwargs = dict(content="我想说的差不多了。", idempotency_key="031-invitation-same-key",
                              runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)))
                process_course_turn(db, course, **kwargs)
                repeated = process_course_turn(db, course, **kwargs)
                self.assertTrue(repeated["deduplicated"])
                self.assertEqual(len(client.calls), 1)
                self.assertNotIn("差不多", course.agent_state_encrypted)
                cid = course.id
            engine.dispose()
            with factory() as db:
                course = db.get(Conversation, cid)
                saved = decrypt_json(course.agent_state_encrypted)
                self.assertEqual(saved["classroom_dialogue"]["mode"], "conversation")
                self.assertEqual(saved["classroom_dialogue"]["invitation"]["status"], "pending")
                self.assertEqual(saved["classroom_dialogue"]["return_to"], dict(stage="practice", case_id=state["case_id"]))
                self.assertEqual(saved["draft_record"], state["draft_record"])
                next_client = DialogueClient("resume_course", "我们按您愿意的节奏接着看。")
                process_course_turn(db, course, content="我愿意继续刚才的学习。", idempotency_key="031-resume-sourced-key",
                    runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=next_client)))
                resumed = decrypt_json(course.agent_state_encrypted)
                self.assertEqual(resumed["classroom_dialogue"]["mode"], "course")
                self.assertEqual(resumed["draft_record"], state["draft_record"])
                self.assertEqual(resumed["practice_flow"]["unanswered"], {})
            engine.dispose()
