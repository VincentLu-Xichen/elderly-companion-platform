# ESDS 项目交接说明

## 包含内容

- `ESDS/elderly-companion-agent/`：FastAPI Agent、Daily Chat、CBT freeform 第 1/2 课、网页和语音桥接接口。
- `ESDS/voice-gateway/`：百炼 ASR/TTS、Daily Chat/CBT Agent Bridge、树莓派 ALSA 音频客户端。
- `tools/esds_control_panel.py`：树莓派桌面控制面板。
- `tools/ESDS-Control-Panel.desktop`：桌面快捷方式。
- `README-操作指南.md`：项目部署操作指南。
- `ESDS/voice-gateway/docs/raspberry_pi.md`：树莓派语音网关说明。
- `backups/README-树莓派备份与恢复.md`：树莓派备份与恢复命令。

## 不包含内容

源码包不包含：

- `.venv/`
- 模型权重和 `.models/`
- Ollama 运行时和 `.tools/`
- SQLite 运行数据库
- 真实 `.env` 或 `~/.config/*/env`
- API Key、Bridge Token、APP_SECRET、DATA_ENCRYPTION_KEY
- 日志、缓存、录音和 Git 元数据

## 当前已验证功能

- Daily Chat 网页模式：百炼 `qwen-plus`
- CBT 网页模式：百炼 `qwen-plus`
- Daily Chat 树莓派语音：已验证
- CBT Lesson 1 树莓派语音桥接：已验证
- BT700 麦克风和扬声器：已验证
- Agent、语音网关和 Pi 音频 systemd 服务：已验证

## 树莓派配置模式

Daily Chat 语音：

```dotenv
ESDS_CHAT_PROVIDER=agent_bridge
```

CBT Lesson 1 语音：

```dotenv
ESDS_CHAT_PROVIDER=cbt_agent_bridge
ESDS_CBT_LESSON_ID=lesson-1
```

两种模式切换后需要重启三个用户服务：

```bash
systemctl --user restart elderly-agent.service
systemctl --user restart esds-voice.service
systemctl --user restart esds-pi-audio.service
```

Agent 配置中 CBT 和 Daily Chat 共用百炼 Key，但使用独立模型配置：

```dotenv
DAILY_CHAT_PROVIDER=dashscope
DASHSCOPE_CHAT_MODEL=qwen-plus
CBT_COURSE_PROVIDER=dashscope
CBT_COURSE_MODEL=qwen-plus
```

## 新机器安装概要

Agent：

```bash
cd elderly-companion-agent
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
```

Voice gateway：

```bash
cd voice-gateway
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e .
```

详细步骤请看 `README-操作指南.md` 和 `ESDS/voice-gateway/docs/raspberry_pi.md`。

## 安全提醒

交接时应通过安全渠道单独传递树莓派上的两个配置文件：

```text
~/.config/elderly-agent/env
~/.config/esds-voice/env
```

不要把它们提交到代码仓库或放进源码压缩包。
