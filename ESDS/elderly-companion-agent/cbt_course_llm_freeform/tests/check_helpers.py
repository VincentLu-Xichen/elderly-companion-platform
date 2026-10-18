"""Drive the new lesson-one segment in pre-existing full-course fixtures."""


def complete_first_check(turn):
    for answer in ("邻居向他问好", "他怕对方觉得自己没礼貌", "紧张", "低下头，没有回话"):
        turn(answer)
    turn(action="continue_after_check")
    turn(action="skip_learning_goal")
