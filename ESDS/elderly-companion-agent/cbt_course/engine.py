from __future__ import annotations

import copy
import re
from typing import Any

from cbt_course.agent import CourseTutorAgent
from cbt_course.catalog import LESSON_1_ID, LESSON_1_VERSION, course_by_id, require_available_course
from cbt_course.lesson_1 import MODEL_STEP_RULES, STATIC_ATTACHMENTS, STEP_ORDER, STEP_PHASE
from cbt_course.schemas import CourseAgentResult, CourseTurnResult


def new_course_state(lesson_id: str) -> dict[str, Any]:
    require_available_course(lesson_id)
    if lesson_id != LESSON_1_ID:
        raise ValueError("这节课尚未接入学习流程。")
    return {
        "lesson_id": LESSON_1_ID,
        "lesson_version": LESSON_1_VERSION,
        "step": "mood",
        "answers": {},
        "quiz_results": {},
        "completed": False,
        "diary_draft": {},
    }


def course_payload(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {}
    step = str(state.get("step", "mood"))
    completed = bool(state.get("completed"))
    if completed:
        progress = 100
    elif step in STEP_ORDER:
        progress = round(STEP_ORDER.index(step) / (len(STEP_ORDER) - 1) * 100)
    else:
        progress = 100
    answers = dict(state.get("answers") or {})
    return {
        "lesson": course_by_id(str(state.get("lesson_id"))) or course_by_id(LESSON_1_ID),
        "lesson_version": state.get("lesson_version"),
        "current_step": step,
        "phase": STEP_PHASE.get(step, "课程学习"),
        "progress_percent": progress,
        "completed": completed,
        "formulation": {
            "situation": answers.get("situation", ""),
            "thought": answers.get("thought", ""),
            "thought_belief": answers.get("thought_belief"),
            "emotion": answers.get("emotion", ""),
            "emotion_intensity": answers.get("emotion_intensity"),
            "behavior": answers.get("behavior", ""),
        },
        "quiz_results": dict(state.get("quiz_results") or {}),
    }


def _parse_single_scale(content: str, minimum: int, maximum: int) -> int | None:
    values = re.findall(r"\d+", content)
    if len(values) != 1:
        return None
    value = int(values[0])
    return value if minimum <= value <= maximum else None


def _clean_acknowledgement(value: str, fallback: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        return fallback
    for separator in ("？", "?"):
        normalized = normalized.replace(separator, "。")
    return normalized[:240]


def _trace(step_from: str, step_to: str, **extra: Any) -> dict[str, Any]:
    return {
        "implementation": "conversational_cbt_course",
        "lesson_id": LESSON_1_ID,
        "lesson_version": LESSON_1_VERSION,
        "step_from": step_from,
        "step_to": step_to,
        **extra,
    }


def _formulation_text(answers: dict[str, Any]) -> str:
    thought_belief = answers.get("thought_belief")
    emotion_intensity = answers.get("emotion_intensity")
    thought_note = f"（当时相信程度 {thought_belief}/10）" if thought_belief is not None else ""
    emotion_note = f"（当时强烈程度 {emotion_intensity}/10）" if emotion_intensity is not None else ""
    return "\n".join(
        [
            "我们把刚才的内容整理一下：",
            f"情境：{answers.get('situation', '')}",
            f"想法：{answers.get('thought', '')}{thought_note}",
            f"情绪：{answers.get('emotion', '')}{emotion_note}",
            f"行为：{answers.get('behavior', '')}",
        ]
    )


class CourseEngine:
    """Deterministic lesson state machine; the model never chooses the next step."""

    def __init__(self, *, agent: CourseTutorAgent | None = None):
        self.agent = agent

    def _evaluate(self, state: dict[str, Any], content: str) -> CourseAgentResult:
        step = str(state["step"])
        rules = MODEL_STEP_RULES.get(step)
        if not rules:
            raise ValueError(f"步骤 {step} 不应调用课程模型。")
        answers = dict(state.get("answers") or {})
        relevant_state = {
            key: answers.get(key)
            for key in ("problem", "situation", "thought", "emotion", "behavior")
            if answers.get(key)
        }
        if self.agent is None:
            self.agent = CourseTutorAgent()
        return self.agent.evaluate(
            step=step,
            rubric=str(rules["rubric"]),
            allowed_outcomes=list(rules["outcomes"]),
            content=content,
            relevant_state=relevant_state,
        )

    def process(self, state: dict[str, Any], content: str) -> CourseTurnResult:
        next_state = copy.deepcopy(state)
        if next_state.get("lesson_id") != LESSON_1_ID:
            raise ValueError("当前课程状态无法识别。")
        step = str(next_state.get("step", "mood"))
        answers = next_state.setdefault("answers", {})
        quiz_results = next_state.setdefault("quiz_results", {})
        attachment: dict[str, Any] = {}
        homework_entry: dict[str, str] | None = None
        completion = None
        outcome = "accepted"

        if step == "mood":
            score = _parse_single_scale(content, 1, 10)
            if score is None:
                return CourseTurnResult(
                    reply="请只回复一个 1—10 之间的分数。1 分代表非常糟糕，10 分代表非常好。",
                    state=next_state,
                    trace=_trace(step, step, validation="retry"),
                )
            answers["mood_score"] = score
            next_state["step"] = "problem"
            if score <= 3:
                opening = "听起来上周确实很不容易。谢谢你愿意从这个分数开始，我们慢慢来。"
            elif score <= 6:
                opening = "谢谢你告诉我。看来上周有好有坏，我们可以从一件最想理清的事开始。"
            else:
                opening = "听起来上周整体状态不错，我们也可以从一个小困扰开始练习。"
            reply = opening + " 最近发生过哪一件让你困扰的事？请尽量说清人物、时间和发生了什么。"

        elif step == "thought_belief":
            score = _parse_single_scale(content, 0, 10)
            if score is None:
                return CourseTurnResult(
                    reply="请只回复一个 0—10 之间的分数。0 分代表完全不相信，10 分代表完全相信。",
                    state=next_state,
                    trace=_trace(step, step, validation="retry"),
                )
            answers["thought_belief"] = score
            next_state["step"] = "emotion"
            attachment = dict(STATIC_ATTACHMENTS["thought_example"])
            reply = (
                "记录好了。想法是我们对事情的即时解读，并不一定等同于已经确认的事实。"
                "现在回到你的经历：当你有这个想法时，最明显的情绪是什么？"
            )

        elif step == "emotion_intensity":
            score = _parse_single_scale(content, 0, 10)
            if score is None:
                return CourseTurnResult(
                    reply="请只回复一个 0—10 之间的分数。0 分代表完全不强烈，10 分代表非常强烈。",
                    state=next_state,
                    trace=_trace(step, step, validation="retry"),
                )
            answers["emotion_intensity"] = score
            next_state["step"] = "behavior"
            attachment = dict(STATIC_ATTACHMENTS["emotion_vocabulary"])
            reply = (
                "谢谢你认真标出了强度。情绪是我们的主观感受，图里的词可以帮助你以后为感受命名。"
                "最后看行为：在那种情绪下，你具体做了什么，或刻意没有做什么？"
            )

        else:
            agent_result = self._evaluate(next_state, content)
            completion = agent_result.completion
            decision = agent_result.decision
            outcome = decision.outcome
            if decision.safety_category != "none":
                return CourseTurnResult(
                    reply=(
                        "这句话需要认真对待。请先暂停课程，马上联系身边可信任的人；"
                        "如果有人正面临生命或身体危险，请立即联系当地紧急服务。"
                    ),
                    state=next_state,
                    trace=_trace(step, step, safety=decision.safety_category),
                    completion=completion,
                    safety_event=f"model_{decision.safety_category}",
                )
            extracted = decision.extracted_values.text.strip() or content.strip()
            acknowledgement = _clean_acknowledgement(decision.acknowledgement, "谢谢你说得这么具体。")

            if step == "problem":
                if outcome == "multiple_events":
                    reply = acknowledgement + " 这里有不止一件事。请先选一件你最想梳理的，重新描述那一件就好。"
                elif outcome == "no_clear_event":
                    reply = acknowledgement + " 请试着回忆一个具体时刻：什么时候、和谁、发生了什么？"
                else:
                    answers["problem"] = extracted
                    next_state["step"] = "situation"
                    reply = (
                        acknowledgement
                        + " 我们先只看客观发生的部分，也就是“情境”：当时在哪里、和谁、发生了什么？"
                    )

            elif step == "situation":
                if outcome == "no_clear_answer":
                    reply = acknowledgement + " 请先不写猜测或感受，只说当时在哪里、和谁、具体发生了什么。"
                else:
                    answers["situation"] = extracted
                    next_state["step"] = "thought"
                    reply = acknowledgement + " 回到那一刻，你脑中最先冒出的那句话、判断或预测是什么？"

            elif step == "thought":
                if outcome == "no_clear_answer":
                    reply = acknowledgement + " 可以试着补全这句话：“当时我心里想……”"
                else:
                    answers["thought"] = extracted
                    next_state["step"] = "thought_belief"
                    reply = acknowledgement + " 当时你对这个想法有多相信？请回复 0—10 之间的一个分数。"

            elif step == "emotion":
                if outcome == "no_clear_answer":
                    reply = acknowledgement + " 可以从紧张、难过、担心、生气、孤独里找一个最接近的感受。"
                else:
                    answers["emotion"] = extracted
                    next_state["step"] = "emotion_intensity"
                    reply = acknowledgement + " 这份情绪当时有多强烈？请回复 0—10 之间的一个分数。"

            elif step == "behavior":
                if outcome == "no_clear_answer":
                    reply = acknowledgement + " 请想一想，当时你具体做了什么，或者刻意没有做什么。"
                else:
                    answers["behavior"] = extracted
                    next_state["step"] = "reflection"
                    reply = (
                        acknowledgement
                        + "\n\n"
                        + _formulation_text(answers)
                        + "\n\n把这些内容连起来看，你现在对这件事有什么新的理解或感受？"
                    )

            elif step == "reflection":
                answers["reflection"] = extracted if outcome == "valid_answer" else content.strip()
                next_state["step"] = "quiz_situation"
                attachment = dict(STATIC_ATTACHMENTS["practice_scenario"])
                reply = (
                    acknowledgement
                    + " 接下来用一个例子练习区分四个部分。请阅读图中材料：哪部分是在描述“情境”？"
                )

            elif step in {"quiz_situation", "quiz_thought", "quiz_emotion", "quiz_behavior"}:
                kind = step.removeprefix("quiz_")
                correct = outcome == "correct"
                quiz_results[kind] = {"answer": content.strip(), "correct": correct}
                if step == "quiz_situation":
                    feedback = (
                        "答对了：情境是“别人和我说话或打招呼时，我没有想到合适的话”。"
                        if correct
                        else "这里的情境是“别人和我说话或打招呼时，我没有想到合适的话”。"
                    )
                    next_state["step"] = "quiz_thought"
                    reply = feedback + " 接着，哪部分是在描述“想法”？"
                elif step == "quiz_thought":
                    feedback = (
                        "答对了：关于不回应会显得不礼貌、影响关系的判断是想法。"
                        if correct
                        else "想法是“如果不回应，对方会觉得我不礼貌、没兴趣聊天，还会影响关系”。"
                    )
                    next_state["step"] = "quiz_emotion"
                    reply = feedback + " 接着，哪部分是在描述“情绪”？"
                elif step == "quiz_emotion":
                    feedback = "答对了：这里的情绪是“紧张”。" if correct else "这里的情绪是“我会感到紧张”。"
                    next_state["step"] = "quiz_behavior"
                    reply = feedback + " 最后，哪部分是在描述“行为”？"
                else:
                    feedback = (
                        "答对了：行为是“我会拼命想和人说话”。"
                        if correct
                        else "这里的行为是“我会拼命想和人说话”。"
                    )
                    correct_count = sum(1 for result in quiz_results.values() if result.get("correct"))
                    next_state["step"] = "goal"
                    attachment = dict(STATIC_ATTACHMENTS["practice_answers"])
                    reply = (
                        f"{feedback} 这次你答对了 {correct_count}/4 题。"
                        "最后想一想：完成全部课程后，你希望生活中的什么有所改善？"
                    )

            elif step == "goal":
                if outcome == "no_clear_answer":
                    reply = acknowledgement + " 可以从情绪、关系、睡眠或日常行动中，选一个最想改善的方向。"
                else:
                    answers["goal"] = extracted
                    next_state["step"] = "completed_idle"
                    next_state["completed"] = True
                    reply = (
                        acknowledgement
                        + " 第 1 课完成了。你已经用情境、想法、情绪和行为梳理了一件事。"
                        "以后想做课后练习时，可以在这里输入“记录日记”，我会继续用四个问题陪你完成。"
                    )

            elif step == "completed_idle":
                if outcome == "start_diary":
                    next_state["step"] = "diary_situation"
                    next_state["diary_draft"] = {}
                    reply = "我们开始一条新的四要素日记。先说说这次具体发生了什么？"
                else:
                    reply = "本课已经完成。想做课后练习时，请告诉我“记录日记”；也可以返回课程目录重新学习。"

            elif step == "diary_situation":
                if outcome == "no_clear_answer":
                    reply = "请先写一个具体时刻：什么时候、和谁、发生了什么？"
                else:
                    next_state.setdefault("diary_draft", {})["situation"] = extracted
                    next_state["step"] = "diary_thought"
                    reply = acknowledgement + " 那一刻，你脑中最先出现了什么想法？"

            elif step == "diary_thought":
                if outcome == "no_clear_answer":
                    reply = "可以试着补全：“当时我心里想……”"
                else:
                    next_state.setdefault("diary_draft", {})["thought"] = extracted
                    next_state["step"] = "diary_emotion"
                    reply = acknowledgement + " 当时最明显的情绪是什么？"

            elif step == "diary_emotion":
                if outcome == "no_clear_answer":
                    reply = "请用一个具体的感受词，例如紧张、难过、担心或生气。"
                else:
                    next_state.setdefault("diary_draft", {})["emotion"] = extracted
                    next_state["step"] = "diary_behavior"
                    reply = acknowledgement + " 在那种情绪下，你具体做了什么，或没有做什么？"

            elif step == "diary_behavior":
                if outcome == "no_clear_answer":
                    reply = "请写下一个具体行动，或者当时刻意回避了什么。"
                else:
                    draft = next_state.setdefault("diary_draft", {})
                    draft["behavior"] = extracted
                    homework_entry = {key: str(draft.get(key, "")) for key in ("situation", "thought", "emotion", "behavior")}
                    next_state["diary_draft"] = {}
                    next_state["step"] = "completed_idle"
                    reply = "这条四要素日记已经保存好了。以后想再记录一条，继续告诉我“记录日记”就可以。"

            else:
                raise ValueError("当前课程步骤无法识别。")

        return CourseTurnResult(
            reply=reply,
            state=next_state,
            trace=_trace(
                step,
                str(next_state["step"]),
                outcome=outcome,
                completed=bool(next_state.get("completed")),
                attachment_kind=attachment.get("kind"),
            ),
            attachment=attachment,
            homework_entry=homework_entry,
            completion=completion,
        )
