# ESDS 便携源码包操作指南

本包用于把当前已验收的 ESDS 语音系统迁移到另一台 macOS/Linux 电脑，或由新电脑继续部署到 Raspberry Pi 5。

当前语音闭环：

```text
麦克风 → 百炼 Qwen ASR → Daily Chat Agent（qwen-plus）
       → 加密持久化与审计 → 百炼 Qwen TTS → 扬声器
```

CBT freeform 第 1、2 课已包含在 Agent 源码中，但尚未接入树莓派语音链路；视觉功能也未接入。

## 1. 包内结构

```text
ESDS-Portable-20260901/
├── README-操作指南.md
├── SOURCE_STATE.md
├── PACKAGE_CONTENTS.txt
├── tools/
│   ├── setup.sh
│   ├── configure_local.py
│   ├── run_desktop.py
│   └── test_all.sh
└── ESDS/
    ├── voice-gateway/
    └── elderly-companion-agent/
```

没有包含以下内容：

- 百炼/Azure API Key、设备 Token、数据库加密密钥和管理员密码；
- `.env`、树莓派 `~/.config/*/env` 和真实数据库；
- `.venv`、Git 对象、Python 缓存、日志、录音与模型权重。

## 2. 校验和解压

将压缩包及同名 `.sha256` 文件放在同一目录：

```bash
shasum -a 256 -c ESDS-Portable-20260901.tar.gz.sha256
tar -xzf ESDS-Portable-20260901.tar.gz
cd ESDS-Portable-20260901
```

Linux 也可以使用：

```bash
sha256sum -c ESDS-Portable-20260901.tar.gz.sha256
```

## 3. 新电脑要求

- macOS 13+ 或常见 64 位 Linux；
- Python 3.11–3.13；
- 可访问 Python 包源和阿里云百炼；
- 浏览器允许 `http://127.0.0.1:8080` 使用麦克风；
- 树莓派硬件部署时，需要 SSH 和 `rsync`。

检查：

```bash
python3 --version
ssh -V
rsync --version
```

## 4. 新电脑一键安装依赖

```bash
chmod +x tools/setup.sh tools/test_all.sh
./tools/setup.sh
```

脚本会分别创建：

```text
ESDS/voice-gateway/.venv
ESDS/elderly-companion-agent/.venv
```

虚拟环境不能跨电脑复制，因此必须在新电脑重新创建。

运行全部离线回归：

```bash
./tools/test_all.sh
```

## 5. 在新电脑体验浏览器语音闭环

首次配置会隐藏读取百炼 Key，并将新生成的本机配置写入 `.runtime/`，权限为 `600`：

```bash
python3 tools/configure_local.py
```

此时同意门禁仍为关闭。只有当前测试参与者明确同意保存转写文本、Agent 回复和审计元数据后，才执行：

```bash
python3 tools/configure_local.py --acknowledge-consent
python3 tools/configure_local.py --check
```

系统不保存原始 PCM 音频。启动：

```bash
python3 tools/run_desktop.py
```

浏览器通常会自动打开 `http://127.0.0.1:8080`。允许麦克风权限后即可说话。停止时在终端按 `Ctrl+C`。

如果不希望自动打开浏览器：

```bash
python3 tools/run_desktop.py --no-open
```

本机运行数据位于：

```text
.runtime/roleplay_chat.db
.runtime/agent.env
.runtime/voice.env
```

不要上传或分享 `.runtime/`。

## 6. CBT 网页说明

包内 Agent 默认加载 freeform CBT 第 1、2 课。Daily Chat 使用百炼；CBT 上游实现仍使用 Azure OpenAI，因此仅运行 Daily Chat 不需要 Azure 配置。

若需要测试 CBT 网页，请在 `.runtime/agent.env` 中另外配置：

```dotenv
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=...
AZURE_OPENAI_COURSE_DEPLOYMENT=...
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

CBT 尚未接入语音链路；不要把它误认为已经完成无视觉语音改造。

## 7. 从新电脑同步源码到树莓派

先保证新电脑与树莓派处于同一局域网，并确认：

```bash
ssh -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> 'hostname; hostname -I'
```

源码包故意不包含 SSH 私钥。推荐在新电脑生成新钥：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/esds_pi_ed25519 -C esds-new-computer
```

然后通过树莓派本地终端或仍能连接树莓派的旧电脑，把新公钥追加到 `/home/esds/.ssh/authorized_keys`。公钥可以普通传输，私钥不能放入本源码包或 Git。

### 7.1 先备份树莓派现有状态

```bash
ssh -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> \
  'mkdir -p ~/ESDS-backups && tar -czf ~/ESDS-backups/source-before-update.tar.gz -C ~/ESDS voice-gateway elderly-companion-agent'
```

数据库应使用 SQLite 在线备份，而不是在服务运行时直接复制：

```bash
ssh -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> \
  "python3 -c 'import sqlite3; src=sqlite3.connect(\"/home/esds/.local/share/elderly-agent/roleplay_chat.db\"); dst=sqlite3.connect(\"/home/esds/ESDS-backups/roleplay_chat-before-update.db\"); src.backup(dst); dst.close(); src.close()' && chmod 600 /home/esds/ESDS-backups/roleplay_chat-before-update.db"
```

### 7.2 仅同步源码

在便携包根目录执行：

```bash
rsync -az -e 'ssh -i ~/.ssh/esds_pi_ed25519' \
  --exclude='.venv' --exclude='.env' --exclude='*.db' --exclude='__pycache__' \
  ESDS/voice-gateway/ esds@<PI_IP>:/home/esds/ESDS/voice-gateway/

rsync -az -e 'ssh -i ~/.ssh/esds_pi_ed25519' \
  --exclude='.venv' --exclude='.env' --exclude='*.db' --exclude='__pycache__' \
  ESDS/elderly-companion-agent/ esds@<PI_IP>:/home/esds/ESDS/elderly-companion-agent/
```

不要使用 `--delete`，不要覆盖树莓派的 `~/.config/esds-voice/env`、`~/.config/elderly-agent/env` 或数据库。

### 7.3 安装/更新树莓派依赖

全新 Raspberry Pi OS Lite 先安装系统包：

```bash
ssh -t -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> \
  'sudo apt-get update && sudo apt-get install -y python3-venv python3-dev build-essential alsa-utils rsync'
```

再创建两个独立虚拟环境：

```bash
ssh -t -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> '
  cd ~/ESDS/voice-gateway &&
  test -x .venv/bin/python || python3 -m venv .venv &&
  .venv/bin/pip install -e . &&
  cd ~/ESDS/elderly-companion-agent &&
  test -x .venv/bin/python || python3 -m venv .venv &&
  .venv/bin/pip install -r requirements.txt
'
```

网络较慢时，可为 pip 添加：

```text
-i https://mirrors.aliyun.com/pypi/simple --timeout 120 --retries 10
```

### 7.4 数据库迁移与测试

```bash
ssh -t -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> '
  set -a; . ~/.config/elderly-agent/env; set +a
  cd ~/ESDS/elderly-companion-agent
  .venv/bin/alembic upgrade head
  .venv/bin/python -m unittest discover tests -v
  .venv/bin/python -m unittest discover cbt_course_llm_freeform/tests -v
  cd ~/ESDS/voice-gateway
  .venv/bin/python -m unittest discover -s tests -v
'
```

### 7.5 安装服务（新树莓派）

已经部署过的树莓派只需更新源码、依赖并重启；全新树莓派执行：

```bash
ssh -t -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> '
  mkdir -p ~/.config/systemd/user
  install -m 0644 ~/ESDS/elderly-companion-agent/deploy/raspberry-pi/elderly-agent.service ~/.config/systemd/user/
  install -m 0644 ~/ESDS/voice-gateway/deploy/raspberry-pi/esds-voice.service ~/.config/systemd/user/
  install -m 0644 ~/ESDS/voice-gateway/deploy/raspberry-pi/esds-pi-audio.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable elderly-agent.service esds-voice.service esds-pi-audio.service
'
```

全新树莓派先输入百炼 Key，再生成 Agent Bridge 与加密持久化配置：

```bash
ssh -tt -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> \
  'cd ~/ESDS/voice-gateway && exec .venv/bin/python -u scripts/configure_pi.py'

ssh -tt -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> \
  'cd ~/ESDS/voice-gateway && exec .venv/bin/python -u scripts/configure_integrated_pi.py'
```

同意门禁只能在当前工程测试参与者已明确同意保存转写文本、Agent 回复和审计元数据后开启：

```bash
ssh -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> \
  'cd ~/ESDS/voice-gateway && .venv/bin/python scripts/configure_integrated_pi.py --acknowledge-consent && .venv/bin/python scripts/configure_integrated_pi.py --check'
```

### 7.6 重启与验收

```bash
ssh -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> '
  systemctl --user restart elderly-agent.service
  systemctl --user restart esds-voice.service
  systemctl --user restart esds-pi-audio.service
  sleep 5
  systemctl --user is-active elderly-agent.service esds-voice.service esds-pi-audio.service
  curl -fsS http://127.0.0.1:8000/healthz
'
```

三项服务都应显示 `active`。随后对模块麦克风说一句完整中文，检查：

```bash
ssh -i ~/.ssh/esds_pi_ed25519 esds@<PI_IP> \
  'journalctl --since "2 minutes ago" --no-pager --user-unit=elderly-agent.service --user-unit=esds-voice.service --user-unit=esds-pi-audio.service'
```

应看到 `voice_turn_complete ... status=success`、`assistant transcript` 和 `playback drained`。

## 8. 数据迁移与隐私

代码包不含真实数据库。若需要迁移历史对话，必须同时安全迁移：

1. 加密数据库；
2. 对应的 `DATA_ENCRYPTION_KEY`；
3. Bridge Token 与设备 ID。

缺少原加密密钥将无法读取历史数据。包含密钥的环境文件应通过加密磁盘或受控 SSH 传输，不能放入普通网盘、邮件或 Git。

## 9. 常见故障

- `Connection refused`：先检查 Agent 8000 端口，再检查网关 8765 端口。
- `VOICE_CONSENT_ACKNOWLEDGED`：尚未明确确认数据记录同意。
- 麦克风没有反应：检查浏览器权限、输入设备、VAD 阈值；树莓派检查 `arecord -l`。
- 模块扬声器无声：检查 `aplay -l`、ALSA 卡名和 `esds-pi-audio.service` 日志。
- 百炼 401/403：重新配置 Key，不要把 Key 粘贴到日志或聊天中。
- 新电脑无法 SSH 树莓派：确保两者处于同一局域网；手机热点与有线路由器通常不是同一网段。

## 10. 回滚

如果更新后 Agent 无法启动，先停止三项服务，将 `~/ESDS-backups/source-before-update.tar.gz` 解压回 `~/ESDS`，恢复数据库备份及原环境文件后，再执行 `systemctl --user daemon-reload` 和服务重启。不要使用 `git reset --hard` 或删除当前数据库。
