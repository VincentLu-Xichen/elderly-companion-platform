"""Per-turn teaching goals and operation effects; no independent progress state."""
from copy import deepcopy
from lesson1_support.content import LESSON_1_DEMONSTRATION, PRACTICE_PLANS
from lesson1_support.content import QUESTIONS, RETRY_QUESTIONS, STORY_A, STORY_B
from .course import LABELS
from .examples import EXAMPLES, LIBRARY_STORY, RUBRIC, teacher_examples
from .prompts import SUPPORT_GOAL, SUPPORT_RETURN

PRACTICE_PERSONAL = '从本人已经描述的近期困扰中，引导本人尝试区分情境、想法、情绪和行为；先回应再提问，提示按需要给，不代分全套。相信程度和情绪强度为0—10，也可暂留。'
SUMMARY = '本课学习区分情境、想法、情绪、行为；完成练习不代表已经在生活中熟练运用。'

GOALS = {
    'check_in': '收集上周整体状态1—10分，或尊重明确跳过；保存后引入四要素概念。',
    'learn': '承接已经呈现的概念示范并回应具体疑问；普通确认后简短邀请选择练习，不默认重讲。',
    'practice': '围绕同一案例先承接，再引导本人辨别；保存本人已尝试的分类，提示按需给，缺失/暂留/拒绝分开，不代分全套。',
    'review': '回看实际记录，允许修改；只接受对当前版本的本人明确核对。',
    'check': '判读当前故事/当前题的实际回答；求助和倾诉不计作答。',
    'check_feedback': '简要反馈已观察结果，默认衔接学习目标；本人主动要求才补练，首次与补练分开保留。',
    'learning_goal': '支持本人表达练习方向，建议与本人选择分开；先草稿，再独立确认，也可跳过。',
    'plan': '说明自愿课后安排，允许拒绝；计划不代表已执行或有效。',
    'summary': '概括真实成果、未定项与本人选择；满足前置条件及本人完成意愿才完成。',
}
DO_NOT = {
    'check_in': ['不要直接索取个人练习四要素/两项评分。', '不要把上周1—10量尺说成课内0—10。'],
    'learn': ['展示材料不等于已经掌握。', '不要过早要求改成积极想法。', '小林是已经讲解完的标准示范，不要求再辨别小林，也不说“接下来用这个例子练习”；练习另选本人愿意谈的事或老李。', '普通承接不重新列出完整示范和四项答案；明确求助/回看可针对性重讲。'],
    'practice': ['不重复索取已表达或暂留项。', '不把虚构人物当本人，不为课程例子编造本人评分。',
                 '未作答且未请求讲解时不先给待答项的标准分类；反馈本轮答案不等于提前讲完后续项。'],
    'review': ['不在修改同一份记录的同时确认它。'],
    'check': ['不把故事人物写成本人经历。', '解释/提示后作答不冒充未受帮助的独立表现。'],
    'check_feedback': ['不覆盖首次结果。', '不主动列补练菜单或反复问要不要再练；已说会了/不再练时直接衔接目标，不把能力自评当补练意愿。'],
    'learning_goal': ['不把好/嗯/不知道当目标，不同轮设置与确认。'],
    'plan': ['不替本人同意，不声称计划已执行。'],
    'summary': ['不把结束会话/暂停当课程完成，不因反思失败撤销成果。'],
}
TARGETS = {
    'weekly_score': 'learn', 'skip_weekly': 'learn', 'start_learning': 'learn',
    'start_practice': 'practice', 'choose_fictional': 'practice', 'choose_personal': 'practice',
    'show_review': 'review', 'start_check': 'check', 'after_check': 'learning_goal',
    'confirm_goal': 'plan', 'skip_goal': 'plan', 'accept_plan': 'summary',
    'decline_plan': 'summary', 'go_summary': 'summary',
}
PRECONDITIONS = {
    'weekly_score': '本轮本人明确上周1—10评分；证据片段只包含该分数。',
    'skip_weekly': '本轮本人明确选择跳过近况。',
    'start_practice': '用户愿意开始练习；个人案例询问未被禁止。',
    'choose_fictional': '本轮本人明确选择课程例子；不与旧案例记录修改同批。',
    'choose_personal': '本轮本人明确换案；如本课禁止个人案例，需先有新明确许可解除对应边界。',
    'show_review': '必要项已表达或合法暂留/拒绝；可回看已进入核对的记录，不代表本人确认。',
    'confirm_record': '本人明确核对当前整份记录；不与该记录修改同批。',
    'start_check': '当前记录已经本人核对且指纹仍有效。',
    'check_answer': '本轮是在回答当前检验题；求助/倾诉不是作答。',
    'check_hint': '本人需要提示；不计作答。',
    'skip_check': '本人明确跳过当前题；不作为答错。',
    'start_retry': '首次四题已完成、补练未开始，且本人本轮主动明确要求额外补练；不默认邀请。',
    'finish_retry': '补练正在进行，本人愿意结束本次补练。',
    'after_check': '首次已完成，当前没有仍在进行的补练。',
    'set_goal': '依据本人明确目标，原句作证据，草稿允许忠实整理；不是好/继续/不知道，不代本人确认。',
    'confirm_goal': '已存在本人目标草稿；本轮独立明确核对，不同批设置目标。',
    'skip_goal': '本人明确暂不设置目标。',
    'accept_plan': '本人明确愿意课后尝试；不代表已执行。',
    'decline_plan': '本人明确不安排课后练习。',
    'finish': '本轮开始在summary且成果门槛满足，本人明确完成课程。',
}
EFFECT_FLAGS = {
    'confirm_record': {'record_confirmed': True},
    'set_goal': {'goal_status': 'draft', 'goal_confirmed': False},
    'adopt_goal': {'goal_status': 'draft', 'goal_confirmed': False},
    'confirm_goal': {'goal_confirmed': True},
    'skip_goal': {'goal_skipped': True},
    'accept_plan': {'plan_status': 'accepted'}, 'decline_plan': {'plan_status': 'declined'},
    'check_hint': {'hint_granted': True, 'answer_count_increased': False},
    'skip_check': {'verdict': 'not_observed', 'answer_count_increased': False},
    'start_retry': {'retry_status': 'active', 'first_result_preserved': True},
    'finish_retry': {'retry_status': 'stopped', 'first_result_preserved': True},
    'choose_fictional': {'previous_case_archived': True, 'new_case_empty': True, 'own_ratings_required': False},
    'choose_personal': {'previous_case_archived': True, 'new_case_empty': True},
}


def _material(phase, state, *, fictional=None):
    if phase == 'learn': return 'concepts', LESSON_1_DEMONSTRATION
    if phase == 'practice':
        if state.case_story and fictional is None:
            return 'practice-selected-event','\n'.join(s.quote for s in state.case_story.sources)
        kind = state.case_kind == 'fictional' if fictional is None else fictional
        return ('practice-library', LIBRARY_STORY) if kind else ('practice-personal', PRACTICE_PERSONAL)
    if phase == 'check': return 'check-first', STORY_A + '\n\n' + QUESTIONS[0]['prompt']
    if phase == 'plan': return 'practice-plan', PRACTICE_PLANS['lesson-1']
    if phase == 'summary': return 'summary', SUMMARY
    if phase == 'check_feedback' and state.course.retry.status == 'active':
        index = state.course.retry.index
        return 'check-retry', STORY_B + '\n\n' + RETRY_QUESTIONS[index]['prompt']
    return None


def build_stage_card(state, operations, fields):
    """operations comes from the exact wire payload variants, never a second whitelist."""
    phase = state.lesson_progress.phase
    card = {'phase': phase, 'phase_label': LABELS[phase], 'mode': state.flow_mode,
            'goal': GOALS[phase], 'fields': deepcopy(fields), 'do_not': list(DO_NOT[phase]),
            'operations': {}, 'materials': {}}
    shown=[]
    for ref,example in EXAMPLES.items():
        if any(m.role=='agent' and (example['story'] in m.text or
               (example['person'] in m.text and all(part in m.text for part in example['parts'].values())))
               for m in state.conversation_history):shown.append(ref)
    card['material_delivery']={'shown_in_prior_agent_messages':shown,
        'meaning':'只证明这些素材文字已经展示，不证明用户已答题或掌握。',
        'page_location':'学习材料在默认收起的只读记录中；不能假定学习者已经看过，首次新故事需在reply给出。',
        'reply_policy':'正文不默认重贴页面故事或已讲示范；明确求助/回看/纠错时按需要解释。'}
    card['operation_rule']='只适用于本轮所在分支；转场先看capability_view.branches的allowed_actions和reply_task。'
    if state.flow_mode != 'teaching':
        card.update(goal=SUPPORT_GOAL,return_policy=SUPPORT_RETURN,
                    teaching_position_role='内部返回定位；交流围绕当前困扰，不反复播报课程，原题补答仅暂存。',
                    do_not=['不以教学缺项催促作答；恢复本轮不执行目标模式教学。'])
        if state.flow_mode == 'paused':
            card.pop('return_policy')
            card.update(goal='课程暂停：只承接、澄清、合法恢复或结束。',
                        do_not=['不收集课程候选、不推进；安全暂停不以普通继续解除。'])
        return card
    if phase in {'learn','practice','review'}:
        from .course import practice_progress
        card['practice_progress']=practice_progress(state.model_dump())
        if phase=='review' and card['practice_progress']['record_confirmed']:
            card['goal']='本案例已核对完成，直接衔接下一教学环节；无需再核对、重贴案例或默认邀请继续聊此事。'
            card['do_not']+=['不把局部停聊当作整次学习结束，不重复确认。']
        card['progress_rule']='正式写入当前案例即开始练习；程序按本轮保存后的记录/暂留更新进度。四要素齐全只处理未定评分；所有必要项完成/暂留后进入未确认核对。本人案例与课程例子是并列选择，不是前后两套必做练习。'
        from .context import response_scope
        if response_scope(state)['kind']=='unselected_material':
            card['response_scope_rule']='前文展示了尚未选用的课程材料。当前回答不能写入本人记录；可简短反馈材料，再回到task_view指定的当前缺项（teaching_step.select_field）或回看记录，不要求重辨已完成四要素。明确换案才choose_fictional。'
    if phase=='practice' and state.case_kind=='personal':
        card['recording_rule']='先判断是在初述事件还是辨别作答：初述只作上下文，先回应再引导本人区分；对本人本轮辨别/主动分类/更正，明确几项便保存几项，不替尚未尝试的项补答案。已主动分四项就保存四项不重问。原句作来源，整理值允许忠实改写。'
        card['do_not']+=['纯概念提问/求助不是本人事实，可actions=[]；不从解释或课程人物编造本人记录。',
                         '聊天新事件不写入当前案例，转交流时按分支暂存原题补答。']
    if phase=='practice' and state.case_kind=='fictional':
        card['goal']='让学习者先尝试区分当前课程人物四要素，保存其明确作答并针对已答部分反馈；不是本人经历，不需要本人评分。'
        card['do_not']+=['不能因不是本人经历就actions=[]；明确答案仍用record_update。',
                         '不另起未登记故事，不让用户重说已存答案。']
        card['recording_rule']='明确几项便写几项record_update；全部完成后可show_review，核对与修改不同批。'
        card['material_fidelity_rule']={
            'rule':'把四要素分类与故事内容核对分开。teacher_examples.parts是固定故事依据；可接受忠实改写，不能把学习者新增的解释说成材料原文或称全部答对。必要时保留原作答并说明与材料的差别，不代写标准答案冒充本人。',
            'contrast':{'learner':'他认为自己白跑了、很倒霉，是想法。',
                'guidance':'可说明这类判断属于想法；但这份故事给出的具体想法是“今天的安排全乱了”，新增判断不是故事已给事实。不要答“对，这就是故事里老李的想法”。'}}
    material = _material(phase, state)
    if phase in {'check', 'check_feedback'}:
        card['practice_record_fields']=card.pop('fields')
        card['fields']={}
        attempt = state.course.retry if state.course.retry.status == 'active' else state.course.first
        questions, story = (RETRY_QUESTIONS, STORY_B) if state.course.retry.status == 'active' else (QUESTIONS, STORY_A)
        if attempt.status == 'active' and attempt.index < len(questions):
            q = questions[attempt.index]
            card['current_question']={'index':attempt.index,'field':q['field'],'prompt':q['prompt']}
            body = story + '\n\n' + q['prompt']
            if attempt.index in attempt.hints: body += '\n提示：' + q['hint']
            material = ('check-current', body)
    if material:
        card['current_material_ref'] = material[0]
        card['materials'][material[0]] = material[1]
        card['material_delivery']['current_page_material_ref']=material[0]
    if phase=='practice':
        card['askable_record_fields_before_turn']=[f for f in ('situation','thought','emotion','behavior')
            if fields.get(f,{}).get('ask_allowed')]
        card['reply_task']='回应本轮已答/求助，再按提交后缺项选一个焦点；本轮新答项和暂留项不再追问。四项齐全转未定评分，评分齐全/暂留后整理实际记录供核对，不邀请重做本人或课程例子；不预先提供后续项答案。'
    for op in operations:
        target = TARGETS.get(op, phase)
        effect = {'phase': target, **EFFECT_FLAGS.get(op, {})}
        if op == 'finish': effect['session_status'] = 'completed'
        if op in {'check_answer', 'skip_check', 'adopt_check_answer'}:
            retry = state.course.retry.status == 'active'
            attempt = state.course.retry if retry else state.course.first
            effect.update(question='next', phase='check_feedback' if attempt.index + 1 == (2 if retry else 4) else phase)
            target = effect['phase']
        if op in {'stage_check_answer', 'stage_goal'}: effect = {'phase': phase, 'formal_adoption': False}
        if op == 'choose_fictional': effect['case_kind'] = 'fictional'
        if op == 'choose_personal': effect['case_kind'] = 'personal'
        description = {'preconditions': PRECONDITIONS.get(op, '只使用当前目录中仍有效的目标和本人依据。'),
                       'effect': effect, 'reply_task': GOALS[target]}
        if op in {'weekly_score', 'skip_weekly', 'start_learning'}:
            description['reply_task'] = '首次进入概念学习时讲解小林的标准示范；末尾可说“接下来可以换一个例子，也可以举一件最近让你困扰的事，我们一起看看”。材料已讲过则只承接，不重贴；不要开始索取个人练习。周分三档的一句衔接由程序加入，模型正文不再重复评分/感谢/关怀。'
        if op == 'choose_fictional':
            description['reply_task'] = '确认改用指定课程例子；若故事尚未在对话展示，先给出指定故事再问情境，让用户尝试，不先给分类答案。已展示则不重贴；明确要求讲解/求助时提供相应帮助。'
        if op in {'choose_personal','start_practice'}:
            description['reply_task'] = '若尚未有事件，邀请举一件近期困扰；已经描述就先自然承接，糟心时可关怀，再请本人从已描述内容辨别一个缺项，不让其重讲故事、不代分四项。已主动分类的项接住，不套旧人物。'
        if op=='confirm_record':
            description['reply_task']='只保存确认操作；正文直接自然引入下一教学环节的内容/目的，不另发确认话术、不重贴记录、不默认邀请继续聊原事件。当前仅一次课程动作，不提前出尚未开始的检验题；下一回合用start_check继续。'
        if op in {'check_answer', 'skip_check', 'adopt_check_answer'}:
            questions, story = (RETRY_QUESTIONS, STORY_B) if retry else (QUESTIONS, STORY_A)
            next_index = attempt.index + 1
            material = ('check-next', story + '\n\n' + questions[next_index]['prompt']) if next_index < len(questions) else None
            effect['question_index']=next_index
            effect['answer_count_increased']=op in {'check_answer','adopt_check_answer'}
            feedback=('答对简要肯定；答错/部分符合先解释并给出本题正确理解；均不要求重答。'
                      if op!='skip_check' else '确认本题跳过，不当作答错。')
            description['reply_task']=feedback+('随后只询问material_ref指向的实际下一题，不提前给后续题答案。'
                if material else '本次检验已结束，简要反馈并自然衔接目标，不主动推荐再练，不再提出新题。')
        elif op == 'start_retry':
            material = ('check-retry', STORY_B + '\n\n' + RETRY_QUESTIONS[0]['prompt'])
        elif op == 'check_hint':
            material = None  # The hint appears after adoption, never preloaded as an answer key.
            effect['question_index']=attempt.index
            description['reply_task']='只解释/提示当前题，不保存作答或推进题号；等待下一条输入重新判断作答、继续求助、跳过或交流。'
        else:
            material = _material(target, state, fictional=op == 'choose_fictional' if op in {'choose_fictional','choose_personal'} else None)
        if material:
            description['material_ref'] = material[0]
            if phase in {'practice','review'} and op in {'choose_fictional','choose_personal'}:
                description['material_delivery']='仅本人明确改选后展示；不是当前案例的下一项任务。'
            else:card['materials'][material[0]] = material[1]
        card['operations'][op] = description
    card['concept_rubric'] = deepcopy(RUBRIC)
    card['teacher_examples'] = teacher_examples(card['materials'])
    return card
