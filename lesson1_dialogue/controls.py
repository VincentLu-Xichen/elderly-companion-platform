"""Explicit learner buttons use the same state executor, with zero model calls."""
from .contracts import DialogueError, checked_state
from .engine import apply_turn
from .course import record_fingerprint

LABELS = {"skip_weekly":"先跳过近况", "start_practice":"开始练习", "show_review":"回看这次记录",
    "choose_fictional":"用课程例子练习", "choose_personal":"换一件本人愿意谈的事",
    "confirm_record":"确认以上记录", "start_check":"换个例子试一试", "check_hint":"需要一点提示",
    "skip_check":"这题先跳过", "start_retry":"换个例子再练两题", "finish_retry":"结束这次补练",
    "after_check":"继续设置练习目标", "confirm_goal":"确认这个目标", "skip_goal":"暂不设置目标",
    "accept_plan":"愿意课后试一试", "decline_plan":"暂不安排课后练习", "finish":"完成本课",
    "pause":"暂停课程", "resume":"继续刚才的学习或对话", "resume_course":"回到原练习",
    "close":"结束本次学习", "resume_session":"恢复这次学习"}
for _field,_label in {"situation":"事情","thought":"想法","emotion":"心情","behavior":"做法",
                     "thought_belief":"相信程度","emotion_intensity":"情绪强度"}.items():
    LABELS["defer_"+_field]="这项先留空："+_label


def available_controls(state):
    if state.session_status=="completed":return []
    if state.session_status=="ended":return ["resume_session"]
    if state.flow_mode=="paused":return ["close"] if state.paused_reason=="safety" else ["resume","close"]
    if state.flow_mode=="communicating":return ["resume_course","pause","close"]
    phase=state.lesson_progress.phase
    course=state.course
    controls={"check_in":["skip_weekly"],"learn":["start_practice","choose_fictional"],
        "practice":["show_review","choose_fictional","choose_personal"],
        "review":["show_review","confirm_record","start_check"],"check":["check_hint","skip_check"],
        "check_feedback":(["check_hint","skip_check","finish_retry"] if course.retry.status=="active" else
                           (["start_retry"] if course.retry.status=="not_started" else [])+["after_check"]),
        "learning_goal":(["confirm_goal"] if course.goal is not None else [])+["skip_goal"],
        "plan":["accept_plan","decline_plan"],"summary":["decline_plan" if course.plan_status=='accepted' else "accept_plan","finish"]}[phase]
    if phase=="practice":
        from .course import practice_ready
        from .engine import context_facts
        if not practice_ready(state.model_dump()):controls.remove("show_review")
        controls += ["defer_"+field for field,view in context_facts(state)["fields"].items() if view["ask_allowed"]]
        if state.case_kind=='fictional':controls.remove('choose_fictional')
    if phase=="review":
        from .course import practice_ready
        if not practice_ready(state.model_dump()):
            controls=[c for c in controls if c not in {'show_review','confirm_record','start_check'}]
        elif state.course.confirmation is None:controls.remove("start_check")
        else:controls.remove('confirm_record')
    return controls+["pause","close"]


def apply_control(state, message, control, request_id):
    from .engine import replay
    cached=replay(state,message,request_id)
    if cached:return cached
    state=checked_state(state)
    if control not in available_controls(state):raise DialogueError("control_not_available")
    if control=="resume_session":
        data=state.model_dump();data["session_status"]="active";state=checked_state(data)
    refs=[{"id":"control", "source_message_id":message.message_id,"quote":message.text}]
    output={"based_on_revision":state.revision,"reply":"已保留您的选择。", "evidence_refs":refs,"actions":[]}
    if control in {"pause","resume","resume_course","close"}:
        output.update(signal={"pause":"pause_request","resume":"resume_request",
                              "resume_course":"resume_request","close":"close_request"}[control],signal_ref_ids=["control"])
        output["reply"]={"pause":"好，先停在这里，已有内容保留。","resume":"好，接着刚才保留的位置。",
                         "resume_course":"好，我们接着原来的练习。","close":"这次学习先到这里，已有内容保留。"}[control]
        if control in {"resume","resume_course"}:
            output.update(resume_target="previous_mode" if control=="resume" else "teaching",resume_basis="explicit_request")
    elif control.startswith("defer_"):
        output["actions"]=[{"id":"defer-control","type":"set_boundary","source_ref_ids":["control"],"depends_on":[],
                           "payload":{"kind":"defer_field","target_ref":control[6:],"scope":"current_case"}}]
        output["reply"]="这一项先留空，不代表理解差；已有内容保留。"
    elif control!="resume_session":
        payload={"operation":control}
        if control=="confirm_record":payload["record_fingerprint"]=record_fingerprint(state.model_dump())
        if control=="confirm_goal":payload["expected_goal_revision"]=state.course.goal_revision
        output["actions"]=[{"id":"control-action","type":"course_action","source_ref_ids":["control"],
                            "depends_on":[],"payload":payload}]
        output["reply"]={"confirm_record":"这份记录已按您的核对保存。","check_hint":"先看看当前提示，再按自己的理解回答。",
            "skip_check":"这题先跳过，不作为答错。","start_retry":"好，换一个例子，补练与首次结果分开保留。",
            "finish_retry":"这次补练先停下，已回答的部分保留。","skip_goal":"已保留您暂不设置目标的选择。",
            "confirm_goal":"这个目标已按您的确认保存。","accept_plan":"已保留您愿意尝试的安排，尚不代表已经执行。",
            "decline_plan":"好，暂不安排课后练习。","finish":"本课已完成，学习记录保留。"}.get(control,"好，接着看当前环节。")
        # Material on the page must also appear in the conversational history;
        # otherwise the next model sees an answer after a generic transition.
        if control in {'start_check','start_retry','check_hint','skip_check'}:
            from .course import current_check
            from lesson1_support.content import QUESTIONS,RETRY_QUESTIONS,STORY_A,STORY_B
            if control in {'start_check','start_retry'}:
                story,questions=(STORY_A,QUESTIONS) if control=='start_check' else (STORY_B,RETRY_QUESTIONS)
                output['reply']='请按自己的理解回答这个课程例子：\n'+story+'\n\n'+questions[0]['prompt']
            else:
                _,attempt,questions,story=current_check(state.model_dump())
                index=attempt['index']+(1 if control=='skip_check' else 0)
                if index<len(questions):
                    output['reply']=('这题先跳过，不作为答错。\n\n' if control=='skip_check' else
                        '提示：'+questions[index]['hint']+'\n\n')+questions[index]['prompt']
                else:output['reply']='这题先跳过。本次检验已结束，可以回看已有结果。'
        elif control=='after_check':
            output['reply']='接下来可以说一项希望在生活中练习的方向，也可以暂不设置目标。'
    return apply_turn(state,message,output,request_id,model_calls=0)
