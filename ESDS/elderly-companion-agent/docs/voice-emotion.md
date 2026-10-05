# Daily Chat 本轮情绪线索

语音网关通过 `POST /internal/voice/v1/sessions/{conversation_id}/turns/stream` 的可选
`emotion` 字段传入当前轮次的弱线索。例如：

```json
{
  "transcript": "我有点担心明天的事",
  "idempotency_key": "voice-example-001",
  "emotion": {"label": "anxious", "confidence": 0.45, "evidence": ["anxious_words"]}
}
```

`label` 仅允许 neutral、calm、happy、excited、low、anxious、angry、uncertain。
`confidence` 必须是 0–1 的有限数；evidence 最多 8 项，每项不超过 64 字符，
进入模型和加密 Trace 前还会按 `daily_agent/emotion_context.py` 的白名单过滤。
不接受由网关任意提供的 system 指令。原有认证、设备登记、同意门禁保持不变。

流式语音链路为 `VoiceTurnCreate → stream_process_turn → DailyChatAgent.stream_reply`。
服务端逐块发送 SSE `delta`，并在完成后发送 `done`；普通 JSON `/turns` 接口仍保留。
情绪数据作为仅对应最后一条用户消息的独立 system 上下文，不改写用户原话，
也不把它存入对话历史。低于 0.35 或标签为 neutral/uncertain 时不据此调整情绪语气；
其他标签也只是弱线索，用户的否定、转述和纠正优先。不新增模型调用。
`confidence` 是启发式可靠度提示，不是准确率或经过校准的心理状态概率。

`voice_emotion` 保存在现有加密 `TurnEvent.trace_encrypted` 内，失败轮次也保留
传入线索。同一个幂等键仍只处理一次。没有数据库结构变化，不需迁移。
不携带 emotion 的旧客户端及 `reply(history) -> str` 保持兼容。
CBT 使用单独的课程接口，不接收这里的日常聊天情绪上下文。

部署时需同时更新本项目和 voice-gateway 的相关文件；只更新 prompt.py 不会接通链路。
真实语音与真实模型效果须在树莓派试听确认。
