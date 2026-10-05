# 情绪线索到 Daily Chat 的传递

当前轮次的 `EmotionSnapshot` 通过以下可选扩展接口传递：

`DeviceSession → LocalCompanionProvider.create_response_with_emotion(instructions, snapshot)
→ AgentBridgeChatClient.stream_reply_with_emotion(messages, snapshot)
→ Agent /internal/voice/v1/sessions/{id}/turns/stream 的 emotion 字段`。

Daily Chat 语音路径使用 SSE 逐块传递生成文本。网关收到一段完整句子后即可交给 TTS，
无需等待整条回复生成完毕；会话记录、加密 trace、幂等键和模型用量仍在服务端完成后写入。
原来的 JSON `/turns` 接口保留给非流式客户端，CBT 课程桥接也继续使用原来的 JSON 接口。

旧 provider 的 `create_response(instructions)` 与旧 chat client 的 `stream_reply(messages)`
仍可使用。emotion 作为函数参数传递，不缓存为下一轮的默认值。会话重新打开后的重试
保留本轮 emotion 和幂等键。CBT 桥接继续只传文字，不携带 Daily Chat 的 emotion。
服务端字段说明见 `../../elderly-companion-agent/docs/voice-emotion.md`。

本轮同时修复了以下启发式判断问题：

- `不难过`、`没有生气` 等否定不再直接匹配负面关键词；`不开心` 不再判为开心。
- 常见第三人称、引号转述、带过去时间的语句不直接当作用户当下感受。
- `开心果`、`积累`、`困难`、`麻烦你` 等词不再因子串而误判。
- 双重否定、常见反讽标记、假设句和混合正负情绪倾向返回 uncertain。
- 每轮重置音频窗口、平滑值、文字和模型状态；读取 snapshot 不改变状态，也不丢证据。
- 语音模型先于最终文字完成时，使用最新融合状态，避免旧任务结果覆盖文字纠正。
- 不再把低模型分数抬到最低情绪置信度，音量本身保持低权重；冲突时降低置信度。
- 回应策略统一采用 0.35 阈值，关键词不能绕过低置信度保护。

`heuristic` 配置仍主要依靠文字规则和基础声学特征。

网关日志 `voice_turn_first_audio_ms` 会记录最终转写后到首段音频的耗时；
`voice_reply_timing` 记录模型首块、模型完成、首段音频和总耗时，
`voice_asr_complete` 记录 ASR 耗时。日志不包含转写文本或回复内容。

规则仍不能完整理解任意中文、反讽或复杂人物关系。情绪只是辅助措辞，不能覆盖用户原话。
本次不下载或启用新的情绪模型，不改变环境配置，也不解决 ASR 听错的问题。
