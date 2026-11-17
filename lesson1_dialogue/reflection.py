"""Conditional post-commit reflection: sourced strategy hypotheses, no fact writes."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, ValidationError
from lesson1_contracts.models import Quote, StrictModel
from .contracts import DialogueError, checked_state
from .engine import _id, context_facts, fingerprint
from .models import State, ReflectionFinding, StrategyCandidate

REFLECTION_VERSION = 'lesson1-dialogue-reflection/1.0'
REFLECTION_PROMPT = '''你是第一课提交后的互动复盘器R。主回复及正式状态已经保存；只核对实际记录，提出供下一轮参考的局部策略候选。
只输出给定Schema的JSON。findings描述观察到的互动问题或有效做法；strategy_candidates是带范围的建议，不是用户事实或永久偏好。
核对用户明确提出的全部评分/边界是否实际保存，尤其两项同时暂留、暂不回课、回课轮补0分应先暂存再采用。区分聊天文字记得与正式状态已存。
整理记录允许语义等价，不因省略人称判错；关注人物、否定、分数/对象及授权是否改变。检查讲解是否与确定例子划分一致。
本人案例先承接叙述再引导本人辨别，不能把Agent代分四项当本人已答。参考activity_id和record_confirmed：确认已完成就不再建议回看核对；下一轮专用任务建议用current_task，已有评分暂留等硬边界继续由正式状态约束。
每项findings和建议都要引用source_catalog的ref_id与连续原句；可以引用用户和Agent原句。没有问题可返回空列表，不为凑建议编造事实。
不得输出动作、改写回复、修改本人事实/评分/边界/进度、解除拒绝、替用户确认或自动跨课采用。用户新边界优先于历史建议；尽量使用current_task/current_case，确属本课持续策略才用current_lesson。
建议短而具体，指出下轮应如何回应。不要让用户填写工程字段、不要把材料人物当本人。'''.strip()


class Proof(StrictModel):
    ref_id: str
    quote: Quote


class Finding(StrictModel):
    text: Quote
    evidence: list[Proof] = Field(min_length=1, max_length=6)


class Recommendation(StrictModel):
    guidance: Quote
    scope: Literal['current_task', 'current_case', 'current_lesson']
    evidence: list[Proof] = Field(min_length=1, max_length=6)


class ReflectionOutput(StrictModel):
    protocol_version: Literal['lesson1-dialogue-reflection/1.0']
    findings: list[Finding] = Field(max_length=4)
    strategy_candidates: list[Recommendation] = Field(max_length=3)


def context_fingerprint(state, scope):
    facts = context_facts(state)
    data = {'participant': state.participant_id, 'conversation': state.conversation_id,
            'case': state.active_case_id, 'fields': state.field_versions,
            'boundaries': facts['boundaries'], 'session_status': state.session_status,
            'mode': state.flow_mode, 'goal_revision': state.course.goal_revision,
            'record_confirmation':state.course.confirmation.fingerprint if state.course.confirmation else None}
    if scope == 'current_task':
        data['task'] = state.lesson_progress.model_dump()
    if scope in {'current_task','current_case'}:
        data['phase']=state.lesson_progress.phase
    return fingerprint(data)


def applicable_strategies(state):
    """Recheck sources, revision TTL and the authoritative state on every read."""
    state = checked_state(state)
    messages = {m.message_id: m for m in state.conversation_history}
    valid = []
    for item in state.strategy_candidates:
        if not 0 <= state.revision - item.origin_revision <= 6:
            continue
        if item.case_id != state.active_case_id:
            continue
        if item.context_fingerprint != context_fingerprint(state, item.scope):
            continue
        if any(e.source_message_id not in messages or e.quote not in messages[e.source_message_id].text
               for e in item.sources):
            continue
        valid.append(item)
    return valid[-4:]


def build_reflection_request(state, job):
    from .runtime import CallRequest
    from .examples import RUBRIC, teacher_examples
    from .context import provenance_view
    sources = {}
    catalog = []
    for index, message in enumerate(state.conversation_history, 1):
        ref = ('u' if message.role == 'learner' else 'g') + str(index)
        sources[ref] = message
        catalog.append({'ref_id': ref, 'speaker': message.role, 'text': message.text,
                        **provenance_view(state,message)})
    facts = context_facts(state)
    context = {'question': job.question, 'scope_limit': job.scope,
               'source_catalog': catalog, 'last_exchange': catalog[-2:],
               'committed_mode': state.flow_mode, 'phase': state.lesson_progress.phase,
               'case_kind': state.case_kind,
               'records': {f: v.value for f, v in state.records.items()},
               'ratings': {f: v.value for f, v in state.ratings.items()},
               'fields': facts['fields'], 'boundaries': facts['boundaries'],
               'pending_evidence': facts['pending_evidence'],
               'last_turn': state.turn_events[-1].model_dump(), 'concept_rubric': RUBRIC}
    from .course import record_fingerprint
    context.update(activity_id=state.lesson_progress.activity_id,
        record_confirmed=bool(state.course.confirmation and
            state.course.confirmation.fingerprint==record_fingerprint(state.model_dump())))
    if state.lesson_progress.phase in {'learn', 'practice', 'review'}:
        context['teacher_examples'] = teacher_examples(['concepts', 'practice-library'])
    return CallRequest(REFLECTION_PROMPT, context, ReflectionOutput.model_json_schema(),
                       purpose='dialogue_reflection'), sources


def finish_reflection(state, job_id, client):
    """Caller first persists attempted/running; one call, failure never undoes a turn."""
    before = checked_state(state)
    data = before.model_dump(mode='json')
    job = next((j for j in before.reflection_jobs if j.id == job_id), None)
    if job is None or job.status != 'running' or not job.attempted:
        raise DialogueError('reflection_not_claimed')
    stored = next(j for j in data['reflection_jobs'] if j['id'] == job_id)
    audit = {'job_id': job_id, 'status': 'running', 'model_calls': 0}
    try:
        request, sources = build_reflection_request(before, job)
        if len(request.system_prompt)+len(json.dumps(request.context,ensure_ascii=False))+len(json.dumps(request.output_schema,ensure_ascii=False))>200_000:
            raise DialogueError('reflection_context_limit')
        audit['model_calls'] = 1
        raw = client.complete(request)
        # Match main-wire parsing: reject duplicate keys and additional write fields.
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result: raise DialogueError('reflection_duplicate_key')
                result[key] = value
            return result
        if isinstance(raw, str): raw = json.loads(raw, object_pairs_hook=pairs)
        output = ReflectionOutput.model_validate(raw)
        def bind(evidence):
            result = []
            for proof in evidence:
                message = sources.get(proof.ref_id)
                if message is None or proof.quote not in message.text:
                    raise DialogueError('reflection_source_quote_or_missing')
                result.append({'source_message_id': message.message_id, 'quote': proof.quote})
            return result
        findings = [ReflectionFinding(text=f.text, sources=bind(f.evidence)).model_dump()
                    for f in output.findings]
        candidates = []
        for index, item in enumerate(output.strategy_candidates):
            if job.scope == 'current_task' and item.scope != 'current_task':
                raise DialogueError('reflection_scope_expansion')
            if job.scope == 'current_case' and item.scope == 'current_lesson':
                raise DialogueError('reflection_scope_expansion')
            candidates.append(StrategyCandidate(id=_id('strategy', job_id, str(index)), job_id=job_id,
                guidance=item.guidance, scope=item.scope, case_id=before.active_case_id,
                task_revision=before.lesson_progress.task_revision, origin_revision=before.revision,
                context_fingerprint=context_fingerprint(before, item.scope), sources=bind(item.evidence)).model_dump())
        stored.update(status='completed', findings=findings, error_code=None)
        data['strategy_candidates'].extend(candidates)
        audit.update(status='completed', findings=findings, strategy_count=len(candidates))
    except Exception as error:
        code = error.code if isinstance(error, DialogueError) else type(error).__name__
        stored.update(status='failed', error_code=code)
        audit.update(status='failed', error_code=code)
    return State.model_validate(data), audit
