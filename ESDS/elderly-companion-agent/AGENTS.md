# AGENTS.md

本文件是本仓库中所有 Agent 的长期工作上下文。开始任务、恢复任务或对话被清空后，必须先完整阅读本文件，再执行任何修改。

## 1. 项目目标

这是一个用于课堂研究的“老人陪伴 Agent”实验项目，包含两种产品入口：

- `DailyChatAgent`：自然、简短的日常陪聊 baseline。
- `cbt_course_llm_freeform`：当前网页默认加载的自由 LLM CBT 实验；第 1、2 课使用各自 Prompt，服务端负责持久化、幂等、审计和白名单控制标记。
- `cbt_course`：保留的确定性课程实现与历史兼容代码，不是当前网页默认路由。

项目是 FastAPI 网页实验平台。学生通过匿名邀请码登录，扮演老年人与 Agent 对话；研究人员在管理员后台查看并导出实验数据。

树莓派 Daily Chat 集成另提供默认关闭的本机内部语音桥接。该桥接只调用
`process_turn`，保留消息加密、幂等和审计；不接入或修改 CBT 课程。设备接口
必须使用 Bearer Token、已登记设备 ID 和显式的数据记录同意，不能绕过同意门禁。

旧的 Prompt-only CBT Agent 已删除。旧 CBT 角色语境会话只作为历史数据支持查看、导出和删除，不能继续发送消息或生成回复。

当前项目用于系统测试和课堂角色扮演，不是正式心理治疗、医疗诊断或紧急救援服务。

## 2. 当前产品行为

### 学生端

1. 使用独立匿名邀请码登录。
2. 确认实验数据记录告知。
3. 选择 `Daily Chat` 或 `CBT 课程`。
4. Daily Chat 由学生扮演老人进行陪聊实验。
5. CBT 进入八课目录，以学习者本人身份通过文字对话完成课程；当前开放第 1、2 课。
6. Daily Chat 可结束、恢复查看或删除；课程自动保存进度，完成后可继续记录课后日记。

### 历史 CBT 语境数据

历史记录中主要包含：

- `loneliness`
- `children_relationship`
- `health_anxiety`

这些语境卡不再用于创建新会话。历史兼容最重要的不变量：

- 历史语境快照必须继续支持管理员查看和导出。
- 语境卡不得拼接到课程 Agent 的 system prompt、user prompt 或模型请求中。
- 新 CBT 课程不得创建或读取角色语境卡。
- 数据库必须保存 `scenario_id`、版本和加密后的语境快照，以便复现实验。

### 管理员端

- 按参与者、模式、语境、日期和状态筛选会话。
- 查看完整对话、实现标记、模型元数据、耗时、错误和安全事件。
- 导出单个会话的 JSON 或 CSV。
- 删除会话，并记录管理员审计日志。

## 3. 代码结构

```text
daily_agent/               Daily Chat Agent、Prompt 与版本元数据
cbt_course/                保留的确定性课程后端与课程内容图片
cbt_course_llm_freeform/   当前默认的自由 LLM CBT 第 1、2 课

webapp/main.py             FastAPI 页面与 API 路由
webapp/services.py         会话、消息、Agent 调用、审计和导出服务
webapp/models.py           SQLAlchemy 数据模型
webapp/security.py         Argon2、会话签名、CSRF、AES-GCM 加解密
webapp/voice_bridge.py     树莓派 Daily Chat 本机内部接口
webapp/templates/          Jinja2 页面，包含 CBT 课程页面
webapp/static/             原生 JavaScript 与 CSS，包含 CBT 课程前端

migrations/                Alembic 数据库迁移
tests/                     Agent 与网页测试
```

## 4. 数据与安全约束

- Azure API Key、数据库密码、加密密钥和管理员密码只能通过环境变量或 `.env` 注入。
- 永远不要提交、打印或在回复中暴露 `.env` 与任何真实密钥。
- `.env.example` 只能包含占位值。
- 邀请码在数据库中使用 Argon2 哈希保存。
- 消息正文、语境快照、Trace 和错误详情使用 AES-GCM 加密保存。
- 浏览器不得直接调用 Azure OpenAI；所有模型调用必须经过服务端。
- 模型调用前先持久化用户消息和 pending 审计事件。
- 成功、失败、超时和课程模型安全分类都必须产生可追踪的 `TurnEvent`。
- 同一会话需要幂等键和串行处理，避免重复消息或并发模型调用。
- 数据库保存完整历史；Daily Chat 传最近 12 条，课程模型只接收当前步骤、本轮输入和该步骤必要的已收集字段。
- 应用日志只能记录匿名 participant ID、conversation ID、request ID 和状态，不记录聊天正文。

## 5. Agent 行为约束

- Daily Chat 保持公开接口兼容：`agent.reply(dialogue_history) -> str`。
- Daily Chat 网页侧丰富结果通过 `reply_turn()` 和 `AgentTurnResult` 提供。
- 修改当前 freeform CBT 课程时必须保留并验证：
  - 每节课按 `lesson_id` 使用自己的 Prompt、版本与 Prompt 指纹，旧版本课程只读。
  - 服务端只解析白名单附件与完成标记；模型不能执行任意控制指令。
  - 第 2 课每轮最多调用模型一次、最多生成 600 tokens，本地高风险词在模型调用前暂停课程。
  - 课程模型只接收同一节课的对话历史，不得接收老人角色语境卡。
  - 课程状态、消息、课后记录、错误和 Trace 必须加密保存，所有轮次保留幂等与审计。
- 不再新增角色语境卡；历史语境数据只用于兼容和实验复现。
- 不要把本项目描述为医疗产品或让 Agent 作出诊断。

## 6. 本地开发

### 首次安装

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

本地 `.env` 至少应使用：

```dotenv
APP_ENV=development
DATABASE_URL=sqlite:///./roleplay_chat.db
COOKIE_SECURE=false
```

同时配置 Azure OpenAI endpoint、API key、deployment 和 API version。不要把实际值写入文档。

### 数据库迁移

```bash
.venv/bin/alembic upgrade head
```

### 启动网页

```bash
.venv/bin/uvicorn webapp.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload \
  --env-file .env
```

访问：

- 学生端：`http://127.0.0.1:8000/`
- 管理员端：`http://127.0.0.1:8000/admin`
- 健康检查：`http://127.0.0.1:8000/healthz`

不要假设网页服务仍在运行。恢复任务时应先检查端口或健康检查，再决定是否启动；不要重复占用 8000 端口。

## 7. 验证要求

任何代码修改后至少执行：

```bash
.venv/bin/python -m unittest discover tests -v
```

当前回归测试覆盖 Daily Chat、历史 CBT 只读兼容、课程流程以及网页的邀请登录、同意、加密、幂等、失败审计、页面路由、导出与删除。

涉及不同层级时还应执行：

- Python 语法：`.venv/bin/python -m compileall -q daily_agent cbt_course cbt_course_llm_freeform webapp tests`
- JavaScript 语法：`node --check webapp/static/app.js`
- 迁移：在临时空数据库执行 `alembic upgrade head`。
- 页面：检查 `/healthz`、登录页、CBT 课程目录、课程对话页和管理员详情页。
- 部署：核对 `vercel.json`，并按 Vercel + Supabase 部署文档完成验收。

测试必须特别证明：

- 历史 CBT 记录保持可查看和导出，但不能继续发送消息。
- 语境卡文本没有进入课程模型消息。
- Daily Chat 和 CBT 课程都不创建角色语境卡。
- 课程状态在刷新和重启后保持不变。
- 模型成功、错误和安全分类都有审计记录。
- 不同邀请码不能读取彼此会话。

## 8. 修改与 Git 规则

- 工作区可能包含用户尚未提交的实现，先运行 `git status --short`，不得覆盖或丢弃现有修改。
- 未经用户明确要求，不执行 `git reset --hard`、`git checkout --`、删除数据库或删除用户数据。
- 不修改与当前需求无关的文件。
- 数据模型变化必须新增或更新 Alembic migration，并验证空库升级。
- API 行为变化必须同步测试和 README/规格文档。
- 保持环境变量模板、Vercel 配置和部署文档一致。

## 9. Spec-Driven Development 方向

用户希望后续使用 Spec-Driven Development（SDD）形式开发。

当前阶段只要求先建立本 `AGENTS.md`；尚未创建正式 SDD 目录与模板。后续用户确认后，优先采用：

- 中文为主。
- Spec Kit 兼容结构。
- 严格的“先规格、后实现”门禁。
- 每个功能先明确需求、用户场景、接口/数据影响、验收条件，再生成 plan 和 tasks。

在正式 SDD 文档建立后，应以规格为需求真相来源，并在本节加入对应入口链接。

## 10. 对话清空后的恢复流程

新 Agent 或清空上下文后的 Agent 必须按以下顺序恢复：

1. 完整阅读根目录 `AGENTS.md`。
2. 阅读 `README.md` 和与任务相关的文档。
3. 执行 `git status --short`，确认现有未提交修改。
4. 使用 `rg` 定位相关入口、测试和数据模型，不凭记忆重写。
5. 如果任务与网页运行有关，检查 `/healthz` 或 8000 端口，不假设服务仍在运行。
6. 如果任务涉及 Azure，只检查变量是否存在，不输出变量值。
7. 修改前确认不会违反“语境卡不得传给 Agent”等关键不变量。
8. 完成后运行与风险相匹配的测试并报告结果。

## 11. 与用户协作方式

- 默认使用中文交流。
- 先给结果，再说明关键实现和验证情况。
- 对能够从仓库发现的事实先检查文件，不询问用户。
- 产品偏好、SDD 门禁或会显著改变实现的选择，优先使用 Question UI 提问；Question UI 不可用时再用一句简短问题确认。
- 用户要求实现时应完成安全范围内的实现和验证，而不是只给建议。
- 用户要求诊断时先说明原因，不在未授权情况下扩大修改范围。
