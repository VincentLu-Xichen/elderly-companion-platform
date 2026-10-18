# AGENTS.md

本文件是本仓库中所有 Agent 的长期工作上下文。开始任务、恢复任务或对话被清空后，必须先完整阅读本文件，再执行任何修改。

工作区统一产品管理入口位于[根 AGENTS](../../AGENTS.md)、[产品](../../docs/PRODUCT.md)、[想法](../../docs/IDEAS.md)、[当前目标](../../docs/ROADMAP.md)与[决策](../../docs/DECISIONS.md)。新想法默认收集，不等于实施授权；当前目标以根 Roadmap 为准，不能把下文历史待办自动当成并行开发任务。本文件继续约束模块安全、SDD 与工程实现，详细规格仍保留在本模块 `specs/`。

## 1. 项目目标

这是一个用于课堂研究的“老人陪伴 Agent”实验项目，包含两种产品入口：

- `DailyChatAgent`：自然、简短的日常陪聊 baseline。
- `cbt_course_llm_freeform`：当前网页默认加载的 CBT 实现；八课使用各自材料和共享契约，服务端控制教学阶段、可配置课内反思、本人确认、分支选择、完成与课间引用。
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
5. CBT 进入八课目录，以学习者本人身份完成课程；八课均开放，第 5、7 课由本人二选一路径，第 8 课可授权回顾多个前课成果。
6. Daily Chat 可结束、恢复查看或删除；课程自动保存阶段与学习记录，完成后查看已确认成果、课后选择和教学复盘。

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
cbt_course_llm_freeform/   当前默认的结构化对话 CBT 八课

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
- 数据库保存完整历史；Daily Chat 传最近 12 条，课程教学模型接收本课最近 24 条、当前阶段与必要记录，课后复盘接收本课最近 40 条与本人反馈。
- 应用日志只能记录匿名 participant ID、conversation ID、request ID 和状态，不记录聊天正文。

## 5. Agent 行为约束

- Daily Chat 保持公开接口兼容：`agent.reply(dialogue_history) -> str`。
- Daily Chat 网页侧丰富结果通过 `reply_turn()` 和 `AgentTurnResult` 提供。
- 修改当前 freeform CBT 课程时必须保留并验证：
  - 每节课按 `lesson_id` 使用自己的 Prompt、版本与 Prompt 指纹，旧版本课程只读。
  - 服务端只接受白名单结构化字段和本课可验证摘录；模型不能直接确认记录、完成课程或授予跨课权限。
  - 普通教学调用一次；触发原任务反思时额外调用 Reflector 和最终 Actor，共三次。010 的互动反馈候选先调用专用 LLM（上限 850 tokens），确认反馈则直接回应、不再教学；否定／不确定才回正常教学。教学输出上限第 2 课 900、其余 1200 tokens，原反思 600、Actor 350；每次超时 20 秒，无隐藏修复调用。八课本地高风险词在模型调用前暂停课程。课末独立复盘不占普通教学轮次，失败不能撤销课程成果。
  - `CBT_REFLECTION_POLICY` 可为 none/per_turn/per_task_step/event_driven，部署默认 none，隔离体验默认 event_driven；新会话冻结策略，不宣称事件策略已被实验证明最优。每轮记录更新与可选反思分开，不以时间、情绪词或长度替代反馈重要性。
  - 课程模型只接收同一节课历史；`PREDECESSORS` 规定可授权来源。仅同一参与者当前版本已完成且本人确认的成果，不接收前课原文或角色语境卡。每次使用重新检查来源、归属和版本；沿用案例需另一次本人操作，只复制本课所需且语义相同的情境字段，保留出处。第 8 课可引用第 1—7 课每课最新的紧凑摘要，逐份复核，拒绝或缺课不阻止完成。
  - 第 3 课的分类只是独立模型假设；本人可以拒绝、不确定或选择无明显模式后完成。反思不能改写本人记录；策略必须符合当前阶段和缺失字段。
  - 第 5、7 课路径由本人显式选择，模型不能代选；重选须撤回旧路径记录、确认、学习证据、课后安排与活动反思，重开示例。动态字段、任务和反思适用性均包括路径，完成后不能重选。
  - 第 4—8 课的替代做法、活动、暴露、睡眠/放松和应对安排都是本人计划，不能宣称已执行或有效；成果标记实际运用尚未测量。不强迫行动或接受积极说法，不生成危险挑战、睡眠限制或药物处方。
  - 课后 Reflexion 独立审计、可重试；教学建议保留为待验证假设，默认不自动用于下一课。
  - 课程状态、消息、课后记录、错误和 Trace 必须加密保存，所有轮次保留幂等与审计。
  - CBT provider 支持 dashscope/deepseek/azure。DeepSeek 从 `DEEPSEEK_API_KEY` 读取服务端密钥，课程模型为 `CBT_COURSE_MODEL`（其默认 deepseek-flash），关闭思考模式，JSON Object + Pydantic 校验；不自动降级到规则模拟。历史消息在 DeepSeek 适配层作为带角色、来源 ID 的 course_history 数据传入，避免模型模仿历史 `{id,text}` 封装输出。
  - `messages/stream` 与原接口保持相同权限和幂等规则，工作线程使用独立 DB Session；仅顶层 reply 的临时文本流出，正式状态在完整校验后提交。none 策略可流式教学，其余策略不提前暴露教学草稿，仅最终 Actor 可流式；判题、Reflector 与课后复盘的内部数据不流出。断开后已开始的工作可完成保存，同键重试回放；不得把流式片段当作持久化成功。
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

已经建立 `specs/`。后续开发优先采用：

- 中文为主。
- Spec Kit 兼容结构。
- 严格的“先规格、后实现”门禁。
- 每个功能先明确需求、用户场景、接口/数据影响、验收条件，再生成 plan 和 tasks。

初版两课和三课规格保留历史。当前以[八课工作流规格](specs/004-eight-lessons/spec.md)为共享基线，第 1 课按[005 实现说明](specs/005-course-learning-design/implementation-lesson-1.md)扩展，互动记忆见 [010](specs/010-event-reflection-memory/spec.md)。Agent `course-guided-v3`、实现 `guided_cbt_v3`；第 1 课 `6.5-interaction-memory`、第 2 课 `5.1-interaction-memory`、第 3 课 `2.1-interaction-memory`、第 4—8 课 `1.1-interaction-memory`。

用户已同意[八课教学练习与检验设计](specs/005-course-learning-design/spec.md)。第 1 课现已实现九阶段、四题统一反馈、可选补练、本人目标及结构化学习结果；检验判读单次调用最多 450 tokens，校验最新回答来源，不叠加课内反思。提示、跳过、目标操作零调用，首次与补练分开保存。完成后独立复盘增加情境假设、其他解释、后续行动与核对办法，最多 1200 tokens；其余课仍为 600 tokens。旧第 1 课只读，数据库表与其他课版本不变。第 2—8 课的新检验尚未实现，原版第 2 课三题复习和作业回顾等仍须逐项对照。三种自我评分及目标数量仍待体验细化；目前近况可跳过、先收一项目标。课内频率与收益仍待实验；学习者检验、Agent 理解测试和工程回归分别报告，反思不自动跨课采用。

架构讨论记录见[课程 Agent 架构规格](specs/002-lesson-3-design/spec.md)，其草案字段不直接视作 API。用户已授权补齐八课，并明确后续再开展专项理解测试。触发策略已接入但优劣待实验，课内和课后反思分开，关注有来源的反馈、新信息、纠正与可比冲突，不预设精神状态稳定。代码与报告见[阅读指南](specs/004-eight-lessons/code-walkthrough.md)，专项测试见[待执行清单](specs/004-eight-lessons/understanding-tests.md)。

真实模型和流式增量见 [006 规格与实现](specs/006-course-streaming/implementation.md)。用户已在被 Git 忽略的本机 `.env` 配置 DeepSeek 密钥，不得读取输出或覆盖。隔离真实模型启动命令为 `scripts/run_course_preview.py --port 8001 --provider deepseek --policy none`；8000 为原离线体验。第 1 课真实完整路径与课后复盘已验证，尚不能外推到所有模型/课程或教学效果。离线回归脚本会清空子进程中的真实密钥，防止误计费。

用户随后要求修改“示范已经讲出答案又问同一句”的问题，6.2 保留小林讲解并换小周菜摊案例引导，见 [007](specs/007-lesson1-guided-example/spec.md)，独立在 8002 运行。当前 6.3 按用户同意的方向新增九阶段重点与有限个人练习，见 [008](specs/008-lesson1-stage-focus/spec.md)：`practice_flow` 保存计数与独立缺失状态；初次回答和一次澄清仍未获得当前项时暂留，或本人选择想不起/先不谈。四项已表达或暂留即可本人核对；缺失不进入 `draft_record`，成果与授权摘要保留范围。个人练习的模型/Actor 草稿不流出，由程序给出下一题与核对摘要；其他阶段沿用既有流式机制。新隔离真实体验在 `http://localhost:8003/`，旧 8001/8002 用户进程和数据保留。第一部分 invalid_evidence 错误尚未全面修复，不能说全部问题解决；本次不放宽来源守卫。

## 10. 对话清空后的恢复流程

最新为[015](specs/015-feedback-and-review/implementation.md)：第一课7.1-feedback-review恢复检验阶段突发反馈处理，新增合法stop_check/pause动作及判题漏检反馈出口，原独立加密记忆复用；case_review.py单次来源化LLM自然回顾，原话不改，案例内容指纹缓存。课末固定LLM/结构化反思继续，未自动跨课采用。014内容蓝图保留；其他课教学Prompt逐字一致。新隔离8014，恢复先检查。以下为历史。

最新为 [014](specs/014-lesson1-blueprint/spec.md)：第一课7.0-blueprint-aligned，恢复同例教学、两项0—10评分、模型/关系回顾、逐题反馈、多项整套课程目标。评分在blueprint状态独立于四要素原话，修改对象后失效；目标草稿/确认与授权来源可追溯。保留拒绝、同例停问、流式和独立Reflexion。第二至八课Prompt须与af0605d逐字一致，不扩展其字段白名单；无新表迁移。014规格/报告为当前恢复入口，以下为历史。

最新 [013](specs/013-stop-probing/implementation.md)：第一课 `6.8-stop-probing`，新状态 `interaction_response_version=interaction-response/2`。风格投诉使用Style Prompt，与个人边界候选分流；response_type/tone/follow_up=stop进入兼容记忆。明确追问投诉保留同一case_id/原字段，未收集项留空转待核对，不能自动本人确认或当能力差；失败保留审计、不设隐私recovery。新版隐藏常驻逐项按钮；`practice_origin`拒绝其他故事填虚构案例。无增量的程序回复保存后前端渐显，不额外调用LLM、不伪称实时生成。176项回归与有限模型检查通过，用户体验待验收；新体验8011，8010旧服务保留，恢复先检查。以下012为此前增量。

最新 [012](specs/012-course-navigation/implementation.md)：第一课 `6.7-course-navigation`，末尾 learning_goal/plan/summary 的普通聊天一次非流式 LLM 导航判断，阶段 Prompt 分开，白名单最多两动作，逐动作本轮消息依据，副本全部校验后采用。含糊完成不作目标或同意；finish 仅本轮开始已在 summary。按钮继续零调用；独立检验与记录确认不受影响。输入立即清空，保留失败原请求及新草稿；虚构暂留文案区分来源。170 项离线回归与有限真实模型验证，用户体验待验收。最终隔离服务 8010，恢复先核对运行状态。下段为此前增量。

最新为 [011](specs/011-personal-boundary/implementation.md)：第 1 课 `6.6-personal-boundary`，共同练习不再被固定回复覆盖。整体拒绝立即停止个人案例，一次自然确认未来范围，未明确同意只本次生效。独立表 `memory_kind/status` 区分风格和询问边界，按类别实时检索、确认引用双来源、删除来源即失效；主动分享不自动撤回。后课创建时就读取有效边界。迁移 `f83a912be504`，162 项离线回归、有限真实模型与浏览器两条第 1 课完成路径，不等于用户验收。最终体验 8008，恢复时检查服务。下段 010 为此前增量。

最新增量见 [010](specs/010-event-reflection-memory/implementation.md)：八课自然互动反馈经候选规则触发一次专用 LLM 判断，独立 `interaction_reflections` 表与消息、轮次状态同事务保存加密结果；不要求选择交流方式。第 1 课 6.5、第 2 课 5.1、第 3 课 2.1、第 4—8 课 1.1，旧版只读；以 `catalog.py` 为准。互动指导每轮按参与者和实时来源检索，局部不满只本课，明确跨课偏好可供后课参考，新反馈覆盖；学习成果授权规则仍不变。`CBT_REFLECTION_POLICY=none` 关闭的是原任务反思，不关闭本次互动事件；普通轮不增加调用。高风险暂停先于事件判断；失败不写记忆、不改学习进度。课末现有异步 LLM 总结纳入本课近期互动反思及来源，新的课末字段和自动采用方式待讨论。6.4 的规则／按钮方案见 [009](specs/009-minimal-feedback-adaptation/spec.md)，只保留显式接口兼容，不当作新版目标。旧 `invalid_evidence` 仍独立待办；不假定旧服务已运行或加载新版。

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
- 用户是 CS 学生，当前重点是 Agent 架构、结构化协议、Prompt、状态与记忆更新、课程数据依赖及工程验证。课程内容由 Agent 整理为配置与案例，不要求用户投入大量精力论证 CBT 的教学或临床价值。
- 用户需要理解并参与讨论各课的具体教学设置。先解释环节作用和方案取舍，再形成教学调整；用户提出的是可讨论建议，不自动当成唯一方案。明确原版内容、当前实现和目标设计的差别，不因用户不熟悉 CBT 而省略说明。
- 先给结果，再说明关键实现和验证情况。
- 每一步实质性操作（设计、修改、验证等）都应说明目的；修改前交代“旧版怎么做、本次改什么、为什么改、预期带来什么”。已有实现应以实际代码为对照，新增能力应明确标为新增。
- 修改完成后提供可用于报告的前后对照，附相关文件位置、验证结果与尚未验证的限制；让用户能追踪每项改动的依据及影响。
- 明确区分“已经实现的行为”“预期收益”和“有证据支持的效果”。不能根据单元测试或离线演示宣称真实模型表现、学习效果或临床效果已经得到验证。
- 对能够从仓库发现的事实先检查文件，不询问用户。
- 产品偏好、SDD 门禁或会显著改变实现的选择，优先使用 Question UI 提问；Question UI 不可用时再用一句简短问题确认。
- 用户要求实现时应完成安全范围内的实现和验证，而不是只给建议。
- 用户要求诊断时先说明原因，不在未授权情况下扩大修改范围。
