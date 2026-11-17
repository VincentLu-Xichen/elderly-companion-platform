"""Model protocol v2: program catalogs, branch schemas and trusted event binding.

The internal 1.2 event format remains private to the executor/explicit controls.
No legacy model-output repair or fallback is performed here.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Annotated, Literal, Union, get_args

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, create_model
from lesson1_contracts.models import Identifier, Numeric, Quote, ReplyText, StrictModel
from .contracts import DialogueError, checked_message, checked_state
from .models import CONTRACT_VERSION, RECORD_FIELDS, SUBJECTS

WIRE_VERSION = 'lesson1-dialogue-wire/2.6'


def _literal(values):
    return Literal[tuple(values)]


def _union(variants, discriminator=None):
    if len(variants) == 1:
        return variants[0]
    result = Union[tuple(variants)]
    return Annotated[result, Field(discriminator=discriminator)] if discriminator else result


def _type(name, **fields):
    return create_model(name, __base__=StrictModel, **fields)


class WireContract:
    def __init__(self, state, message):
        from .engine import context_facts
        self._state = checked_state(state)
        self._message = checked_message(self._state, message)
        self._data = self._state.model_dump(mode='json')
        self._facts = context_facts(self._state)
        self._sources = {}
        self._catalog = []
        for index, item in enumerate([*self._state.conversation_history, self._message], 1):
            ref = ('u' if item.role == 'learner' else 'g') + str(index)
            self._sources[ref] = item
            entry = {'ref_id': ref, 'speaker': item.role, 'sequence': item.sequence,
                     'timing': 'current' if item.message_id == self._message.message_id else 'history',
                     'origin': 'material' if item.material_id is not None else 'message', 'text': item.text}
            from .context import provenance_view
            entry.update(provenance_view(self._state,item,current=item.message_id==self._message.message_id))
            if item.case_id is not None:
                entry['case_membership'] = 'current' if item.case_id == self._state.active_case_id else 'other'
            else:
                entry['case_membership'] = 'not_program_confirmed'
            self._catalog.append(entry)
        self._source_alias = {item.message_id: ref for ref, item in self._sources.items()}
        self._current_refs = tuple(ref for ref, item in self._sources.items()
                                   if item.message_id == self._message.message_id
                                   and item.role == 'learner' and item.material_id is None)
        self._boundaries = {'b'+str(i): b for i, b in enumerate(self._facts['boundaries'], 1)}
        self._subjects = {'subject-'+field: item for field, item in self._state.records.items()
                          if field in SUBJECTS.values()}
        self._pending = {}
        for item in self._facts['pending_evidence']:
            if item['is_current']:
                self._pending['p'+str(len(self._pending)+1)] = {'kind': 'record', 'item': item}
        self._add_course_pending()
        self._case_choices={'case-choice-'+str(i):item.model_dump() for i,item in enumerate(
            [p for p in self._state.case_choices if p.status=='pending' and p.origin_case_id==self._state.active_case_id],1)}
        from .context import planned_case_id
        self._planned_case_id=planned_case_id(self._state,self._message)
        self._type_cache = {}
        self._operations = set()
        self._course_operations = {'formal':set(),'staging':set()}
        self._branches = []
        self._record_audit = []
        variants = self._output_variants()
        self._adapter = TypeAdapter(_union(variants))

    @property
    def state(self):
        return self._state.model_copy(deep=True)

    def _evidence(self, current=True):
        key = ('evidence', current)
        if key not in self._type_cache:
            refs = self._current_refs if current else tuple(self._sources)
            if not refs:
                return None
            self._type_cache[key] = _type('CurrentEvidence' if current else 'CatalogEvidence',
                ref_id=(_literal(refs), Field(description='程序来源目录的ref_id；不是消息UUID或自造ID。')),
                quote=(Quote, Field(description='所选消息中的连续原句，不改写、不代替本人表达。')))
        return self._type_cache[key]

    def _add_course_pending(self):
        from .course import current_check
        for item in self._data['course']['pending_responses']:
            if item['status'] != 'pending' or item['task_revision'] != self._state.lesson_progress.task_revision:
                continue
            content = item['content']
            messages = {m.message_id: m for m in self._state.conversation_history}
            if any(s['source_message_id'] not in messages or messages[s['source_message_id']].role != 'learner'
                   or messages[s['source_message_id']].material_id is not None
                   or s['quote'] not in messages[s['source_message_id']].text for s in item['sources']):
                continue
            if content['operation'] == 'stage_goal':
                fresh = (self._state.lesson_progress.phase == 'learning_goal'
                         and content['expected_goal_revision'] == self._state.course.goal_revision)
                kind = 'goal'
            else:
                key, attempt, _, _ = current_check(self._data)
                fresh = (self._state.lesson_progress.phase in {'check', 'check_feedback'}
                         and attempt['status'] == 'active' and content['attempt_id'] == key
                         and content['question_index'] == attempt['index'])
                kind = 'check'
            if fresh:
                self._pending['p'+str(len(self._pending)+1)] = {'kind': kind, 'item': item}

    def _action(self, name, kind, payload, *, evidence=True, record_evidence=False, evidence_description=None):
        fields = {'id': (Identifier, Field(description='只用于同批depends_on的动作编号，如a1。')),
                  'type': (Literal[kind], ...), 'payload': (payload, ...),
                  'depends_on': (list[Identifier], Field(default_factory=list, max_length=8))}
        if evidence:
            ref = self._write_evidence() if record_evidence else self._evidence()
            if ref is None:
                return None
            fields['evidence'] = (list[ref], Field(min_length=1, max_length=6, description=evidence_description))
        else:
            fields['evidence'] = (list[self._evidence(False)],Field(default_factory=list,max_length=6,
                description='可省略。若重复附来源，必须与候选的已存原句/来源完全一致；程序始终采用已存来源。'))
        return _type(name, **fields)

    def _write_evidence(self):
        refs=set(self._current_refs)
        if self._state.flow_mode=='teaching':
            refs.update(ref for ref,item in self._sources.items() if item.role=='learner' and item.material_id is None)
        if self._state.case_story:
            refs.update(self._source_alias[e.source_message_id] for e in self._state.case_story.sources)
        return _type('CourseEvidence',ref_id=(_literal(tuple(sorted(refs))),...),
            quote=(Quote,Field(description='本轮原句，或已明确选为课程案例的story原句范围；不能借机引用无关历史。')))

    def _case_change(self, staging):
        if self._state.lesson_progress.phase not in {'learn','practice','review'}:return None
        refs=tuple(ref for ref,item in self._sources.items() if item.role=='learner' and item.material_id is None)
        proof=_type('CaseStoryEvidence',ref_id=(_literal(refs),...),quote=(Quote,...))
        op='stage' if staging else 'select'
        payload=_type('ChooseCase_'+op,operation=(Literal[op],...),
            story_evidence=(list[proof],Field(min_length=1,max_length=6,
                description='本人明确选择用来练习的事件原句，和当前选择意愿的evidence分开。')))
        variants=[self._action('CaseChange_'+op,'case_change',payload,evidence_description=
            '仅引用本轮本人明确选择“把哪件事用于课程练习”的意愿片段；这不是新事件记录。'
            '只想聊天、叙述新事件、暂不回课时不输出此动作；故事原句另放story_evidence。')]
        if not staging and self._case_choices:
            adoption=_type('AdoptCaseChoice',operation=(Literal['adopt'],...),
                pending_ref=(_literal(tuple(self._case_choices)),...))
            variants.append(self._action('AdoptCase','case_change',adoption,evidence=False))
        return _union(variants)

    def _boundary(self, excluded=()):
        key = ('boundary', tuple(sorted(excluded)))
        if key in self._type_cache:
            return self._type_cache[key]
        payloads = []
        def add(name, kind, target, scope):
            if kind not in excluded:
                payloads.append(_type(name, kind=(Literal[kind], ...), target_ref=(target, ...), scope=(scope, ...)))
        add('DeferField', 'defer_field', _literal((*RECORD_FIELDS, *SUBJECTS)), Literal['current_case'])
        add('StopCaseQuestions', 'stop_case_questions', Literal['case-current'], Literal['current_case'])
        for kind in ('no_personal_case', 'return_not_now', 'pause_lesson'):
            add('LessonBoundary_'+kind, kind, Literal['lesson'], Literal['current_lesson'])
        topics = sorted({b['content']['target_ref'] for b in self._boundaries.values()
                         if b['content']['kind'] == 'stop_topic_questions'})
        # No invented topic registry: only already-known targets/scopes can be selected.
        for index, target in enumerate(topics):
            scopes = sorted({b['content']['scope'] for b in self._boundaries.values()
                             if b['content']['kind'] == 'stop_topic_questions' and b['content']['target_ref'] == target})
            if 'stop_topic_questions' not in excluded:
                payloads.append(_type('KnownTopic_'+str(index), kind=(Literal['stop_topic_questions'], ...),
                    target_ref=(Literal['topic-'+str(index+1)], ...), scope=(_literal(scopes), ...)))
        # Topic variants share a kind and therefore use anyOf, not a false kind discriminator.
        payload = _union(payloads, None if topics else 'kind')
        action = self._action('SetBoundary_'+str(len(self._type_cache)), 'set_boundary', payload)
        self._type_cache[key] = action
        return action

    def _release(self):
        refs = tuple(ref for ref, b in self._boundaries.items() if b['content']['kind'] != 'pause_lesson')
        if not refs or self._state.flow_mode == 'paused':
            return None
        payload = _type('ReleaseBoundaryPayload', boundary_ref=(_literal(refs), ...),
                        basis=(Literal['explicit_permission'], 'explicit_permission'))
        return self._action('ReleaseBoundary', 'release_boundary', payload)

    def _write(self, staging=False):
        from .context import response_scope
        variants = []
        case = Literal['case-current'] if staging else Literal['case-current','case-next']
        record = _type('RecordValue', case_ref=(case, ...), field=(_literal(RECORD_FIELDS), ...), value=(Quote, ...))
        payloads = [record]
        if self._state.case_kind == 'personal':
            for field, subject in SUBJECTS.items():
                common = {'case_ref': (case, ...), 'field': (Literal[field], ...),
                          'value': (Numeric, Field(ge=0, le=10)),
                          'scale_id': (Literal['course-0-10'], 'course-0-10')}
                if 'subject-'+subject in self._subjects:
                    payloads.append(_type('ExistingScore_'+field, **common,
                        subject_ref=(Literal['subject-'+subject], ...)))
                # Staged scores cannot reference a not-yet-adopted new object.
                if not staging:
                    payloads.append(_type('NewSubjectScore_'+field, **common,
                        subject_action_id=(Identifier, Field(description='同批更新对应想法/情绪的动作ID，必须列入depends_on。'))))
        if staging:
            variants.append(self._action('StageEvidence', 'stage_evidence', _union(payloads),record_evidence=True))
        else:
            variants.append(self._action('RecordUpdate', 'record_update', record,evidence_description=
                '引用本轮学习者的辨别作答、主动分类或更正；初始事件叙述仅留作上下文，不由Agent代分四项后当作已完成。'))
            if len(payloads) > 1:
                variants.append(self._action('ScoreUpdate', 'score_update', _union(payloads[1:])))
            refs = tuple(ref for ref, entry in self._pending.items() if entry['kind'] == 'record')
            if refs:
                payload = _type('AdoptPendingPayload', pending_ref=(_literal(refs), ...))
                variants.append(self._action('AdoptPending', 'adopt_pending', payload, evidence=False))
            steps = [_type('StepStayOrHelp', operation=(Literal['stay', 'help'], ...))]
            askable = tuple(field for field, view in self._facts['fields'].items() if view['ask_allowed'])
            if askable:
                steps.append(_type('StepSelect', operation=(Literal['select_field'], ...), next_field=(_literal(askable), ...)))
            variants.append(self._action('TeachingStep', 'teaching_step', _union(steps, 'operation')))
        if response_scope(self._state)['kind']=='unselected_material':
            # Discussion of an unselected example cannot write the personal case.
            # Keep teaching_step so a permitted current field can be refocused.
            variants=[v for v in variants if not staging and v.__name__=='TeachingStep']
        return [v for v in variants if v is not None]

    def _course(self, staging=False):
        if not self._state.course.enabled:
            return None
        from .controls import available_controls
        from .course import PHASE_MOVES, current_check
        phase = self._state.lesson_progress.phase
        payloads = []
        def add(op, **fields):
            self._operations.add(op)
            self._course_operations['staging' if staging else 'formal'].add(op)
            payloads.append(_type('Course_'+op, operation=(Literal[op], ...), **fields))
        if staging:
            if phase in {'check', 'check_feedback'}:
                _, attempt, _, _ = current_check(self._data)
                if attempt['status'] == 'active': add('stage_check_answer', value=(Quote, ...))
            elif phase == 'learning_goal': add('stage_goal', value=(Quote, ...))
        else:
            controls = set(available_controls(self._state))
            for op in PHASE_MOVES[phase]:
                # UI buttons are a subset: explicit language can also request a case
                # change while reviewing. Keep the typed course capability intact.
                if op in controls or op in {'choose_fictional','choose_personal'}: add(op)
            if phase == 'check_in': add('weekly_score', value=(Numeric, Field(ge=1, le=10)))
            if phase == 'review' and 'confirm_record' in controls: add('confirm_record')
            if phase in {'check', 'check_feedback'}:
                _, attempt, _, _ = current_check(self._data)
                if attempt['status'] == 'active':
                    add('check_answer', verdict=(Literal['matches','partial','does_not_match','unclear'], ...), reason=(Quote, ...))
                    refs = tuple(ref for ref, item in self._pending.items() if item['kind'] == 'check')
                    if refs:
                        add('adopt_check_answer', pending_ref=(_literal(refs), ...),
                            verdict=(Literal['matches','partial','does_not_match','unclear'], ...), reason=(Quote, ...))
            if phase == 'learning_goal':
                add('set_goal', value=(Quote, ...))
                if self._state.course.goal is not None: add('confirm_goal')
                refs = tuple(ref for ref, item in self._pending.items() if item['kind'] == 'goal')
                if refs: add('adopt_goal', pending_ref=(_literal(refs), ...))
        if not payloads:
            return None
        # Adoption carries trusted evidence from the candidate, not rewritten model evidence.
        ordinary = [p for p in payloads if p.model_fields['operation'].annotation.__args__[0] not in {'adopt_check_answer','adopt_goal'}]
        adopting = [p for p in payloads if p not in ordinary]
        variants = []
        if ordinary:
            variants.append(self._action('CourseAction', 'course_action', _union(ordinary, 'operation')))
        if adopting:
            variants.append(self._action('AdoptCourseResponse', 'course_action', _union(adopting, 'operation'), evidence=False))
        return _union([v for v in variants if v is not None]) if any(variants) else None

    def _actions(self, *, formal=False, staging=False, invite=False, stopping=False, resuming=False):
        excluded = set() if stopping else {'pause_lesson'}
        if invite or resuming: excluded.add('return_not_now')
        variants = [self._boundary(excluded), self._release()]
        if self._state.lesson_progress.phase in {'learn','practice','review'}:
            if self._case_choices:
                payload=_type('CancelCaseChoice',pending_ref=(_literal(tuple(self._case_choices)),...))
                variants.append(self._action('CancelChoice','cancel_case_choice',payload))
            existing=tuple([*self._state.records,*self._state.ratings])
            if existing:
                payload=_type('RemoveRecord',case_ref=(Literal['case-current'],...),field=(_literal(existing),...))
                variants.append(self._action('RemoveRecordAction','record_remove',payload,evidence_description=
                    '引用本人删除要求。若还要求晚点补，另加同字段defer_field；删除和暂留可同批，不能漏掉后者。'))
        if formal:
            if self._state.lesson_progress.phase in {'learn','practice','review'}:
                variants += self._write()
            variants.append(self._course())
            variants.append(self._case_change(False))
        if staging:
            variants.append(self._case_change(True))
            # Record candidates are meaningful only in record phases.
            if self._state.lesson_progress.phase in {'learn','practice','review'}:
                variants += self._write(staging=True)
            variants.append(self._course(staging=True))
        if invite:
            variants.append(self._action('InviteReturn', 'invite_return', _type('InvitePayload')))
        return [v for v in variants if v is not None]

    def _branch(self, name, signal, actions, *, bridge=False, resume_basis=None, resume_target=None,
                requires_candidate=False, invite=False, requires_return_refusal=False):
        current = self._evidence()
        if signal != 'none' and current is None:
            return None
        schema_checks = []
        course_match = {'properties': {'type': {'const': 'course_action'}}, 'required': ['type']}
        schema_checks.append({'contains': course_match, 'minContains': 0, 'maxContains': 1})
        schema_checks.append({'contains':{'properties':{'type':{'const':'case_change'}},'required':['type']},
                              'minContains':0,'maxContains':1})
        for score, subject in SUBJECTS.items():
            def staged(field):
                return {'contains': {'properties': {'type': {'const':'stage_evidence'},
                    'payload': {'properties': {'field': {'const':field}}, 'required':['field']}},
                    'required':['type','payload']}}
            schema_checks.append({'not': {'allOf': [staged(subject), staged(score)]}})
        if invite:
            schema_checks.append({'contains': {'properties': {'type': {'const': 'invite_return'}}, 'required':['type']},
                                  'minContains': 1, 'maxContains': 1})
        if requires_return_refusal:
            schema_checks.append({'contains': {'properties': {
                'type': {'const': 'set_boundary'}, 'payload': {'properties': {
                    'kind': {'const': 'return_not_now'}}, 'required': ['kind']}},
                'required': ['type','payload']}, 'minContains': 1})
        if requires_candidate:
            schema_checks.append({'contains': {'anyOf': [
                {'properties': {'type': {'const':'stage_evidence'}}, 'required':['type']},
                {'properties': {'type': {'const':'course_action'}, 'payload': {'properties': {
                    'operation': {'enum':['stage_check_answer','stage_goal']}}, 'required':['operation']}},
                 'required':['type','payload']}]}, 'minContains': 1})
        fields = {'protocol_version': (Literal[WIRE_VERSION], ...),
                  'based_on_revision': (Literal[self._state.revision], ...),
                  'signal': (Literal[signal], ...),
                  'bridge_ready': (Literal[bridge], ... if bridge else False),
                  'actions': (list[_union(actions)] if actions else list[object],
                      Field(..., max_length=8 if actions else 0,
                            json_schema_extra={'allOf': schema_checks})),
                  'reply': (ReplyText, Field(pattern=r'^[^?？]*[?？][^?？]*$') if invite else ...)}
        if current is not None:
            fields['signal_evidence'] = (list[current], Field(min_length=0 if signal == 'none' else 1, max_length=6,
                                                             default_factory=list) if signal == 'none' else Field(min_length=1,max_length=6))
        if resume_basis:
            fields.update(resume_basis=(Literal[resume_basis], ...), resume_target=(resume_target, ...))
        if self._sources:
            reflection = _type('ReflectionRequest', question=(Quote, ...),
                scope=(Literal['current_task','current_case','current_lesson'], ...),
                evidence=(list[self._evidence(False)], Field(min_length=1, max_length=6)))
            fields['reflection_request'] = (reflection | None, None)
        if current is not None:
            tag_evidence=_type('CurrentTagEvidence',quote=(Quote,Field(
                description='只摘录本轮用户的连续原句；消息身份由程序绑定，不填写ref_id，不给历史内容补标签。')))
            tag=_type('ContextTag',relation=(Literal['course_case','conversation_event','uncertain','quoted_example'],...),
                      evidence=(tag_evidence,...))
            fields['context_tags']=(list[tag],Field(default_factory=list,max_length=12))
        def models(annotation):
            if isinstance(annotation,type) and issubclass(annotation,BaseModel):yield annotation
            else:
                for argument in get_args(annotation):yield from models(argument)
        allowed={}
        for variant in actions:
            for model in models(variant):
                kind=get_args(model.model_fields['type'].annotation)[0]
                operations=allowed.setdefault(kind,set())
                for payload in models(model.model_fields['payload'].annotation):
                    if 'operation' in payload.model_fields:
                        operations.update(get_args(payload.model_fields['operation'].annotation))
        formal=name in {'Teaching','RedundantResume'}
        if signal=='needs_switch':reply_task='围绕当前困扰提供支持，先承接并主动选择相关澄清或帮助；普通支持不播报“先不回课”，原题补答仅暂存，不继续教学追问。'
        elif self._state.flow_mode=='communicating' and signal=='resume_request':
            reply_task='自然确认本人愿意返回、说明已有内容保留；本轮不索取下一道教学答案或评分，下轮才用教学Prompt。'
        elif invite:reply_task='自然承接已有支持、情绪缓和或话题收束的依据，再仅询问是否愿意返回；不把缓和当同意，不夹带课程题目或评分。'
        elif formal and self._state.lesson_progress.phase in {'check','check_feedback'}:
            reply_task='按所选操作的reply_task反馈：作答判读后进入下一题，求助提示后等待；不要求已经判读的同一题重答。'
        elif formal:reply_task='按当前阶段卡和实际保存结果教学；课程人物的明确答案也写学习记录。'
        elif self._state.flow_mode=='communicating':reply_task='围绕当前困扰提供情绪支持，主动选择有用的澄清、梳理或小步骤；不反复索取已说感受，不播报课程位置，尊重倾听/停止意愿。'
        else:reply_task='承接当前表达；不索取课程缺项，不以旧任务替代本轮诉求。'
        if requires_return_refusal:reply_task='已有缓和或收束依据，但本轮本人明确暂不返回；保存return_not_now，不发邀请，继续按其需要支持或自然收束。'
        self._branches.append({'name': name, 'signal': signal, 'bridge_ready': bridge,
                               'resume_basis': resume_basis,
                               'formal_teaching': formal,
                               'allowed_actions':[{'type':kind,'operations':sorted(ops)} for kind,ops in allowed.items()],
                               'course_operations':sorted(allowed.get('course_action',set())),
                               'reply_task':reply_task,
                               'candidate_required': requires_candidate, 'invitation_required': invite,
                               'return_refusal_required':requires_return_refusal})
        return _type(name, **fields)

    def _invitation_ready(self):
        s = self._state; invitation = s.return_invitation
        return bool(s.flow_mode == 'communicating' and invitation is not None and invitation.status == 'pending'
                    and invitation.task_revision == s.lesson_progress.task_revision
                    and invitation.case_id == s.active_case_id and s.conversation_history
                    and s.conversation_history[-1].message_id == invitation.assistant_message_id)

    def _output_variants(self):
        from .engine import _active
        mode = self._state.flow_mode
        outputs = []
        def add(*args, **kwargs):
            item = self._branch(*args, **kwargs)
            if item is not None: outputs.append(item)
        if mode == 'teaching':
            add('Teaching', 'none', self._actions(formal=True))
            add('SwitchToChat', 'needs_switch', self._actions(staging=True))
            add('RedundantResume', 'resume_request', self._actions(formal=True, resuming=True),
                resume_basis='explicit_request', resume_target=Literal['teaching'])
        elif mode == 'communicating':
            blocked = any(_active(self._data, 'return_not_now')) or (
                self._state.return_invitation is not None and self._state.return_invitation.status == 'pending')
            add('Chat_none', 'none', self._actions(staging=True))
            if blocked:
                add('Chat_conversation_closed', 'conversation_closed', self._actions(staging=True))
            else:
                add('ClosedWithReturnRefusal','conversation_closed',self._actions(staging=True),requires_return_refusal=True)
            if not blocked:
                for signal in ('none','conversation_closed'):
                    add('Invite_'+signal, signal, self._actions(staging=True, invite=True), bridge=True, invite=True)
            for basis in ('explicit_request','invitation_answer'):
                if basis == 'invitation_answer' and not self._invitation_ready(): continue
                add('Resume_'+basis, 'resume_request', self._actions(staging=True, resuming=True),
                    resume_basis=basis, resume_target=Literal['teaching'], requires_candidate=basis == 'original_answer')
        else:
            add('Paused', 'none', self._actions())
            if self._state.paused_reason != 'safety':
                add('ResumePaused', 'resume_request', self._actions(resuming=True),
                    resume_basis='explicit_request', resume_target=Literal['previous_mode','teaching'])
        add('Pause', 'pause_request', self._actions(stopping=True))
        add('Close', 'close_request', self._actions(stopping=True))
        return outputs

    def schema(self):
        return copy.deepcopy(self._adapter.json_schema())

    def audit_view(self):
        """Encrypted server audit only; never sent to the model as a second ID system."""
        return {'protocol_version': WIRE_VERSION, 'based_on_revision': self._state.revision,
                'sources': {ref: item.message_id for ref, item in self._sources.items()},
                'case_refs': {'case-current': self._state.active_case_id},
                'boundaries': {ref: item['id'] for ref, item in self._boundaries.items()},
                'pending': {ref: entry['item']['id'] for ref, entry in self._pending.items()},
                'subjects': {ref: {'field': ref.removeprefix('subject-'), 'revision': item.revision}
                             for ref, item in self._subjects.items()},
                'field_versions': copy.deepcopy(self._state.field_versions),
                'task_revision': self._state.lesson_progress.task_revision,
                'goal_revision': self._state.course.goal_revision,
                'record_review': copy.deepcopy(self._record_audit),
                'case_choices':{ref:p['id'] for ref,p in self._case_choices.items()}}

    def _visible_evidence(self, sources):
        return [{'ref_id': self._source_alias[s['source_message_id']], 'quote': s['quote']}
                for s in sources if s['source_message_id'] in self._source_alias]

    def context(self):
        from .stage_cards import build_stage_card
        state = self._state
        records = {f: {'value': r.value, 'evidence': self._visible_evidence([s.model_dump() for s in r.sources])}
                   for f, r in state.records.items()}
        ratings = {f: {'value': r.value, 'scale_id': r.scale_id, 'subject_ref': 'subject-'+r.subject_field,
                      'evidence': self._visible_evidence([s.model_dump() for s in r.sources])}
                   for f, r in state.ratings.items()}
        boundaries = []
        for alias, entry in self._boundaries.items():
            content = copy.deepcopy(entry['content'])
            if content['kind'] == 'stop_case_questions': content['target_ref'] = 'case-current'
            if content['kind'] == 'stop_topic_questions':
                targets = sorted({b['content']['target_ref'] for b in self._boundaries.values()
                                  if b['content']['kind'] == 'stop_topic_questions'})
                content['target_ref'] = 'topic-'+str(targets.index(content['target_ref'])+1)
            boundaries.append({'boundary_ref': alias, **content, 'evidence': self._visible_evidence(entry['sources'])})
        candidates = []
        for alias, entry in self._pending.items():
            item = entry['item'];content = item['content']
            candidates.append({'pending_ref': alias, 'kind': entry['kind'], 'field': content.get('field'),
                               'value': content.get('value'), 'is_current': True,
                               'evidence': self._visible_evidence(item['sources'])})
            if entry['kind']=='record':
                candidates[-1]['adoption_effect']={'releases_deferral_for':content['field'],
                    'other_field_deferrals':'unchanged'}
        course = None
        from .context import response_scope
        task_view={'phase': state.lesson_progress.phase, 'activity_id':state.lesson_progress.activity_id,
                   'field': state.lesson_progress.field, 'response_scope':response_scope(state),
                   'case_ref':'case-current','case_kind':state.case_kind}
        last_agent=next((entry['ref_id'] for entry in reversed(self._catalog[:-1])
                         if entry['speaker']=='agent'),None)
        if state.course.enabled:
            from .course import record_fingerprint, practice_progress
            if state.lesson_progress.phase in {'learn','practice','review'}:
                task_view['practice_progress']=practice_progress(self._data)
            c = state.course
            course = {'phase': state.lesson_progress.phase, 'case_kind': state.case_kind,
                      'weekly_score': c.weekly_score, 'weekly_skipped': c.weekly_skipped,
                      'record_confirmed': bool(c.confirmation and c.confirmation.fingerprint == record_fingerprint(self._data)),
                      'goal': c.goal.value if c.goal else None,
                      'goal_confirmed': bool(c.goal and c.goal_confirmed_revision == c.goal_revision),
                      'goal_skipped': c.goal_skipped, 'plan_status': c.plan_status,
                      'attempts': {}}
            for key in ('first','retry'):
                attempt = getattr(c,key)
                course['attempts'][key] = {'status': attempt.status, 'index': attempt.index,
                    'answers': [{'question_index': a.question_index, 'verdict': a.verdict, 'reason': a.reason,
                                 'assisted': a.assisted, 'prior_feedback': a.prior_feedback,
                                 'evidence': self._visible_evidence([s.model_dump() for s in a.sources])}
                                for a in attempt.answers]}
            from .course import context as course_context
            check=course_context(self._data).get('check')
            if check:
                course['current_question']=check
                task_view.update(field=check['field'],case_ref=None,case_kind='independent_material',
                    response_target='本轮是对当前检验题的回应；若内容是在作答，判读并保存check_answer，不重新发同一题。求助/倾诉不耗次数。')
        return {'control_view': {'protocol_version': WIRE_VERSION, 'revision': state.revision,
                    'flow_mode': state.flow_mode, 'paused_reason': state.paused_reason,
                    'suspended_mode': state.suspended_mode},
                'source_catalog': copy.deepcopy(self._catalog),
                'task_view':task_view,
                'dialogue_focus':{'last_agent_ref':last_agent,
                    'stop_scope_rule':'先读该条实际Agent消息：问还聊本事件吗，短拒绝只停止当前案例；明确问整次学习是否结束，短拒绝才按整次范围理解。仅当前状态/关键词不足以判断，确有歧义才自然澄清。'},
                'learner_facts': {'records': records, 'ratings': ratings, 'fields': copy.deepcopy(self._facts['fields'])},
                'resource_view': {'case_refs': ['case-current','case-next'] if state.flow_mode=='teaching'
                    and state.lesson_progress.phase in {'learn','practice','review'} else ['case-current'],
                    'subjects': [{'subject_ref': ref, 'field': ref.removeprefix('subject-'), 'value': r.value}
                                 for ref, r in self._subjects.items()],
                    'boundaries': boundaries, 'candidates': candidates,
                    'case_choices':[{'pending_ref':ref,'story':self._visible_evidence(item['sources'])}
                                    for ref,item in self._case_choices.items()],
                    'case_selection_rule':'没提新选择就保留现有pending；明确选用才case_change.stage，明确撤回才cancel_case_choice。两者都不是转交流所必需。',
                    'case_story':self._visible_evidence([s.model_dump() for s in state.case_story.sources]) if state.case_story else []},
                'capability_view': {'branches': copy.deepcopy(self._branches),
                    'context_tag_rule':'只标本轮用户原句，evidence仅填quote；当前消息身份由程序绑定，不填ref_id，不补历史标签。历史故事另用story_evidence。',
                    'adoption_source_rule':'adopt_pending/候选采用不需要evidence；若重复附证据，必须逐原句匹配已存来源，不能改来源或值。',
                    'constraints': ['仅当前本人原话可支持新事实/边界/授权。',
                        '候选采用只选择pending_ref，程序取原来源并重验版本。',
                        '同轮新对象评分必须depends_on对应subject_action_id。',
                        'depends_on只能引用本批现有动作且无环；边界不能依赖教学写入。',
                        '交流同轮新对象与新评分的成组候选暂未开放，不把新分数绑定旧对象。',
                        '同字段竞争写入、record_update/score_update/stage_evidence/adopt_pending与同字段暂留、修改并核对、换案并编辑、多个阶段动作整轮拒绝。',
                        'record_remove不是新增值：允许同字段record_remove加defer_field，分别落实“删除”和“晚点补”；仅删除不自动暂留。',
                        '邀请必须真实单一回课问题；已有邀请/拒绝时不重邀。',
                        '原句存在不证明语义归属，未知归属先澄清。',
                        'case_change.stage只存换案意向；select/adopt仅教学正式执行并归档旧案。',
                        'case-next写入必须同批依赖select/adopt，不能携带旧对象评分；story来源仅按选定范围授权。']},
                'return_invitation': {'pending': self._invitation_ready()},
                'stage_card': build_stage_card(state, sorted(self._course_operations[
                    'formal' if state.flow_mode=='teaching' else 'staging']) if state.flow_mode!='paused' else [], self._facts['fields']),
                'course': course, 'strategy_candidates': self._strategy_view()}

    def _strategy_view(self):
        from .reflection import applicable_strategies
        return [{'guidance': item.guidance, 'scope': item.scope, 'status': 'hypothesis',
                 'evidence': self._visible_evidence([e.model_dump() for e in item.sources])}
                for item in applicable_strategies(self._state)]

    def bind(self, raw):
        """Validate v2 and bind only program-owned technical facts to executor events."""
        if isinstance(raw, BaseModel): raw = raw.model_dump()
        if isinstance(raw, str):
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result: raise ValueError('duplicate key')
                    result[key] = value
                return result
            try: raw = json.loads(raw, object_pairs_hook=pairs)
            except (ValueError, TypeError) as error: raise DialogueError('wire_output_contract') from error
        if not isinstance(raw, dict) or type(raw.get('based_on_revision')) is not int:
            raise DialogueError('wire_output_contract')
        try: output = self._adapter.validate_python(copy.deepcopy(raw)).model_dump()
        except ValidationError as error: raise DialogueError('wire_output_contract') from error
        actions = output['actions']
        case_changes=[a for a in actions if a['type']=='case_change']
        if case_changes and any(a['type'] in {'cancel_case_choice','record_remove'} for a in actions):
            raise DialogueError('competing_case_controls')
        if len(case_changes)>1 or (case_changes and any(a['type']=='course_action' for a in actions)):
            raise DialogueError('competing_case_controls')
        adopting=case_changes[0] if case_changes and case_changes[0]['payload']['operation']!='stage' else None
        next_case_id=(self._case_choices[adopting['payload']['pending_ref']]['case_id']
                      if adopting and adopting['payload']['operation']=='adopt' else self._planned_case_id)
        if sum(a['type'] == 'course_action' for a in actions) > 1: raise DialogueError('multiple_course_actions')
        staged_fields = {a['payload']['field'] for a in actions if a['type'] == 'stage_evidence'}
        if any(score in staged_fields and subject in staged_fields for score, subject in SUBJECTS.items()):
            raise DialogueError('staged_subject_score_dependency_not_supported')
        invites = [a for a in actions if a['type'] == 'invite_return']
        if output['bridge_ready'] and len(invites) != 1: raise DialogueError('wire_invitation_required')
        if self._state.flow_mode=='communicating' and output['signal']=='conversation_closed':
            from .engine import _active
            blocked=any(_active(self._data,'return_not_now')) or (
                self._state.return_invitation is not None and self._state.return_invitation.status=='pending')
            refused=any(a['type']=='set_boundary' and a['payload']['kind']=='return_not_now' for a in actions)
            if not blocked and not refused and not invites:
                raise DialogueError('wire_closed_requires_invitation_or_refusal')
        if output.get('resume_basis') == 'original_answer' and not any(a['type'] == 'stage_evidence' or
                (a['type'] == 'course_action' and a['payload']['operation'] in {'stage_check_answer','stage_goal'}) for a in actions):
            raise DialogueError('original_answer_missing')
        refs = []
        def internal_refs(evidence=None, stored=None):
            ids = []
            for e in evidence or []:
                item = self._sources.get(e['ref_id'])
                if item is None or e['quote'] not in item.text: raise DialogueError('source_quote_or_missing')
                ids.extend(internal_refs(stored=[{'source_message_id': item.message_id, 'quote': e['quote']}]))
            for source in stored or []:
                msg = next((m for m in self._sources.values() if m.message_id == source['source_message_id']), None)
                if msg is None or source['quote'] not in msg.text: raise DialogueError('source_quote_or_missing')
                match = next((r for r in refs if r['source_message_id'] == source['source_message_id'] and r['quote'] == source['quote']), None)
                if match is None:
                    match = {'id': 'bound-'+str(len(refs)+1), **source};refs.append(match)
                ids.append(match['id'])
            if len(refs) > 24: raise DialogueError('wire_evidence_limit')
            return ids
        def adoption_refs(action,stored):
            if action.get('evidence'):
                actual={(self._sources[e['ref_id']].message_id,e['quote']) for e in action['evidence']}
                expected={(e['source_message_id'],e['quote']) for e in stored}
                if actual!=expected:raise DialogueError('adoption_evidence_mismatch')
            return internal_refs(stored=stored)
        result = {'contract_version': CONTRACT_VERSION, 'based_on_revision': self._state.revision,
                  'reply': output['reply'], 'signal': output['signal'], 'bridge_ready': output['bridge_ready'],
                  'signal_ref_ids': internal_refs(output.get('signal_evidence',[])), 'actions': []}
        for key in ('resume_target','resume_basis'):
            if key in output: result[key] = output[key]
        for action in actions:
            kind = action['type'];p = copy.deepcopy(action['payload'])
            ids = internal_refs(action.get('evidence',[]))
            if kind in {'record_update','score_update','stage_evidence'}:
                if p['field'] in RECORD_FIELDS:
                    evidence = copy.deepcopy(action['evidence'])
                    self._record_audit.append({'action_id': action['id'], 'field': p['field'],
                        'value': p['value'], 'evidence': evidence,
                        'verbatim': any(p['value'] in e['quote'] for e in evidence),
                        'semantic_review': 'pending_human_review'})
                new_case=p.pop('case_ref')=='case-next'
                if adopting and (not new_case or adopting['id'] not in action['depends_on']):
                    raise DialogueError('case_change_dependency_required')
                if new_case and adopting is None:raise DialogueError('case_next_requires_selection')
                if new_case and p.get('subject_ref'):raise DialogueError('new_case_old_subject')
                p.update(target_case_id=next_case_id if new_case else self._state.active_case_id,
                         expected_field_revision=0 if new_case else self._state.field_versions.get(p['field'],0))
                if p['field'] in SUBJECTS:
                    p['quote'] = self._number_quote(action['evidence'], p['value'])
                    if 'subject_ref' in p:
                        subject = self._subjects[p.pop('subject_ref')]
                        p['subject_revision'] = subject.revision
                    p['scale_id'] = 'course-0-10'
            elif kind=='record_remove':
                p.pop('case_ref');p.update(target_case_id=self._state.active_case_id,
                    expected_field_revision=self._state.field_versions[p['field']])
            elif kind=='cancel_case_choice':
                p={'pending_id':self._case_choices[p.pop('pending_ref')]['id']}
            elif kind == 'adopt_pending':
                entry = self._pending[p.pop('pending_ref')]['item']
                p = {'pending_id': entry['id']};ids = adoption_refs(action,entry['sources'])
            elif kind == 'set_boundary':
                if p['target_ref'] == 'case-current': p['target_ref'] = next_case_id if adopting else self._state.active_case_id
                if p['kind'] == 'stop_topic_questions':
                    targets = sorted({b['content']['target_ref'] for b in self._boundaries.values()
                                      if b['content']['kind'] == 'stop_topic_questions'})
                    p['target_ref'] = targets[int(p['target_ref'].split('-')[-1])-1]
            elif kind == 'release_boundary': p['boundary_id'] = self._boundaries[p.pop('boundary_ref')]['id']
            elif kind in {'teaching_step','invite_return'}:
                p['expected_task_revision'] = self._state.lesson_progress.task_revision
            elif kind == 'course_action':
                op = p['operation']
                if op == 'weekly_score': p['quote'] = self._number_quote(action['evidence'],p['value'])
                elif op == 'confirm_record':
                    from .course import record_fingerprint
                    p['record_fingerprint'] = record_fingerprint(self._data)
                elif op in {'check_answer','stage_check_answer'}:
                    from .course import current_check
                    key, attempt, _, _ = current_check(self._data)
                    p.update(attempt_id=key, question_index=attempt['index'])
                elif op in {'confirm_goal','stage_goal'}: p['expected_goal_revision'] = self._state.course.goal_revision
                elif op in {'adopt_goal','adopt_check_answer'}:
                    entry = self._pending[p.pop('pending_ref')]['item']
                    p['pending_id'] = entry['id'];ids = adoption_refs(action,entry['sources'])
                if op in {'set_goal','stage_goal','adopt_goal'}:
                    value=entry['content']['value'] if op=='adopt_goal' else p['value']
                    evidence=self._visible_evidence(entry['sources']) if op=='adopt_goal' else copy.deepcopy(action['evidence'])
                    self._record_audit.append({'action_id':action['id'],'field':'goal','value':value,
                        'evidence':evidence,'verbatim':any(value in e['quote'] for e in evidence),
                        'semantic_review':'pending_human_review'})
            elif kind=='case_change':
                if p['operation']=='adopt':
                    choice=self._case_choices[p.pop('pending_ref')]
                    p['pending_id']=choice['id'];ids=adoption_refs(action,choice['permission_sources'])
                else:
                    story=[]
                    for proof in p.pop('story_evidence'):
                        message=self._sources[proof['ref_id']]
                        if message.role!='learner' or message.material_id is not None or proof['quote'] not in message.text:
                            raise DialogueError('case_story_source')
                        story.append({'source_message_id':message.message_id,'quote':proof['quote']})
                    p.update(story_sources=story,new_case_id=self._planned_case_id)
            result['actions'].append({'id': action['id'], 'type': kind, 'source_ref_ids': ids,
                                      'depends_on': action['depends_on'], 'payload': p})
        reflection = output.get('reflection_request')
        if reflection is not None:
            result['reflection_request'] = {'question': reflection['question'], 'scope': reflection['scope'],
                                           'source_ref_ids': internal_refs(reflection['evidence'])}
        result['evidence_refs'] = refs
        result['context_tags']=[{'relation':tag['relation'],
            'source_message_id':self._message.message_id,
            'quote':tag['evidence']['quote']} for tag in output.get('context_tags',[])]
        # The private event validator remains authoritative for source roles and atomic execution.
        from .contracts import DialogueContract
        DialogueContract(self._state,self._message).parse(result)
        return result

    @staticmethod
    def _number_quote(evidence, value):
        for item in evidence:
            numbers = re.findall(r'(?<![0-9.])[-+]?\d+(?:\.\d+)?(?![0-9.])', item['quote'])
            if len(numbers) == 1 and float(numbers[0]) == value: return item['quote']
        raise DialogueError('score_quote_mismatch')
