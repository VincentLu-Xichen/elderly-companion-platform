"""Persistent message provenance and small, source-scoped case boundaries."""
from __future__ import annotations

import copy
import hashlib
import json

from .contracts import DialogueError


def planned_case_id(state, message):
    value=json.dumps([state.conversation_id,message.message_id,'selected-case'])
    return 'case-'+hashlib.sha256(value.encode()).hexdigest()[:24]


def _ranges(text, quote):
    start=0
    while quote and (index:=text.find(quote,start))>=0:
        yield index,index+len(quote)
        start=index+1


def overlaps(text, left, right):
    return any(a<d and c<b for a,b in _ranges(text,left) for c,d in _ranges(text,right))


def enrolled_source(data, source, case_id):
    story=data.get('case_story')
    return bool(story and story['case_id']==case_id and any(
        s['source_message_id']==source['source_message_id'] and source['quote'] in s['quote']
        for s in story['sources']))


def _library_shown(text):
    from .examples import EXAMPLES
    card=EXAMPLES['practice-library']
    return card['story'] in text or (card['person'] in text and all(p in text for p in card['parts'].values()))


def response_scope(state):
    """Bind replies to a known displayed material; do not guess arbitrary story semantics.

    A registered fictional case remains writable as learner answers. An unselected
    library story in a personal exercise is discussion only until task refocus.
    """
    if not state.course.enabled or state.flow_mode!='teaching' or state.case_kind!='personal' or state.lesson_progress.phase not in {'learn','practice','review'}:
        return {'kind':'current_task','material_ref':None}
    for message in reversed(state.conversation_history):
        if message.role!='agent':continue
        entry=state.message_context.get(message.message_id)
        if entry and entry.case_at_start!=state.active_case_id:break
        if (entry and entry.material_id=='practice-library') or _library_shown(message.text):
            return {'kind':'unselected_material','material_ref':'practice-library'}
        if entry and entry.case_id==state.active_case_id:break
    return {'kind':'current_task','material_ref':None}


def guard_course_source(data, source, messages, case_id, *, enrollment=False):
    """Honor recorded span boundaries; a model label is not semantic proof."""
    metadata=data.get('message_context',{}).get(source['source_message_id'],{})
    if metadata.get('material_id')=='practice-library':
        raise DialogueError('source_material_scope_mismatch')
    message=messages[source['source_message_id']]
    selected=enrolled_source(data,source,case_id)
    for tag in metadata.get('tags',[]):
        if not overlaps(message.text,source['quote'],tag['quote']):continue
        relation=tag['relation']
        if relation=='quoted_example' and (enrollment or data['case_kind']=='personal'):
            raise DialogueError('example_not_personal_case')
        if relation in {'conversation_event','uncertain'} and not (selected or enrollment):
            raise DialogueError('source_context_not_course')
        if relation=='course_case' and tag.get('case_id')!=case_id and not selected and not enrollment:
            raise DialogueError('source_case_mismatch')


def remember_incoming(data, before, message, tags, course_case_id=None):
    """Mode and starting case are program facts, independent of semantic tags."""
    entry={'origin_mode':before.flow_mode,'case_at_start':before.active_case_id,
           'case_id':message.case_id,'material_id':message.material_id,'tags':[]}
    scope=response_scope(before)
    if scope['kind']=='unselected_material':entry['material_id']=scope['material_ref']
    for tag in tags:
        value=tag.model_dump()
        if value['source_message_id']!=message.message_id or value['quote'] not in message.text:
            raise DialogueError('context_tag_source')
        value['case_id']=(course_case_id or before.active_case_id) if value['relation']=='course_case' else None
        for older in entry['tags']:
            if older['relation']!=value['relation'] and overlaps(message.text,older['quote'],value['quote']):
                raise DialogueError('context_tag_conflict')
        if value not in entry['tags']:entry['tags'].append(value)
    data['message_context'][message.message_id]=entry


def remember_course_use(data, sources, case_id):
    for source in sources:
        if enrolled_source(data,source,case_id):continue
        entry=data['message_context'].get(source['source_message_id'])
        if entry is None:continue
        # Keep a known original event tag after explicit enrollment. The enrollment
        # receipt supplies the new purpose; do not rewrite historical provenance.
        if any(t['quote']==source['quote'] for t in entry['tags']):continue
        entry['tags'].append({**source,'relation':'course_case','case_id':case_id})


def restore_message_context(data, messages):
    """Restore trusted fields when history is rebuilt from Message rows."""
    metadata=data.get('message_context',{})
    return [message.model_copy(update={k:metadata[message.message_id].get(k)
            for k in ('origin_mode','case_id','material_id')}) if message.message_id in metadata else message
            for message in messages]


def provenance_view(state, message, *, current=False):
    entry=state.message_context.get(message.message_id)
    return {'origin_mode':state.flow_mode if current else entry.origin_mode if entry else message.origin_mode,
            'content_tags':[{'quote':tag.quote,'relation':tag.relation,
                'case_ref':'case-current' if tag.case_id==state.active_case_id else 'other' if tag.case_id else None}
                for tag in (entry.tags if entry else [])]}


def remember_outgoing(data, before, message, *, refocused=False):
    from .examples import EXAMPLES
    entry={'origin_mode':before.flow_mode,'case_at_start':before.active_case_id,
           'case_id':data['active_case_id'] if data['course']['enabled'] and data['flow_mode']=='teaching' else None,
           'material_id':None,'tags':[]}
    for material_ref,card in EXAMPLES.items():
        if card['story'] in message.text:
            entry['tags'].append({'source_message_id':message.message_id,'quote':card['story'],
                                 'relation':'quoted_example','case_id':None})
            if message.text.strip()==card['story']:entry['material_id']=material_ref
    foreign=(data['case_kind']=='personal' and data['flow_mode']=='teaching' and
             data['lesson_progress']['phase'] in {'learn','practice','review'} and
             (_library_shown(message.text) or not refocused and
              data['active_case_id']==before.active_case_id and response_scope(before)['kind']=='unselected_material'))
    if foreign:entry.update(material_id='practice-library',case_id=None)
    data['message_context'][message.message_id]=entry
    return message.model_copy(update={'material_id':entry['material_id'],'case_id':entry['case_id']})


def change_case(data, case_id, sources, permission_sources):
    from .engine import _active
    if any(_active(data,'no_personal_case')):raise DialogueError('personal_case_blocked')
    if case_id==data['active_case_id']:raise DialogueError('case_change_same_case')
    data['archived_cases'].append({'case_id':data['active_case_id'],'case_kind':data['case_kind'],
        'records':copy.deepcopy(data['records']),'ratings':copy.deepcopy(data['ratings']),
        'story':copy.deepcopy(data.get('case_story'))})
    data.update(active_case_id=case_id,case_kind='personal',records={},ratings={},field_versions={},
        case_story={'case_id':case_id,'sources':sources,'permission_sources':permission_sources})
    data['course']['confirmation']=None
    data['lesson_progress'].update(phase='practice',activity_id='practice',field='situation',
        task_revision=data['lesson_progress']['task_revision']+1,attempts=0)
    if data['return_invitation'] is not None and data['return_invitation']['status']=='pending':
        data['return_invitation']['status']='superseded'


def apply_case_change(data, before, action, permission_sources, messages, request_id):
    from .engine import _id
    payload=action.payload
    if before.lesson_progress.phase not in {'learn','practice','review'}:
        raise DialogueError('case_change_phase')
    if payload.operation in {'stage','select'}:
        # A story may come from another conversation event after explicit
        # selection. The permission itself must not be an event/uncertainty/
        # quotation span: enrollment never grants its own authorization.
        for permission in permission_sources:
            message=messages[permission['source_message_id']]
            tags=data['message_context'].get(message.message_id,{}).get('tags',[])
            if any(tag['relation'] in {'conversation_event','uncertain','quoted_example'} and
                   overlaps(message.text,permission['quote'],tag['quote']) for tag in tags):
                raise DialogueError('case_choice_permission_not_selection')
        sources=[s.model_dump() for s in payload.story_sources]
        for source in sources:
            message=messages.get(source['source_message_id'])
            if message is None or message.role!='learner' or message.material_id is not None or source['quote'] not in message.text:
                raise DialogueError('case_story_source')
            guard_course_source(data,source,messages,payload.new_case_id,enrollment=True)
        if payload.operation=='stage':
            for choice in data['case_choices']:
                if choice['status']=='pending':choice['status']='superseded'
            data['case_choices'].append({'id':_id('case-choice',request_id,action.id),
                'case_id':payload.new_case_id,'origin_case_id':before.active_case_id,
                'sources':sources,'permission_sources':permission_sources,'status':'pending'})
        else:change_case(data,payload.new_case_id,sources,permission_sources)
    else:
        choice=next((p for p in data['case_choices'] if p['id']==payload.pending_id),None)
        if choice is None or choice['status']!='pending' or choice['origin_case_id']!=before.active_case_id:
            raise DialogueError('case_choice_stale')
        change_case(data,choice['case_id'],choice['sources'],choice['permission_sources'])
        choice['status']='adopted'
