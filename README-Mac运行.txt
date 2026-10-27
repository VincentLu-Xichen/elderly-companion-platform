项目：/Users/harrison/Documents/elderly-companion-platform

启动方法
1. 在访达打开项目文件夹，双击「启动网页-Mac.command」。
2. 浏览器访问 http://127.0.0.1:8000/
3. 本机测试邀请码：mac-local-2026
4. 根据网页告知，自行确认测试数据记录后进入 CBT 课程。
5. 停止：在启动的终端中按 Ctrl+C。当前服务已经启动，无需重复启动。

也可在终端运行：
cd /Users/harrison/Documents/elderly-companion-platform
./ESDS/elderly-companion-agent/.venv/bin/python -B tools/run_web_mac.py

已完成
- 安装独立 Python 3.13.17，路径在 /Users/harrison/Documents/Codex/runtimes/python/。
- 重建 Agent 和 voice-gateway 的 Mac 虚拟环境；Windows 环境保留为 .venv-windows-backup-20261025。
- 修复 setup.sh、test_all.sh 的 Windows 换行及执行权限。
- 添加 tools/run_web_mac.py、启动网页-Mac.command。
- 本地网页配置保存在 .runtime/web.env，数据库为 .runtime/web.db，与原配置和历史数据分开。
- 原 Agent .env 中的 DeepSeek 配置保留；启动时显式加载，避免继承旧进程覆盖。
- 修正语音网关旧测试的 JSON 模拟响应，使其匹配现有 SSE 流协议；业务代码未改。

验证
- 语音网关 104 项、Agent 56 项、CBT 221 项，共 381 项离线测试通过。
- 两个虚拟环境 pip check 通过，Python 编译检查通过。
- 新空数据库 Alembic 升级通过；网页启动及测试邀请码登录通过。
- DeepSeek /models 认证通过，当前配置模型在返回列表中。未调用付费对话生成。

尚未验证或配置
- 未验证真实模型生成、完整课程体验或麦克风语音链路。
- Daily Chat 和语音的百炼/Azure 配置未提供，暂不能视为可用。
- 未代替用户同意记录真实测试数据；网页中的同意步骤由测试者自行完成。
- 管理员密码随机生成，保存在 .runtime/web.env，勿分享此文件。
- API 密钥、加密密钥和本机运行数据不要上传；.runtime 和旧环境备份已加入本地 Git 排除。
- 保留原有未提交代码，未 commit、tag 或 push。
