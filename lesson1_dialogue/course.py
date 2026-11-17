"""Lesson-one content projection and deterministic phase preconditions."""
import copy
import hashlib
import json
import re
from typing import Annotated, Literal, Union

from pydantic import Field, create_model
from lesson1_support.content import LESSON_1_DEMONSTRATION, PRACTICE_PLANS
from lesson1_support.content import QUESTIONS, RETRY_QUESTIONS, STORY_A, STORY_B
from .course_types import (Weekly, Move, ConfirmRecord, CheckAnswer, SetGoal, ConfirmGoal,
                           StageCheck,AdoptCheck,StageGoal,AdoptGoal)
from .models import CourseAction

LABELS = {"check_in": "近况与回顾", "learn": "认识四要素", "practice": "一起练习",
          "review": "核对学习记录", "check": "换个例子试一试", "check_feedback": "回看与补练",
          "learning_goal": "我的练习目标", "plan": "课后安排", "summary": "回顾与结束"}
PHASE_MOVES = {
    "check_in": ("skip_weekly", "start_learning"),
    "learn": ("start_practice", "choose_fictional", "choose_personal"),
    "practice": ("show_review", "choose_fictional", "choose_personal"),
    "review": ("show_review", "start_check", "choose_fictional", "choose_personal"),
    "check": ("check_hint", "skip_check"),
    "check_feedback": ("start_retry", "finish_retry", "after_check", "check_hint", "skip_check"),
    "learning_goal": ("skip_goal",), "plan": ("accept_plan", "decline_plan", "go_summary"),
    "summary": ("accept_plan", "decline_plan", "finish"),
}
SPECIALS = {"check_in": Weekly, "review": ConfirmRecord, "check": (CheckAnswer,AdoptCheck),
            "check_feedback": (CheckAnswer,AdoptCheck), "learning_goal": (SetGoal, ConfirmGoal,AdoptGoal)}


def action_for_phase(phase, *, include_staging=False):
    move = create_model("Move_"+phase, __base__=Move,
                        operation=(Literal[PHASE_MOVES[phase]], ...))
    variants = [move]
    special = SPECIALS.get(phase)
    if special is not None:
        variants.extend(special if isinstance(special, tuple) else (special,))
    if include_staging:
        if phase in {"check", "check_feedback"}: variants.append(StageCheck)
        elif phase == "learning_goal": variants.append(StageGoal)
    payload = Annotated[Union[tuple(variants)], Field(discriminator="operation")] if len(variants)>1 else move
    return create_model("CourseAction_"+phase, __base__=CourseAction, payload=(payload, ...))


def staging_action_for_phase(phase):
    if phase in {"check","check_feedback"}:payload=StageCheck
    elif phase=="learning_goal":payload=StageGoal
    else:return None
    return create_model("StagedCourseAction_"+phase,__base__=CourseAction,payload=(payload,...))


def record_fingerprint(data):
    facts = {k: data[k] for k in ("active_case_id", "case_kind", "records", "ratings", "field_versions")}
    return hashlib.sha256(json.dumps(facts,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def current_check(data):
    retry = data["course"]["retry"]["status"] == "active"
    key, questions, story = ("retry", RETRY_QUESTIONS, STORY_B) if retry else ("first", QUESTIONS, STORY_A)
    return key, data["course"][key], questions, story


def practice_progress(data):
    """Project the accepted case, never a second writable progress authority."""
    from .engine import _active
    stop=any(_active(data,"stop_case_questions"))
    def missing(fields):
        return [f for f in fields if not (f in data['records'] or f in data['ratings'] or stop
                                         or any(_active(data,'defer_field',f)))]
    record_fields=missing(('situation','thought','emotion','behavior'))
    rating_fields=missing(('thought_belief','emotion_intensity')) if data['case_kind']=='personal' else []
    ready=not (record_fields or rating_fields)
    confirmed=bool(ready and data['course']['confirmation'] and
        data['course']['confirmation']['fingerprint']==record_fingerprint(data))
    task=('practice-elements' if record_fields else 'practice-ratings' if rating_fields else
          'review-confirmed' if confirmed else 'review')
    return {'activity_id':task,'missing_elements':record_fields,'missing_ratings':rating_fields,
            'ready_for_review':ready,
            'record_confirmed':confirmed,'next_operation':'start_check' if confirmed else None,
            'case_options':'parallel_alternatives'}


def practice_ready(data):
    return practice_progress(data)['ready_for_review']


def sync_practice_progress(data):
    """An accepted formal case starts practice; completed work is not requested again.

    Called only after a normal teaching turn. This does not grant confirmation,
    invent records, adopt conversation candidates, or advance independent checks.
    """
    progress=data['lesson_progress']
    if not data['course']['enabled'] or progress['phase'] not in {'learn','practice','review'}:return
    if progress['phase']=='learn' and not (data['records'] or data['ratings']):return
    view=practice_progress(data)
    phase='review' if view['ready_for_review'] else 'practice'
    candidates=view['missing_elements'] or view['missing_ratings']
    field=progress['field'] if progress['field'] in candidates else next(iter(candidates),None)
    target=(phase,view['activity_id'],field)
    if target!=(progress['phase'],progress['activity_id'],progress['field']):
        progress.update(phase=phase,activity_id=view['activity_id'],field=field,
                        task_revision=progress['task_revision']+1)
        invitation=data['return_invitation']
        if invitation and invitation['status']=='pending':invitation['status']='superseded'


def context(data):
    phase = data["lesson_progress"]["phase"]
    course = data["course"]
    result = {"phase": phase, "phase_label": LABELS[phase], "record_fingerprint": record_fingerprint(data),
              "case_kind": data["case_kind"], "weekly_score": course["weekly_score"],
              "weekly_skipped": course["weekly_skipped"], "goal": course["goal"],
              "goal_confirmed_revision": course["goal_confirmed_revision"],
              "goal_skipped": course["goal_skipped"], "plan_status": course["plan_status"]}
    if phase in {'learn','practice','review'}:result['practice_progress']=practice_progress(data)
    result["pending_responses"]=copy.deepcopy(course["pending_responses"])
    result["attempts"]={k:copy.deepcopy(course[k]) for k in ("first","retry")}
    if phase == "check_in":
        result["material"] = "请用1—10分说说上周整体状态，也可以先跳过；这与课内0—10评分分开。"
    elif phase == "learn":
        result["material"] = LESSON_1_DEMONSTRATION
    elif phase == "practice":
        from .stage_cards import LIBRARY_STORY, PRACTICE_PERSONAL
        story=data.get('case_story')
        result["material"] = '\n'.join(s['quote'] for s in story['sources']) if story else (
            LIBRARY_STORY if data["case_kind"] == "fictional" else PRACTICE_PERSONAL)
    elif phase in {"check", "check_feedback"}:
        key, attempt, questions, story = current_check(data)
        if attempt["status"] == "active":
            index = attempt["index"]
            q = questions[index]
            # Deliberately omit expected answer keys from all model/context projections.
            result["check"] = {"attempt_id": key, "question_index": index, "story": story,
                               "field": q["field"], "prompt": q["prompt"]}
            if index in attempt["hints"]:
                result["check"]["hint"] = q["hint"]
        result["attempts"] = {k: copy.deepcopy(course[k]) for k in ("first", "retry")}
    elif phase == "learning_goal":
        result["material"] = "可以说一项想在生活中练习的方向；目标需要本人核对，也可以暂不设置。"
    elif phase == "plan":
        result["material"] = PRACTICE_PLANS["lesson-1"]
    elif phase == "summary":
        result["material"] = "本课学习区分情境、想法、情绪、行为；完成练习不代表已经在生活中熟练运用。"
    return result


def validate_goal_draft(value, sources):
    """Quotes remain exact; a draft may faithfully paraphrase before user review."""
    from .contracts import DialogueError
    brief={'好','好的','嗯','嗯嗯','继续','可以','行','不知道','我不知道','没想好'}
    def plain(text):return re.sub(r'[\s，,。.!！?？、]+','',text)
    if not sources:raise DialogueError('goal_source')
    if plain(value) in brief or all(plain(s['quote']) in brief for s in sources):
        raise DialogueError('goal_not_explicit')


def apply_course_action(data, action, sources, request_id):
    from .contracts import DialogueError
    from .engine import _active, _id
    phase = data["lesson_progress"]["phase"]
    course = data["course"]
    payload, op = action.payload, action.payload.operation
    if not course["enabled"]:
        raise DialogueError("course_not_enabled")
    allowed = set(PHASE_MOVES[phase]) | {
        "check_in": {"weekly_score"}, "review": {"confirm_record"},
        "check": {"check_answer","stage_check_answer","adopt_check_answer"},
        "check_feedback": {"check_answer","stage_check_answer","adopt_check_answer"},
        "learning_goal": {"set_goal", "confirm_goal","stage_goal","adopt_goal"},
    }.get(phase,set())
    if op not in allowed:
        raise DialogueError("course_phase_action")
    def need(condition, code):
        if not condition: raise DialogueError(code)
    def move(target, field=None):
        data["lesson_progress"].update(phase=target, activity_id=target, field=field,
            task_revision=data["lesson_progress"]["task_revision"]+1)
        if data["return_invitation"] is not None and data["return_invitation"]["status"] == "pending":
            data["return_invitation"]["status"] = "superseded"
    if op in {"stage_check_answer","stage_goal"}:
        if op=='stage_goal':validate_goal_draft(payload.value,sources)
        else:need(any(payload.value in s["quote"] for s in sources),"response_source")
        if op=="stage_check_answer":
            key,attempt,questions,_=current_check(data)
            need(attempt["status"]=="active" and payload.attempt_id==key and payload.question_index==attempt["index"],"check_question_mismatch")
        else:need(payload.expected_goal_revision==course["goal_revision"],"goal_revision_conflict")
        for old in course["pending_responses"]:
            if old["status"]=="pending" and old["task_revision"]==data["lesson_progress"]["task_revision"]:
                old["status"]="superseded"
        course["pending_responses"].append({"id":_id("response",request_id,action.id),"content":payload.model_dump(),
            "task_revision":data["lesson_progress"]["task_revision"],"sources":sources,"status":"pending","adopted_revision":None})
    elif op in {"adopt_check_answer","adopt_goal"}:
        pending=next((p for p in course["pending_responses"] if p["id"]==payload.pending_id),None)
        need(pending is not None and pending["status"]=="pending" and
             pending["task_revision"]==data["lesson_progress"]["task_revision"],"pending_response_stale")
        need(sources==pending["sources"],"pending_response_source")
        original=pending["content"]
        if op=="adopt_check_answer":
            need(original["operation"]=="stage_check_answer","pending_response_kind")
            adopted=CheckAnswer(operation="check_answer",attempt_id=original["attempt_id"],
                question_index=original["question_index"],verdict=payload.verdict,reason=payload.reason)
        else:
            need(original["operation"]=="stage_goal" and original["expected_goal_revision"]==course["goal_revision"],"goal_revision_conflict")
            adopted=SetGoal(operation="set_goal",value=original["value"])
        apply_course_action(data,action.model_copy(update={"payload":adopted}),sources,request_id)
        pending.update(status="adopted",adopted_revision=data["revision"]+1)
    elif op == "weekly_score":
        nums=re.findall(r"(?<![0-9.])[-+]?\d+(?:\.\d+)?(?![0-9.])",payload.quote)
        need(len(nums)==1 and float(nums[0])==payload.value and any(payload.quote in s["quote"] for s in sources),"weekly_score_evidence")
        course.update(weekly_score=payload.value,weekly_skipped=False,weekly_sources=sources)
        move("learn")
    elif op in {"skip_weekly","start_learning"}:
        if op=="skip_weekly":course.update(weekly_skipped=True,weekly_sources=sources)
        need(course["weekly_score"] is not None or course["weekly_skipped"],"weekly_mood_required")
        move("learn")
    elif op == "start_practice":
        need(data["case_kind"]=="fictional" or not any(_active(data,"no_personal_case")),"personal_case_blocked")
        move("practice","situation")
    elif op in {"choose_fictional","choose_personal"}:
        # A bare continuation accepts the current task, never a destructive case reset.
        brief={"继续","继续吧","好","好的","好啊","嗯","嗯嗯","可以","行","就这样","就是这样","嗯嗯就是这样","ok"}
        need(not all(s['quote'].strip().strip('。.!！?？ ,，').lower() in brief for s in sources),
             'case_choice_requires_selection')
        kind = "fictional" if op=="choose_fictional" else "personal"
        need(kind=="fictional" or not any(_active(data,"no_personal_case")),"personal_case_blocked")
        data["archived_cases"].append({"case_id":data["active_case_id"],"case_kind":data["case_kind"],
            "records":copy.deepcopy(data["records"]),"ratings":copy.deepcopy(data["ratings"]),
            'story':copy.deepcopy(data.get('case_story'))})
        data.update(active_case_id=_id("case",request_id),case_kind=kind,records={},ratings={},field_versions={},case_story=None)
        course["confirmation"]=None
        move("practice","situation")
    elif op == "show_review":
        need(practice_ready(data),"practice_incomplete")
        if phase!='review':move("review")
    elif op == "confirm_record":
        need(practice_ready(data),'practice_incomplete')
        need(payload.record_fingerprint==record_fingerprint(data),"confirmation_stale")
        course["confirmation"]={"fingerprint":payload.record_fingerprint,"sources":sources}
    elif op == "start_check":
        need(practice_ready(data),'practice_incomplete')
        need(course["confirmation"] is not None and
             course["confirmation"]["fingerprint"]==record_fingerprint(data),"record_confirmation_required")
        course["first"].update(status="active",index=0,answers=[],hints=[])
        move("check")
    elif op in {"check_answer","skip_check","check_hint"}:
        key,attempt,questions,_=current_check(data)
        need(attempt["status"]=="active" and attempt["index"]<len(questions),"check_not_active")
        index=attempt["index"]
        if op=="check_hint":
            if index not in attempt["hints"]:attempt["hints"].append(index)
        else:
            if op=="check_answer":
                need(payload.attempt_id==key and payload.question_index==index,"check_question_mismatch")
                verdict,reason=payload.verdict,payload.reason
            else:verdict,reason="not_observed","本人选择跳过，不作为答错。"
            attempt["answers"].append({"question_index":index,"verdict":verdict,"reason":reason,
                                       "sources":sources,"assisted":any(h<=index for h in attempt["hints"]),
                                       "prior_feedback":index>0})
            attempt["index"]+=1
            data["lesson_progress"]["attempts"]+=int(op=="check_answer")
            if attempt["index"]==len(questions):
                attempt["status"]="completed"
                move("check_feedback")
            else:data["lesson_progress"]["task_revision"]+=1
    elif op == "start_retry":
        need(course["first"]["status"]=="completed" and course["retry"]["status"]=="not_started","retry_unavailable")
        course["retry"]["status"]="active"
        data["lesson_progress"]["task_revision"]+=1
    elif op == "finish_retry":
        need(course["retry"]["status"]=="active","retry_not_active")
        course["retry"]["status"]="stopped"
        data["lesson_progress"]["task_revision"]+=1
    elif op == "after_check":
        need(course["first"]["status"]=="completed" and course["retry"]["status"]!="active","check_incomplete")
        move("learning_goal")
    elif op == "set_goal":
        validate_goal_draft(payload.value,sources)
        course["goal_revision"]+=1
        course.update(goal={"value":payload.value,"revision":course["goal_revision"],"sources":sources},
                      goal_confirmed_revision=None,goal_confirmation_sources=[],goal_skipped=False)
    elif op == "confirm_goal":
        need(course["goal"] is not None and payload.expected_goal_revision==course["goal_revision"],"goal_confirmation_stale")
        course.update(goal_confirmed_revision=course["goal_revision"],goal_confirmation_sources=sources)
        move("plan")
    elif op == "skip_goal":
        course.update(goal_skipped=True,goal_confirmed_revision=None,goal_confirmation_sources=sources)
        move("plan")
    elif op in {"accept_plan","decline_plan"}:
        course.update(plan_status="accepted" if op=="accept_plan" else "declined",plan_sources=sources)
        move("summary")
    elif op == "go_summary":
        need(course["plan_status"]!="undecided","plan_choice_required")
        move("summary")
    elif op == "finish":
        need(course["first"]["status"]=="completed" and course["plan_status"]!="undecided" and
             (course["goal_skipped"] or course["goal_confirmed_revision"]==course["goal_revision"]>0),"finish_precondition")
        data["session_status"]="completed"
    return "course:"+op
