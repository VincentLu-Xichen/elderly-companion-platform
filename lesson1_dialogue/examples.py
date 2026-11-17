"""Reviewed teaching examples; learner story and teacher interpretation share one card."""
from copy import deepcopy

RUBRIC = {
    'situation': '本次分析的触发事件/背景：发生在何时何地、遇到什么事；与当事人随后的应对分开。',
    'thought': '当事人对事情的解释、判断或预测，不把解释当已经证实的客观事实。',
    'emotion': '当事人的主观感受，例如难过、着急、失望；感受名称与强度评分分开。哭是动作，不把哭得很急直接称为情绪。',
    'behavior': '当事人随后实际做了或没有做什么；即使客观可见，也不因此归入本例触发情境。',
    'teaching_note': '依据同一案例和分析时点区分；可讨论视角。客观可见只帮助区分内外，不足以区分情境与行为。',
}

EXAMPLES = {
    'concepts': {
        'example_id': 'phone-demo-1', 'person': '小林', 'purpose': 'teaching',
        'story': '朋友没有回电话，小林想到‘他是不是不愿理我’，感到失落，于是没有再联系。',
        'parts': {'situation': '朋友没有回电话', 'thought': '他是不是不愿理我',
                  'emotion': '失落', 'behavior': '没有再联系'},
        'note': '朋友没回电话是触发情境；小林没再联系是其应对行为。不能因两者都是客观事件而合并。',
    },
    'practice-library': {
        'example_id': 'library-practice-1', 'person': '老李', 'purpose': 'guided_practice',
        'story': '老李到图书馆借书，发现临时闭馆。他想“今天的安排全乱了”，感到失望，转身回家。',
        'parts': {'situation': '老李到图书馆借书，发现临时闭馆', 'thought': '今天的安排全乱了',
                  'emotion': '失望', 'behavior': '转身回家'},
        'note': '本例以发现闭馆为触发事件，转身回家为老李随后的应对行为；不把同一句同时列为本例情境和待识别行为。',
    },
}


def validate_examples():
    ids = set()
    for card in EXAMPLES.values():
        assert card['example_id'] not in ids
        ids.add(card['example_id'])
        assert set(card['parts']) == {'situation', 'thought', 'emotion', 'behavior'}
        assert all(value and value in card['story'] for value in card['parts'].values())
    return True


validate_examples()
LIBRARY_STORY = EXAMPLES['practice-library']['story']


def teacher_examples(material_refs):
    """No independent check/retry answer keys are exposed here."""
    return {ref: deepcopy(EXAMPLES[ref]) for ref in material_refs if ref in EXAMPLES}
