"""Replay unchanged captured JSON on a synthetic state with captured context."""
from pathlib import Path
import copy,json,zipfile
from cbt_course_llm_freeform.tests.test_dialogue_ownership import starting
from cbt_course_llm_freeform.schemas import TeachingDecision,AgentResult
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime,faithful_excerpt
r=Path('test-results/dialogue-evals/20261027-033-conversation-priority')
old=Path('test-results/dialogue-evals/20261027-032-live-cua/request-006.json')
q=json.loads(old.read_text());decision=TeachingDecision.model_validate_json(q['completion']['text'])
c=json.loads(q['messages'][1]['content'])['data'];state,_=starting()
state.update(stage=c['stage'],case_id=c['case_id'],draft_record=copy.deepcopy(c['recorded_fields']),blueprint=copy.deepcopy(c['blueprint']),classroom_dialogue=copy.deepcopy(c['classroom_dialogue']))
history=[]
for m in q['messages'][2:]:
 item=json.loads(m['content']);history.append(dict(id=item['id'],content=item['text'],role='learner' if m['role']=='user' else 'agent'))
latest=history[-1];before=copy.deepcopy(state)
old_scope={}
with zipfile.ZipFile(r/'before-source.zip') as z:
 exec(compile(z.read('cbt_course_llm_freeform/dialogue.py'), 'captured-before-dialogue.py','exec'),old_scope)
try:
 old_scope['resolve_turn'](decision,latest,faithful_excerpt)
 raise AssertionError('Old conflict was expected')
except ValueError as e: old_error=str(e)
class Stub:
 def reply(self,history,*,context):return AgentResult(reply=decision.reply,decision=decision)
result=FreeformCourseRuntime(agent=Stub()).process(state,history)
for key in ['stage','draft_record','practice_flow','blueprint','case_id','confirmed_record']:
 assert result.state[key]==before[key],key
assert result.reply==decision.reply
assert result.trace['observations']==[]
assert result.trace['conversation_record_guard']['rejected_signals']==[s.model_dump() for s in decision.assessment.signals]
(r/'original-json-replay.json').write_text(json.dumps(dict(original_file=str(old),original_json_unchanged=True,synthetic_state_with_captured_context=True,before_error=old_error,after_reply=result.reply,record_unchanged=True,guard=result.trace['conversation_record_guard'],api_requests=0),ensure_ascii=False,indent=2))
print('Original request-006 JSON replay passed: reply preserved, candidate writes/signals rejected, original records unchanged.')
