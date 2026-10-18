# ESDS × Elderly Companion Agent

当前产品现状、想法和开发顺序统一见[产品](../docs/PRODUCT.md)、[想法](../docs/IDEAS.md)、[当前目标](../docs/ROADMAP.md)与[决策](../docs/DECISIONS.md)。本文件继续保留原语音验收范围；实际能力与历史范围的差异见产品文档及 TD-03，不据旧说明判断当前功能缺失。

本目录包含两个独立工作区：

- `voice-gateway/`：树莓派麦克风、VAD、百炼 ASR、情绪表达、百炼 TTS 与扬声器。
- `elderly-companion-agent/`：Daily Chat Prompt、加密会话持久化、幂等和审计。

当前验收范围仅为：

```text
创乐博麦克风
  → 百炼 Qwen ASR
  → Daily Chat Agent（百炼 qwen-plus）
  → 百炼 Qwen TTS
  → 创乐博模块扬声器
```

CBT 课程和视觉附件尚未接入语音链路，不在当前验收范围。

## 树莓派目录与服务

```text
/home/esds/ESDS/voice-gateway
/home/esds/ESDS/elderly-companion-agent

elderly-agent.service
esds-voice.service
esds-pi-audio.service
```

Agent 只监听 `127.0.0.1:8000`。ESDS 使用独立 Bearer Token 调用内部
Daily Chat API。百炼 Key 和数据库加密密钥只保存在树莓派权限为 `600`
的环境文件中。

## 配置与同意门禁

首次生成私密配置时不自动确认持久化数据记录：

```bash
cd /home/esds/ESDS/voice-gateway
.venv/bin/python scripts/configure_integrated_pi.py
```

当前工程测试参与者明确同意持久化保存转写文本、Agent 回复和审计元数据后，
再显式执行：

```bash
.venv/bin/python scripts/configure_integrated_pi.py --acknowledge-consent
```

原始 PCM 音频不写入 Agent 数据库。

## 回归测试

```bash
cd /home/esds/ESDS/voice-gateway
.venv/bin/python -m unittest discover -s tests -v

cd /home/esds/ESDS/elderly-companion-agent
.venv/bin/python -m unittest discover tests -v
```
