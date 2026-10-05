# ESDS Voice

Daily Chat 情绪传递与常见误判修复说明：[emotion-bridge.md](docs/emotion-bridge.md)。

无视觉输入的语音共情系统：

```text
麦克风 → VAD → ASR + 情绪识别 → 共情策略/LLM → 情绪化 TTS → 扬声器
```

项目从 `AdvX26 - Audio` 第一轮迁移而来，保留阿里百炼 API 能力，删除摄像头、Qwen-VL、一眼识别、夸夸视觉和值守事件。浏览器客户端只请求麦克风权限。

## 当前能力

- 24 kHz、单声道、PCM16、20 ms WebSocket 音频帧
- AEC / 降噪浏览器约束；服务端频谱门控或 RNNoise
- 自适应噪声底 VAD、约 200 ms 预卷
- 本地 SenseVoice 或百炼 Qwen3-ASR
- 本地 emotion2vec+、文本情绪以及 Qwen Realtime 情绪信号融合
- Ollama Qwen3 流式回复
- 百炼 Qwen3-TTS Realtime Cherry，Edge TTS 备用
- 百炼 Qwen Omni Realtime 云端 ASR/LLM/TTS 模式
- 半双工、播放耗尽确认、回声尾部保护
- 原始音频默认不落盘

## 运行模式

### 1. 模块化本地模式

ASR、情绪、LLM、TTS 可分别替换。默认组合是：

```text
SenseVoice + emotion2vec → Ollama Qwen3 → 百炼 Cherry TTS
```

本仓库配置完成后无需激活虚拟环境、设置模型路径或手动启动 Ollama：

```bash
python scripts/run_local.py
```

启动器会自动切换到项目的 `.venv`，发现 `.models` 中的 SenseVoice 和
emotion2vec，启动 `.tools` 中的 Ollama，并在终端安全提示输入百炼 Key。
Key 只保存在当前 Python 进程内，不写入磁盘或传给浏览器。也可以预先设置
`DASHSCOPE_API_KEY`，此时不会再次询问。

页面地址默认是 `http://127.0.0.1:8080`。

### 2. 百炼模块化模式

保留本地 Ollama 和可选 emotion2vec，但把 ASR、TTS 放到百炼：

```bash
export ESDS_RUNTIME_PROVIDER=local
export ESDS_ASR_PROVIDER=qwen
export ESDS_TTS_PROVIDER=qwen
export ESDS_EMOTION_BACKEND=emotion2vec
export ESDS_EMOTION2VEC_MODEL_DIR='/absolute/path/to/emotion2vec_plus_base'
export DASHSCOPE_API_KEY='...'
python scripts/run_local.py
```

### 3. 百炼 Qwen Realtime 模式

适合资源有限的树莓派网关。ASR、对话模型、TTS 均在百炼，树莓派主要负责音频、VAD、协议和播放。

```bash
export ESDS_RUNTIME_PROVIDER=qwen_realtime
export ESDS_EMOTION_BACKEND=heuristic
export DASHSCOPE_API_KEY='...'
export ESDS_QWEN_REALTIME_WORKSPACE_ID='...'
python scripts/run_local.py
```

设置 `ESDS_EMOTION_BACKEND=emotion2vec` 并提供模型路径，可以同时使用本地 emotion2vec；使用 `heuristic` 时仍会融合 Qwen Realtime 返回的情绪标签和转写文本信号。

## 测试

测试使用标准库 `unittest`，不要求 pytest：

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py' -q
```

模型与网络评测：

```bash
PYTHONPATH=src python scripts/benchmark_hot_path.py
PYTHONPATH=src python scripts/evaluate_emotion2vec.py MODEL_DIR AUDIO_DIR
PYTHONPATH=src python scripts/evaluate_qwen_asr.py --help
PYTHONPATH=src python scripts/evaluate_qwen_tts.py --help
```

## 安全与隐私

- `DASHSCOPE_API_KEY` 只放在网关环境变量中，不进入浏览器或设备固件。
- 生产环境使用 `wss://`、反向代理 TLS 和 `ESDS_DEVICE_TOKEN`。
- `.models/`、`.env`、诊断音频和构建产物均不提交。
- 当前浏览器客户端不调用摄像头 API，也不加载人脸或视觉模型。

树莓派部署和硬件边界见 [docs/raspberry_pi.md](docs/raspberry_pi.md)，协议见 [docs/protocol.md](docs/protocol.md)。
