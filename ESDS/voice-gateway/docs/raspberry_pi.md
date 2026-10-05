# 树莓派集成方案

## 当前 Daily Chat 集成拓扑

本工作区部署于 `/home/esds/ESDS/voice-gateway`，并与独立的
`/home/esds/ESDS/elderly-companion-agent` 协作：

```text
创乐博麦克风 → 本地 VAD → 百炼 ASR
  → Elderly Agent 内部 API（加密持久化、幂等、Daily Chat）
  → 百炼 TTS → 模块扬声器
```

`ESDS_RUNTIME_PROVIDER=local` 在此表示模块化链路，不代表使用本地模型；
`ESDS_CHAT_PROVIDER=agent_bridge` 会跳过 Ollama。Agent 只监听
`127.0.0.1:8000`。CBT 与视觉附件不在当前部署范围。

## 推荐拓扑

第一轮建议将树莓派作为音频终端或轻量网关，不在 4 GB 设备上同时常驻 emotion2vec、4B Ollama、Chromium 和高质量 TTS。

### 拓扑 A：树莓派音频终端

```text
树莓派
  麦克风 / AEC / NS / 24 kHz PCM / 播放
        ↕ companion-audio/1 WebSocket
局域网 Mac、迷你主机或云网关
  SenseVoice / emotion2vec / Ollama / 百炼 TTS
```

优点是情绪识别完全受控，设备负载低，适合先完成硬件声学验收。

### 拓扑 B：树莓派轻量百炼网关

```text
树莓派
  音频采集 + 本地 VAD + ESDS Gateway
        ↕ 百炼 Qwen Realtime
  云端 ASR + 对话 + TTS
```

配置：

```bash
export ESDS_RUNTIME_PROVIDER=qwen_realtime
export ESDS_EMOTION_BACKEND=heuristic
export DASHSCOPE_API_KEY='...'
export ESDS_QWEN_REALTIME_WORKSPACE_ID='...'
```

Qwen Realtime 的情绪字段和文本情绪会进入 ESDS 情绪融合。若树莓派型号和内存允许，可再启用本地 emotion2vec，作为独立声学情绪信号。

## 树莓派系统要求

- 64 位 Raspberry Pi OS
- Python 3.11+
- 有线网络或稳定的 5 GHz Wi-Fi
- ALSA / PipeWire 可正常进行全双工采集播放
- 设备端 AEC；没有 AEC 时保持半双工
- 生产使用 TLS 反向代理，不把百炼 Key 下发到浏览器页面

## Raspberry Pi 5 安装

项目采用轻量百炼网关模式，不把 Mac 的 `.venv`、`.models` 或
`.tools` 复制到树莓派。项目同步到 `/home/esds/ESDS/voice-gateway` 后执行：

```bash
cd /home/esds/ESDS/voice-gateway
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e .

mkdir -p ~/.config/systemd/user
cp deploy/raspberry-pi/esds-voice.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable esds-voice.service
cp deploy/raspberry-pi/esds-pi-audio.service ~/.config/systemd/user/
systemctl --user enable esds-pi-audio.service
```

首次配置百炼凭据：

```bash
cd /home/esds/ESDS/voice-gateway
.venv/bin/python scripts/configure_pi.py
```

Key 通过隐藏输入读取，只写入树莓派本机
`~/.config/esds-voice/env`，文件权限为 `600`。还需要填写百炼
Workspace ID。配置完成后脚本会重启服务。

让用户服务在没有 SSH 登录时也能随系统启动：

```bash
sudo loginctl enable-linger esds
```

检查服务：

```bash
systemctl --user status esds-voice.service --no-pager
systemctl --user status esds-pi-audio.service --no-pager
journalctl --user -u esds-voice.service -n 100 --no-pager
journalctl --user -u esds-pi-audio.service -n 100 --no-pager
```

原生客户端默认使用创乐博模块当前枚举出的 ALSA 卡名：

```text
capture:  plughw:CARD=Device,DEV=0
playback: plughw:CARD=Device,DEV=0
```

模块原生为 48 kHz 双声道；ALSA `plughw` 在设备边界转换为协议要求的
24 kHz 单声道 PCM16。实测标定后，客户端启动时将
`Mic Capture Volume` 固定为 `+8 dB`、扬声器音量固定在约 `-13 dB`；
再使用最大 `+18 dB`、目标 `-20 dBFS` 的峰值保护自动增益补偿远距离
说话，同时在近距离说话时自动回落。VAD 启停阈值为 `-48/-54 dBFS`，
启动 SNR 为 `12 dB`。播放期间停止上传麦克风数据，播放耗尽后再等待
450 ms 才恢复收音。

不调用百炼的硬件协议自检：

```bash
# 终端 1
.venv/bin/python scripts/pi_audio_selftest.py

# 终端 2
.venv/bin/python scripts/run_pi_audio.py \
  --config-url http://127.0.0.1:18081/runtime-config.js
```

测试会验证 20 ms 麦克风分帧、播放一段短提示音、`playback.drained`
确认，以及播放期间没有麦克风上行。

网关和演示页面默认只监听树莓派回环地址，避免将百炼链路直接暴露在局域网。
需要从 Mac 调试页面时使用 SSH 隧道：

```bash
ssh -L 8080:127.0.0.1:8080 -L 8765:127.0.0.1:8765 esds@esds-pi.local
```

然后在 Mac 打开 `http://127.0.0.1:8080`。

## 音频契约

- 采样率：24,000 Hz
- 声道：单声道
- 编码：PCM16 little-endian
- 帧长：20 ms，即 960 字节
- 播放初始缓冲：建议 40–80 ms

如果声卡只能输出 48 kHz，应在设备端重采样至 24 kHz 后上传。Qwen ASR 所需的 16 kHz 由网关使用 soxr 高质量流式重采样。

## 硬件验收顺序

1. 只跑本地 PCM 环回，确认无丢帧、声道和端序正确。
2. 使用 `ESDS_RUNTIME_PROVIDER=mock ESDS_EMOTION_BACKEND=heuristic`，验证握手、状态和播放队列。
3. 接百炼 Qwen Realtime，测网络 TTFA 和 30 分钟稳定性。
4. 在扬声器播放期间确认麦克风不上传，验证半双工回声保护。
5. 完成 AEC 后，再进入下一轮语义打断迁移。

## 资源边界

emotion2vec 权重约 1 GB，SenseVoice 约 229 MB，Ollama Qwen3 4B 模型约 2.3 GB；运行时内存还会高于文件体积。因此 4 GB 树莓派不建议采用全部本地模式。8 GB 设备也应分别测内存、温度和 P95 延时后再决定是否常驻模型。
