import copy
import json
import unittest
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state, course_payload
from cbt_course_llm_freeform import boundaries
from cbt_course_llm_freeform.tests.test_learning_check import prepared, step
from daily_agent.azure_chat_client import ChatCompletionResult


def goal_state():
    state = prepared()
    for _ in range(4):
        state = step(state, action="skip_check_question").state
    return step(state, action="continue_after_check").state


class NavigationClient:
    def __init__(self, intent="actions", actions=(), fail=False, bad_source=False):
        self.intent, self.actions, self.fail, self.bad_source = intent, actions, fail, bad_source

    def complete_with_metadata(self, messages, **kwargs):
        if self.fail:
            raise TimeoutError("synthetic timeout")
        self.prompt = messages[0]["content"]
        latest = json.loads(messages[-1]["content"])
        data = {"intent": self.intent, "reply": "您是想确认已有目标，还是暂不设置目标继续？" if self.intent == "clarify" else "",
            "actions": [{"action": action, "source_message_id": "wrong" if self.bad_source else latest["id"], "quote": latest["text"]} for action in self.actions]}
        return ChatCompletionResult(text=json.dumps(data, ensure_ascii=False), model="navigation-test", finish_reason="stop")


def navigate(state, text, client):
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)).process(state, [{"id": "latest", "role": "learner", "content": text}])


class NavigationTests(unittest.TestCase):
    def test_two_explicit_choices_advance_atomically_to_summary(self):
        state = goal_state()
        result = navigate(state, "目标先不设，也不安排课后练习，直接总结吧", NavigationClient(actions=["skip_learning_goal", "decline_practice"]))
        self.assertEqual(result.state["stage"], "summary")
        self.assertEqual(result.state["learning_goal"]["status"], "skipped")
        self.assertEqual(result.state["practice_plan"]["status"], "declined")
        self.assertFalse(result.state["completed"])
        self.assertEqual(len(result.trace["model_calls"]), 1)
        self.assertEqual(state["stage"], "learning_goal")

    def test_ambiguous_done_is_not_a_goal_or_confirmation(self):
        for draft in (False, True):
            state = goal_state()
            if draft:
                state["learning_goal_draft"] = {"value": "分清事实和猜测", "source_message_id": "old"}
            result = navigate(state, "我觉得已经完成了", NavigationClient(intent="clarify"))
            self.assertEqual(result.state["stage"], "learning_goal")
            self.assertNotIn("learning_goal", result.state)
            self.assertEqual(result.state.get("learning_goal_draft"), state.get("learning_goal_draft"))

    def test_two_positive_choices_do_not_get_negative_confirmation_text(self):
        state = goal_state()
        state["learning_goal_draft"] = {"value": "分清事实和猜测", "source_message_id": "draft"}
        result = navigate(state, "就按这个目标，也愿意做课后练习", NavigationClient(actions=["confirm_learning_goal", "accept_practice"]))
        self.assertEqual(result.state["learning_goal"]["status"], "confirmed")
        self.assertEqual(result.state["practice_plan"]["status"], "accepted")
        self.assertNotIn("不安排", result.reply)
        self.assertNotIn("不设置", result.reply)

    def test_goal_still_requires_separate_confirmation_and_plan_choice(self):
        state = navigate(goal_state(), "我希望分清事实和猜测", NavigationClient(intent="goal")).state
        self.assertEqual(state["learning_goal_draft"]["value"], "我希望分清事实和猜测")
        state = navigate(state, "对，就按这个目标", NavigationClient(actions=["confirm_learning_goal"])).state
        self.assertEqual(state["learning_goal"]["confirmation_message_id"], "latest")
        self.assertEqual(state["stage"], "plan")
        state = navigate(state, "这次不安排课后练习", NavigationClient(actions=["decline_practice"])).state
        result = navigate(state, "结束本课吧", NavigationClient(actions=["finish"]))
        self.assertTrue(result.state["completed"])
        self.assertEqual(result.state["reflection"]["status"], "pending")

    def test_invalid_second_action_and_evidence_do_not_partially_apply(self):
        for client in (NavigationClient(actions=["skip_learning_goal", "finish"]),
                       NavigationClient(actions=["confirm_learning_goal"]),
                       NavigationClient(actions=["skip_learning_goal"], bad_source=True)):
            state = goal_state()
            result = navigate(state, "继续吧", client)
            self.assertEqual(result.state["stage"], "learning_goal")
            self.assertNotIn("learning_goal", result.state)
            self.assertEqual(result.trace["navigation_event"]["status"], "failed")

    def test_failed_model_preserves_progress_and_audits_call(self):
        result = navigate(goal_state(), "继续吧", NavigationClient(fail=True))
        self.assertEqual(result.state["stage"], "learning_goal")
        self.assertEqual(result.trace["navigation_event"]["status"], "failed")
        self.assertEqual(result.trace["model_calls"][0]["status"], "error")

    def test_navigation_persists_and_same_key_retry_does_not_run_again(self):
        from cbt_course_llm_freeform.tests.test_personal_boundary import BoundaryPersistenceTests
        from cbt_course_llm_freeform.services import process_course_turn
        from webapp.security import encrypt_json, decrypt_json
        fixture = BoundaryPersistenceTests()
        fixture.setUp()
        try:
            state = goal_state()
            state["conversation_id"] = fixture.course.id
            fixture.course.agent_state_encrypted = encrypt_json(state)
            fixture.db.commit()
            client = NavigationClient(actions=["skip_learning_goal", "decline_practice"])
            def factory():
                return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client))
            args = dict(content="目标不设，也不安排课后练习", idempotency_key="navigation-same-key", runtime_factory=factory)
            first = process_course_turn(fixture.db, fixture.course, **args)
            second = process_course_turn(fixture.db, fixture.course, **args)
            self.assertTrue(second["deduplicated"])
            self.assertEqual(first["reply"], second["reply"])
            fixture.db.expire_all()
            self.assertEqual(decrypt_json(fixture.course.agent_state_encrypted)["stage"], "summary")
        finally:
            fixture.tearDown()

    def test_fictional_and_personal_defer_have_clear_next_field_and_source(self):
        for fictional in (False, True):
            state = new_course_state("lesson-1", reflection_policy="none")
            state["stage"] = "practice"
            if fictional:
                boundaries.switch(state, "fictional")
            result = step(state, action="defer_practice_field")
            self.assertIn("接下来看看", result.reply)
            self.assertIn("想法", result.reply)
            self.assertEqual(course_payload(result.state)["personal_practice"]["current_field"], "thought")
            label = course_payload(result.state)["personal_practice"]["deferred"][0]["status_label"]
            self.assertEqual("辨认" in label, fictional)
            if fictional:
                self.assertNotIn("脑中", result.reply)
                self.assertEqual(course_payload(result.state)["practice_control_labels"]["defer_practice_field"], "这一项还分不清")
