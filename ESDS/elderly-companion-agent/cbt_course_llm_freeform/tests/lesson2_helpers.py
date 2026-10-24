"""Walk the public teacher-aligned path with explicit source-labelled answers."""
def prepare(turn, *, skip_checkin=True):
    result = None
    if skip_checkin:
        result = turn(action="skip_checkin")
    def current(value):
        return value["course"]["current_step"] if isinstance(value,dict) else value.state["lesson2_flow"]["step"]
    if result is None or current(result)=="homework":
        report = turn("这次还没尝试课后记录。")
        if current(report)=="homework":
            turn("这次不想解释，先继续吧。",action="continue_lesson2")
    # An authorized previous decline can legitimately omit homework review.
    for answer in ("认知", "情绪", "行为"):
        turn(answer)
    turn(action="continue_lesson2")
    turn("情绪：失望；想法：出游安排泡汤了")
    turn(action="continue_lesson2")
    turn(action="continue_lesson2")
    turn("情境：散步时下雨；想法：安排泡汤了；情绪：失望；情绪强度：6分")
