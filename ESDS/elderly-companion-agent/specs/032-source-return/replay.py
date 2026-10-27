"""Zero-API replay of captured T06 invitation against a missing invitation state."""
import copy,json
from pathlib import Path
from cbt_course_llm_freeform import dialogue
r=Path('test-results/dialogue-evals/20261026-continuous-demo-12-cua')
s=json.loads((r/'T06-persisted-state.json').read_text())
# This snapshot is after T06 and contains its actual validated latest teaching turn.
t=s['latest_teaching_turn']; latest={'id':t['source_message_id'],'content':t['quote']}
# Original JSON invite_return must remain an invitation, not automatic consent.
s['classroom_dialogue']['invitation']=None
dialogue.apply_turn(s,t,latest)
assert s['classroom_dialogue']['invitation']['status']=='pending'
assert s['classroom_dialogue']['mode']=='conversation'
# The user's reported proactive refusal is a separate synthetic branch, not a captured model output.
s['classroom_dialogue']['invitation']=None
latest={'id':'synthetic-032-refusal','content':'我现在还不想回练习，想再缓一会儿。'}
t=dict(kind='decline_return',source_message_id=latest['id'],quote=latest['content'],attempted_field=None)
before=copy.deepcopy(s)
dialogue.apply_turn(s,t,latest)
assert s['classroom_dialogue']['invitation'] is None
assert s['classroom_dialogue']['return_preference']['quote']==latest['content']
assert s['draft_record']==before['draft_record']
print(json.dumps({'captured_T06_invitation_replay':'pass','synthetic_no_invitation_refusal_branch':'pass','api_requests':0},ensure_ascii=False))
