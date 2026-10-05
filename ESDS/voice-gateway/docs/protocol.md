# companion-audio/1 语音协议

第一轮迁移继续兼容原协议，避免树莓派或既有终端同时改动。WebSocket 路径为 `/v1/device`。

## 握手

设备连接后 5 秒内发送：

```json
{
  "type": "device.hello",
  "protocol": "companion-audio/1",
  "device_id": "raspberry-pi-01",
  "device_type": "raspberry_pi_audio",
  "token": "optional-device-token",
  "audio": {
    "sample_rate": 24000,
    "channels": 1,
    "format": "pcm16",
    "frame_ms": 20
  },
  "capabilities": ["audio", "aec"]
}
```

收到 `session.ready` 后才开始上传音频。

## 音频

- 文本帧：JSON 控制事件
- 二进制帧：裸 PCM16 little-endian
- 推荐上行帧：960 字节
- 下行二进制：24 kHz 单声道 PCM16

## 设备发送的事件

- `playback.progress`
- `playback.drained`
- `response.cancel`
- `audio.flush`
- `client.audio_settings`
- `client.metrics`
- `ping`

视觉、presence、praise、yiyan 和 scene 事件不属于 ESDS Voice，发送后会收到 `unsupported_event`。

## 网关发送的事件

- `session.ready`
- `state.changed`
- `emotion.updated`
- `transcript.user`
- `transcript.assistant`
- `turn.ignored`
- `audio.flush`
- `audio.done`
- `error`
- `pong`

状态为：

```text
listening → user_speaking → processing → assistant_speaking → listening
```

`audio.done` 只代表不再产生新音频。设备必须在本地播放队列和声卡缓存全部耗尽后发送 `playback.drained`。
