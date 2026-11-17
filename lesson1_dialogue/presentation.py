"""Reject recognizable internal output before it becomes a saved learner reply."""
import re
from .contracts import DialogueError

# Restored from the reviewed weekly-mood rule (017), only for weekly 1—3.
LOW_WEEKLY_SUPPORT = '您给上周的状态打了较低的分，听起来这段时间可能不容易。谢谢您告诉我，我们按您的节奏来。'
MIDDLE_WEEKLY_SUPPORT = '谢谢，先记下您对上周状态的评价。我们接着看今天的内容。'
HIGH_WEEKLY_SUPPORT = '您对上周状态的评价比较高，谢谢您告诉我。我们开始今天的内容。'
WEEKLY_SUPPORT = (LOW_WEEKLY_SUPPORT, MIDDLE_WEEKLY_SUPPORT, HIGH_WEEKLY_SUPPORT)


def weekly_support_reply(state, output):
    """A fixed presentation rule, independent of model phrasing or score inference."""
    weekly=next((a.payload.value for a in output.actions if a.type=='course_action'
                 and a.payload.operation=='weekly_score'),None)
    if (state.course.enabled and state.flow_mode=='teaching' and
            state.lesson_progress.phase=='check_in' and output.signal=='none' and weekly is not None):
        support=WEEKLY_SUPPORT[0 if weekly<=3 else 1 if weekly<=6 else 2]
        body=output.reply
        for sentence in WEEKLY_SUPPORT:body=body.replace(sentence,'')
        body=body.strip()
        return support+('\n\n'+body if body else '')
    return output.reply


INTERNAL = re.compile(r'(?<![A-Za-z0-9_])(?:case_ref|pending_ref|subject_ref|expected_revision|idempotency_key|'
    r'source_message_id|wire_output_contract)(?![A-Za-z0-9_])|lesson1-dialogue(?:-wire)?/\d|'
    r'Traceback \(most recent call last\)|'
    r'(?:请(?:你|您)?|需要(?:你|您)|麻烦(?:你|您)).{0,8}(?:提供|填写|修复|修改).{0,12}(?:JSON|Schema)',re.IGNORECASE)


def check_public_reply(reply):
    # Deliberately narrow: this is not a semantic classifier or a second model call.
    if INTERNAL.search(reply):
        raise DialogueError('reply_internal_details')
