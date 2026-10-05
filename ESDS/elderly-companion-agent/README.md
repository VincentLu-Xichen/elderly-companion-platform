# 老人陪伴 Agent：Daily Chat 与对话式 CBT 课程

树莓派本轮情绪上下文的接口、兼容性与验证说明：[voice-emotion.md](docs/voice-emotion.md)。

这是一个用于课堂研究与角色扮演实验的 FastAPI 对话平台，包含两个相互独立的产品入口：

- **Daily Chat**：学生扮演老人，与简短、自然的日常陪聊 Agent 对话。
- **CBT 课程**：学生以学习者本人身份完成八课纯文字认知行为练习课程。

> 本项目用于系统测试、课程学习和课堂研究，不提供正式心理治疗、医疗诊断或紧急救援服务。

## 当前状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| Daily Chat | 可用 | 使用最近 12 条对话生成简短陪聊回复。 |
| CBT 第 1 课 | 可用（freeform 实验） | 由 LLM 根据本课完整对话历史自由引导，服务端处理持久化和完成标记。 |
| CBT 第 2 课 | 可用（freeform 实验） | 单次 LLM 调用根据完整本课历史自然带领三栏记录，服务端处理安全拦截、持久化和完成标记。 |
| CBT 第 3—8 课 | 待上线 | 课程目录已展示，后端流程尚未实现。 |
| 历史 CBT 角色会话 | 只读 | 仅支持查看、导出和删除，不能继续发送消息。 |
| 管理员后台 | 可用 | 支持筛选、查看、导出和删除实验记录。 |

## 产品流程

### 学生端

1. 使用独立匿名邀请码登录。
2. 确认实验数据记录告知。
3. 选择 Daily Chat 或 CBT 课程。
4. Daily Chat 会话可结束、再次查看或删除。
5. CBT 课程自动保存进度；当 freeform 模型标记本课完成后，记录转为只读。

学生端入口：

- 登录页：`http://127.0.0.1:8000/`
- 实验首页：`http://127.0.0.1:8000/app`
- CBT 课程目录：`http://127.0.0.1:8000/cbt-course`

### 管理员端

管理员可以：

- 按参与者、模式、Agent 版本、日期和状态筛选会话。
- 查看完整消息、课次、Prompt 指纹、模型元数据、耗时、错误和安全事件。
- 导出单个会话的精简 JSON、完整 JSON 或 CSV。
- 按模式和 Agent 版本批量导出已结束会话。
- 删除会话并生成管理员审计日志。

管理员入口：`http://127.0.0.1:8000/admin`

## 核心设计

### Daily Chat

`DailyChatAgent` 保持简单的公开接口：

```python
from daily_agent import DailyChatAgent

agent = DailyChatAgent()
)
```

处理流程：

```text
最近 12 条对话
    -> Daily Chat System Prompt
    -> Azure OpenAI Chat Completions
    -> 简短自然回复
```

网页侧使用 `reply_turn()` 获取回复和模型元数据；外部调用仍可使用 `reply(dialogue_history) -> str`。

#### 树莓派 Daily Chat 语音桥接

树莓派集成使用仅监听本机回环地址的内部 API，不模拟网页 Cookie 或 CSRF：

```text
百炼 ASR → POST /internal/voice/v1/sessions/{id}/turns

内部接口默认关闭。启用时必须配置 `VOICE_BRIDGE_TOKEN`、已登记的
`VOICE_DEVICE_ID` 和工程测试参与者，并显式确认当前数据记录告知。接口只支持
`daily_chat`；CBT 路由和课程状态机不进入本轮语音集成。

Daily Chat 的原始默认模型提供方仍为 Azure。树莓派可设置

CBT freeform 课程默认使用百炼 `qwen-plus`，与 Daily Chat 共用
`DASHSCOPE_API_KEY`，但使用独立配置项：

```dotenv
CBT_COURSE_PROVIDER=dashscope
CBT_COURSE_MODEL=qwen-plus
```

如需回退 CBT 到 Azure，可设置 `CBT_COURSE_PROVIDER=azure`，并配置
`AZURE_OPENAI_ENDPOINT`、`AZURE_OPENAI_API_KEY` 和课程 deployment。
`DAILY_CHAT_PROVIDER=dashscope`，通过百炼 OpenAI 兼容接口调用
`DASHSCOPE_CHAT_MODEL`。该部署使用独立 Agent 版本标签，避免与 Azure 实验批次混用。

### 对话式 CBT 课程

当前分支的 FastAPI 默认加载 `cbt_course_llm_freeform`。第 1、2 课分别使用自己的 Prompt，由 LLM 根据完整的本课对话历史自由引导：

```text
学习者本轮输入
    -> 服务端保存用户消息和 pending 审计事件
    -> FreeformCourseAgent 接收本课完整对话历史
    -> LLM 自由回复并选择附件或课程完成标记
    -> 服务端移除控制标记，保存回复、加密状态和审计结果
```

职责边界：

- `FreeformCourseAgent` 负责回应、追问、课程推进和完成时机。
- `FreeformCourseRuntime` 只解析附件白名单和课程完成标记。
- 学习者可以用“三分”或“我觉得大概三分”等自然语言回答量表，服务端不强制转为阿拉伯数字。
- 课程模型接收本课完整对话历史，但不接收角色语境卡。
- 原有确定性 `cbt_course` 保留在仓库中，但当前 FastAPI 不加载它的路由。

第 1 课依次完成：

1. 上周心境评分。
2. 选择一件具体困扰。
3. 梳理情境、想法、情绪和行为。
4. 记录想法相信程度和情绪强度。
5. 在回复正文中生成纯文本四要素回顾。
6. 完成四道概念练习。
7. 设置课程目标。
8. 布置四要素日记作业并结束本课，会话随后转为只读。

课程不会生成四栏概念图附件；用户案例会直接写入回复正文。

第 2 课依次完成近况签到、第一课练习回顾、概念复习、下雨取消公园之约的引导示例、个人三栏记录、回顾和课后练习。每轮最多调用模型一次，回复上限为 600 tokens；本地高风险词会在模型调用前暂停课程。

### 历史 CBT 兼容

旧的 Prompt-only CBT Agent 已删除。已有历史会话仍保留：

- `scenario_id`
- 语境版本
- AES-GCM 加密后的语境快照
- 原始消息与逐轮审计数据

历史记录可以继续查看、导出和删除，但不能创建同类新会话，也不能继续生成回复。历史语境快照不会进入新课程的模型请求。

## 项目结构

```text
daily_agent/
  daily_chat_agent.py       Daily Chat 公开接口
  prompt.py                 Daily Chat Prompt
  azure_chat_client.py      Azure OpenAI 客户端
  dashscope_chat_client.py  百炼 OpenAI 兼容客户端
  agent_runtime.py          丰富返回值与兼容层

cbt_course/
  ...                       原有确定性课程实现（当前不加载）
  assets/                   课程教学图片

cbt_course_llm_freeform/
  runtime.py                自由课程运行时与控制标记解析
  agent.py                  基于本课完整历史生成自由回复
  prompt.py                 第 1 课蓝图与 System Prompt
  services.py               课程持久化、幂等和审计
  router.py                 当前 FastAPI 加载的课程页面和 API

webapp/
  main.py                   FastAPI 主应用和通用路由
  services.py               Daily Chat、历史兼容、导出和审计
  models.py                 SQLAlchemy 数据模型
  security.py               Argon2、会话签名、CSRF、AES-GCM
  voice_bridge.py           树莓派 Daily Chat 本机内部接口
  templates/                Jinja2 页面
  static/                   原生 JavaScript 和 CSS

migrations/                 Alembic 数据库迁移
scripts/bootstrap_database.py
                            部署环境的迁移与邀请码初始化
tests/                      单元、服务和网页回归测试
```

## 快速开始

### 环境要求

- Python 3.10 或更高版本。
- SQLite 用于本地开发，PostgreSQL/Supabase 用于部署。
- 可访问的 Azure OpenAI Chat Completions deployment。

### 1. 创建环境并安装依赖

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell：

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### 2. 配置本地环境

本地 `.env` 至少应调整为：

```dotenv
APP_ENV=development
DATABASE_URL=sqlite:///./roleplay_chat.db
DATABASE_POOL_MODE=application
COOKIE_SECURE=false
```

同时设置：

```dotenv
APP_SECRET=本地随机长字符串
DATA_ENCRYPTION_KEY=URL-safe-Base64-encoded-32-byte-key
INVITE_CODES=student-001:你的测试邀请码
ADMIN_PASSWORD=你的本地管理员密码

AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=replace-key
AZURE_OPENAI_DEPLOYMENT=replace-deployment
AZURE_OPENAI_COURSE_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

`AZURE_OPENAI_COURSE_DEPLOYMENT` 可以留空；留空时课程复用 `AZURE_OPENAI_DEPLOYMENT`。

可以用下面的命令生成 `DATA_ENCRYPTION_KEY`：

```bash
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

不要提交本地 `.env`。部署后也不要随意更换 `DATA_ENCRYPTION_KEY`，否则已有加密数据将无法解密。

### 3. 执行迁移并启动网页

macOS / Linux：

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn webapp.main:app --host 127.0.0.1 --port 8000 --reload
```

Windows PowerShell：

```powershell
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\uvicorn.exe webapp.main:app --host 127.0.0.1 --port 8000 --reload
```

健康检查：`http://127.0.0.1:8000/healthz`

非 Vercel 环境启动时会初始化表结构并同步 `.env` 中的邀请码；正式数据库仍应以 Alembic migration 为准。

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `APP_ENV` | `development` 或 `production`。 |
| `DATABASE_URL` | SQLite 或 PostgreSQL/Supabase 连接字符串。 |
| `DATABASE_POOL_MODE` | `application` 或 Supabase Transaction Pooler 使用的 `transaction`。 |
| `APP_SECRET` | 会话签名和本地派生密钥使用的应用密钥。 |
| `DATA_ENCRYPTION_KEY` | URL-safe Base64 编码的 32 字节 AES-GCM 密钥。 |
| `INVITE_CODES` | `参与者标签:邀请码` 的逗号分隔列表。 |
| `ADMIN_PASSWORD` | 管理员后台密码。 |
| `CONSENT_VERSION` | 当前数据记录告知版本。 |
| `DAILY_CHAT_AGENT_VERSION` | Daily Chat 实验版本。 |
| `CBT_COURSE_AGENT_VERSION` | CBT 课程 Agent 实验版本。 |
| `COOKIE_SECURE` | HTTPS 部署时应为 `true`。 |
| `SESSION_HOURS` | 登录会话有效期。 |
| `MAX_MESSAGE_CHARS` | 单条消息长度上限。 |
| `RATE_LIMIT_PER_MINUTE` | 数据库共享限流阈值。 |
| `AZURE_OPENAI_*` | Azure endpoint、key、deployment 和 API version。 |

修改 Agent Prompt 或行为逻辑时，应递增对应的 Agent 版本。新会话会冻结 `agent_version` 和 System Prompt 的 SHA-256 指纹，已有会话不会被覆盖。

## 主要 API

### 通用学生 API

```text
POST   /api/session/invite
POST   /api/session/logout
POST   /api/consents
POST   /api/conversations
GET    /api/conversations/{conversation_id}
POST   /api/conversations/{conversation_id}/messages
POST   /api/conversations/{conversation_id}/end
DELETE /api/conversations/{conversation_id}
```

`POST /api/conversations` 只创建 Daily Chat，通用消息接口也只接受 Daily Chat。新的 CBT 会话和消息必须使用课程专用 API；历史 CBT 会话会被拒绝。

### CBT 课程

```text
GET  /cbt-course
POST /api/cbt-course/lessons/{lesson_id}/start
GET  /cbt-course/conversations/{conversation_id}
GET  /api/cbt-course/conversations/{conversation_id}
POST /api/cbt-course/conversations/{conversation_id}/messages
```

### 管理员导出

```text
GET /admin/exports/{conversation_id}.json
GET /admin/exports/{conversation_id}/full.json
GET /admin/exports/{conversation_id}.csv
GET /admin/exports/bulk/ended-dialogues.json
GET /admin/exports/bulk/ended.json
```

所有写请求均经过服务端权限校验；浏览器不会直接调用 Azure OpenAI。

## 数据与安全

- 邀请码在数据库中使用 Argon2 哈希保存。
- 消息、课程状态、附件、课后练习、语境快照、Trace 和错误详情使用 AES-GCM 加密。
- 模型调用前先保存用户消息和 pending `TurnEvent`。
- 成功、失败和超时均保留可追踪审计记录。当前 freeform 实验尚未输出结构化安全分类。
- 同一会话使用幂等键和数据库串行处理，避免重复消息和并发模型调用。
- 应用日志只记录匿名 participant ID、conversation ID、request ID 和状态，不记录聊天正文。
- 不同邀请码不能读取彼此的会话。
- 管理员删除行为会写入审计日志。

当前 freeform 课程使用普通 Chat Completions 文本输出，不要求 `json_schema`。服务端只接受白名单内的附件标记和固定的课程完成标记。

## 测试

完整回归测试：

```bash
.venv/bin/python -m unittest discover tests -v
.venv/bin/python -m unittest discover cbt_course_llm_freeform/tests -v
```

Windows：

```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
.venv\Scripts\python.exe -m unittest discover cbt_course_llm_freeform\tests -v
```

附加检查：

```bash
.venv/bin/python -m compileall -q daily_agent cbt_course cbt_course_llm_freeform webapp tests
node --check webapp/static/app.js
node --check webapp/static/cbt_course/course.js
```

测试覆盖：

- Daily Chat 包导出、公开接口和网页集成。
- 历史 CBT 记录的查看、导出和只读限制。
- freeform 第 1 课的完整历史输入、控制标记白名单和完成处理。
- 课程状态刷新恢复、幂等、失败审计和完成后只读。
- 本课完整对话历史传递及角色语境隔离。
- 加密、幂等、失败审计和参与者隔离；原确定性实现的测试仍覆盖安全分类。
- 管理员详情、JSON/CSV 导出和删除。
- Vercel/Supabase 数据库连接配置。

浏览器冒烟脚本位于 `tests/playwright_course_smoke.py`，用于检查桌面端和移动端课程页面、无横向溢出、教学图片和纯文字交互。

## 部署

当前部署目标为 Vercel + Supabase：

- 根目录 `app.py` 是 Vercel ASGI 入口。
- `vercel.json` 将单次 Function 最长执行时间设置为 90 秒。
- Vercel 冷启动不会执行建表或邀请码初始化。
- 部署前必须单独运行 Alembic migration 和 `scripts.bootstrap_database`。

完整步骤参见：

- [Vercel + Supabase 部署手册](docs/VERCEL_SUPABASE_DEPLOYMENT.md)

## 当前限制

- 网页模式由学生明确选择，没有自动 Mode Router。
- 当前第 1、2 课开放，第 3—8 课只有目录占位。
- 没有长期跨 session Memory。
- 网页应用本身不直接采集或播放音频；树莓派通过独立 `voice-gateway` 提供百炼 ASR/TTS，并只接入 Daily Chat。
- 历史 Prompt-only CBT 会话仅保留兼容读取能力。
