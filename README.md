# 第一课 · 最小运行版

当前版本：**9.16-supportive-dialogue**。独立运行的第一课测试程序，使用 DeepSeek，包含自然语言教学、交流与返回、流式回复，以及本地加密记录。

## 安装与启动（macOS）

需要已安装的 **Python 3.11—3.13**。

```sh
git clone --single-branch --branch codex/lesson1-minimal-9.16 https://github.com/VincentLu-Xichen/elderly-companion-platform.git
cd elderly-companion-platform
python3 setup_env.py
cp .env.example .env
open -e .env
```

在 `.env` 中填写自己的 `DEEPSEEK_API_KEY` 并保存，然后启动：

```sh
.venv/bin/python run.py
```

浏览器打开 **http://127.0.0.1:8080/**，使用邀请码 **course-pilot** 登录，阅读并确认数据告知后进入第一课。

- 其他测试者可分别使用 `course-eval`、`course-003`。不同测试者请使用不同邀请码；可在 `.env` 的 `INVITE_CODES` 中增加代码。
- 端口占用时：`.venv/bin/python run.py --port 8085`，打开 **http://127.0.0.1:8085/**。
- 停止：终端按 `Ctrl+C`。在同一目录重新启动即可继续原记录。
- 配置检查：`.venv/bin/python run.py --check`，不会调用模型，但会初始化本地数据目录和恢复密钥。

`setup_env.py` 会寻找已安装的兼容 Python 并创建 `.venv`，安装 `requirements.txt` 中锁定的依赖；不会自动安装 Python。Linux 使用相同启动命令；Windows 将 `.venv/bin/python` 改为 `.venv\Scripts\python.exe`。本版已在 macOS/Python 3.13 验证，其他系统未实机验证。

## 目录

| 文件或目录 | 用途 |
| --- | --- |
| `run.py` | 唯一启动入口与本地配置 |
| `setup_env.py`、`requirements.txt` | 安装环境与依赖 |
| `.env.example` | 配置模板，填写后保存为 `.env` |
| `lesson1_dialogue/` | Prompt、状态、动作校验、反思与流式处理 |
| `lesson1_contracts/` | 共享数据结构 |
| `lesson1_support/` | 课程材料与模型连接 |
| `webapp/` | 登录、数据保存和测试网页 |

## 记录与配置

首次启动会生成 `data/`，保存本机数据库和恢复密钥 `local-secrets.json`。备份时保留整个 `data/`，否则旧加密记录可能无法恢复。`.env`、`data/`、虚拟环境和本地日志已加入 Git 忽略规则，请勿强行提交。

程序仅监听本机。发送文字会调用付费模型，条件反思也可能产生额外调用；登录、刷新、查看记录不调用模型。本分支不含现有密钥、真实用户记录、历史版本、第二课或测试工具。

## 当前范围与限制

仅供第一课本机试用与验收。9.16 已通过离线程序检查、前端模拟和本机 HTTP/SSE 模拟；这些结果不能代替真实模型的多轮表现评估。本次上传没有改变模型参数或课程规则，没有新增真实模型测试。

已知仍需关注：偶发模型连接失败；部分求助与课程举例混合时的意图判断；少量重复承接；条件反思的引用校验。失败时按页面提示核对或重试原消息。发现问题请记录操作步骤和实际表现，反馈前遮去个人内容与密钥。
