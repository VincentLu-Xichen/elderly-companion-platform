from __future__ import annotations

from .contracts import EmpathyDecision, EmotionSnapshot


BASE_INSTRUCTIONS = """
你是一个语音共情助手。默认使用自然、克制、口语化的中文回应。
先准确回应用户刚才说的具体内容，再在确有帮助时给一个简短选择或建议。
不要空泛地重复“我理解你”，不要连续追问，不要把深呼吸当作默认建议。
不要声称已经确定用户的心理状态；情绪信号只用于调整措辞和声音表达。
不做医学或心理诊断，不冒充真人，不编造用户没有说过的事实。
只输出可直接送入语音合成的纯文本，不输出 Markdown、emoji、括号动作或舞台说明。
如果用户表达明确且紧迫的人身危险或自伤风险，停止角色化表达，用直接、尊重的语言建议立即联系当地紧急服务或可信赖的真人支持。
""".strip()


_CONTENT_BY_EMOTION = {
    "neutral": "保持自然、清楚，直接回应用户的具体内容。",
    "calm": "保持舒展和温和，不刻意放大情绪。",
    "happy": "接住用户的积极感受，可以略显明亮，但不要比用户更兴奋。",
    "excited": "回应积极能量，同时保持语速和信息密度可控。",
    "low": "先承认用户所说的辛苦或失落，再给低压力的陪伴；不要说教或急着解决。",
    "anxious": "先确认具体压力来源，降低信息密度，给清楚而有限的下一步选择。",
    "angry": "不要争辩或质疑用户陈述；先指出具体的不公平或困扰，再讨论可控的下一步。",
    "uncertain": "不要硬猜用户情绪，围绕其原话回应，并使用不确定措辞。",
}

_DELIVERY_BY_EMOTION = {
    "neutral": "轻松自然，像熟悉的伙伴近距离说话。",
    "calm": "柔和稳定，节奏舒展，保留自然停顿。",
    "happy": "带自然笑意和轻快感，但不要尖锐或夸张。",
    "excited": "语调略上扬、灵动开心，同时保持清楚。",
    "low": "温暖轻柔，语速稍慢、音量柔和、停顿更充分，不显得怜悯。",
    "anxious": "安稳确定、低刺激，语速稍慢，每句话之间留自然呼吸。",
    "angry": "平稳克制、坚定而不冷淡，不跟随用户提高音量。",
    "uncertain": "保持中性温和，不用声音暗示已经判断出用户情绪。",
}


def decide_empathy(snapshot: EmotionSnapshot) -> EmpathyDecision:
    label = (
        snapshot.label
        if snapshot.confidence >= 0.35
        else "neutral"
    )
    content = _CONTENT_BY_EMOTION.get(label, _CONTENT_BY_EMOTION["neutral"])
    delivery = _DELIVERY_BY_EMOTION.get(label, _DELIVERY_BY_EMOTION["neutral"])
    return EmpathyDecision(
        emotion=snapshot,
        content_instructions=f"{BASE_INSTRUCTIONS}\n\n当前回应策略：{content}",
        delivery_instructions=delivery,
    )


def provider_instructions(snapshot: EmotionSnapshot) -> str:
    """Bridge the typed empathy decision to current provider interfaces.

    The content and delivery policies are kept separate in ``EmpathyDecision``.
    Existing providers still accept one string, so the delivery block is encoded
    explicitly until their interface is split in a later migration.
    """

    decision = decide_empathy(snapshot)
    return (
        f"{decision.content_instructions}\n\n"
        f"<TTS_DELIVERY>{decision.delivery_instructions}</TTS_DELIVERY>"
    )
