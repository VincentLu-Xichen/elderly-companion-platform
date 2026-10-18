# 八课：结构化记录与可配置反馈工作流

最新为[015报告](../specs/015-feedback-and-review/implementation.md)：第一课7.1，检验反馈也经过原事件Reflexion或判题漏检出口，程序采用停止本组题/暂停等动作；案例回顾由有来源的LLM概括，原话保留。每课固定课末Reflexion继续，未自动跨课采用。其他课版本/教学Prompt不变；下文014为内容基线。

最新为 [014 老师蓝图对齐](../specs/014-lesson1-blueprint/spec.md)：第一课 `7.0-blueprint-aligned`，`blueprint.py` 承载同例教学、两项有来源评分、模型与关系回顾、一至五项目标。四题恢复原场景与逐题反馈，记录反馈暴露；延续拒绝、同例停问、独立记忆和自然语言导航。第二至八课完整 Prompt 与 6.8 阶段逐字一致，版本不变；无新增数据库迁移。以下为历史增量。

最新为 [013](../specs/013-stop-probing/implementation.md)：第一课 `6.8-stop-probing`。新增 `interaction-response/2` 状态标记，结构化 type/tone/stop 区分讲法反馈与个人案例拒绝；前者同例停问待核对，失败不进入隐私recovery。新版隐藏逐项按钮，程序回复保存后前端渐显；`practice_origin` 防止其他故事填入当前虚构记录。176项回归与有限模型/页面验证，用户体验待反馈。其他课版本不变，无新数据库迁移；旧记录可选字段默认兼容。以下012为此前增量。

当前最新为 [012](../specs/012-course-navigation/implementation.md)：第一课 `6.7-course-navigation`，新增 `navigation.py` 的阶段专用判读和有限动作校验，目标/课后安排/总结可用自然语言推进；按钮仍可用。虚构暂留文案区分辨认与个人回忆，输入框立即清空并保留重试和新草稿。170 项离线回归及有限真实模型/浏览器验证完成，用户体验待验收。以下 011/010 为此前增量。

最新 [011 个人询问边界](../specs/011-personal-boundary/implementation.md)：第 1 课为 `6.6-personal-boundary`，其余版本不变。`boundaries.py` 管理候选判读、一次确认、范围校验及案例切换；共同练习保留模型回复。独立表增加 `memory_kind/status`，须执行 Alembic 迁移。风格和询问边界分开检索；虚构练习不作为个人经历。下文版本和“无 schema 变化”等为此前增量说明，以本段和迁移为准。

当前增量是[事件 LLM Reflexion 与独立互动记忆](../specs/010-event-reflection-memory/spec.md)：`interaction.py` 负责候选、契约和白名单指导，`interaction_memory.py` 在独立表保存加密结果、按归属和作用域检索；自然反馈不再走选择按钮。一次确认反馈事件只调用专用 LLM 一次，返回即时回应且不消费学习答案；普通轮不新增反思调用。既有 `CBT_REFLECTION_POLICY` 控制任务反思，与本次互动事件分开；选 none 仍处理明确互动事件。原 6.4 的显式控制接口保留兼容测试，当前页面不展示其交流选项。课末总结保留独立 LLM 调用并加入本课最近三条互动反思的来源。

包名保留以兼容现有路由；当前实现是 `course-guided-v3` / `guided_cbt_v3`。第 1 课为 `6.5-interaction-memory`，第 2 课为 `5.1-interaction-memory`，第 3 课为 `2.1-interaction-memory`，第 4—8 课为 `1.1-interaction-memory`。旧版本记录仍可查看、导出和删除，不能继续生成或自动成为新版跨课学习成果来源。互动偏好与学习成果分开，版本兼容依据其独立 `interaction-reflection/1` 协议。

- `design.py`：六个教学阶段、八课必要字段、问题、案例和课后安排；第 5、7 课显式分支及动态字段。
- `learning_check.py`：第 1 课扩展为九阶段，四题首次检验、提示、可选两题补练、本人目标与学习结果；不覆盖首次表现。
- `practice_flow.py`：第 1 课九阶段重点、个人练习初问加一次澄清、本人暂留操作；原话与缺失说明分别保存，程序控制对话收束。
- `schemas.py` / `prompt.py` / `agent.py`：Pydantic 契约、自动嵌入 Schema 的分角色 Prompt、JSON Object 模型调用及解析校验。
- `feedback.py`：四种触发策略、事件理由和建议适用性；反思频率尚待实验。
- `runtime.py`：消息来源和精确摘录校验、阶段控制、本人确认、暂停与完成。
- `memory.py`：同一参与者已确认成果的授权、显式采用与来源复核；只采用语义相同的情境字段，第 8 课可回顾每个前课最新的紧凑成果摘要。
- `reflection.py`：课末一次独立复盘，审计、失败重试、建议不自动应用。
- `preview.py`：明确标注的离线规则体验，走同一校验与持久化路径。
- `deepseek_chat_client.py`：真实 DeepSeek 非思考模式的 JSON 与 SSE 客户端；历史消息以带角色和来源的数据传入，避免模仿 `{id,text}` 为输出格式。
- `reply_stream.py` / `streaming.py`：仅投影顶层回复文字、有界队列和独立数据库会话；完整校验及持久化后返回最终结果。

数据继续使用加密状态与审计；独立互动记忆表及其类别/状态列需要数据库迁移。课程完成、引导练习表现、生活中运用分开表达。关键确认由实际用户操作产生，模型不能自行确认或解锁课程。

从项目目录运行：

```powershell
.venv\Scripts\python.exe scripts\run_regression.py
.venv\Scripts\python.exe scripts\run_course_preview.py
.venv\Scripts\python.exe scripts\trace_course_workflow.py --policy event_driven
```

体验地址 `http://127.0.0.1:8000/`，测试邀请码 `course-preview`。真实百炼/Azure 模型部署沿用原环境变量；尚需用真实模型走课验证自然教学表现。

使用 DeepSeek：本机 `.env` 配置 `CBT_COURSE_PROVIDER=deepseek`、`CBT_COURSE_MODEL=deepseek-flash`、`DEEPSEEK_API_KEY` 后执行 `.venv\Scripts\python.exe -B scripts\run_course_preview.py --port 8001 --provider deepseek --policy none`。第 1 课真实网页完整路径已验证，其他课及反思策略仍待真实模型专项测试。新版页面使用 `messages/stream`，普通教学在 none 策略下流式显示回复；可触发反思的策略只允许最终 Actor 流出，判题与 Reflector 不流出。一次性 JSON 接口保留。

DeepSeek 判题必须显式要求 JSON，第 1 课当时据此升为 `6.1-learning-check`，当前教学修订为 6.3。来源或结构不合法时整轮不推进，无隐藏修复调用；断流后的相同幂等键能恢复已保存结果。前后对照、调用与测试记录见[006 实现说明](../specs/006-course-streaming/implementation.md)。

6.2 将小林示范与小周买菜的引导练习分开，见 [007](../specs/007-lesson1-guided-example/spec.md)。当前 6.3 增加阶段重点与个人练习收束，见 [008](../specs/008-lesson1-stage-focus/spec.md)：每项两次回答仍未获得时暂留，也可由本人选择想不起或先不谈；缺失状态不写入原话。个人练习的模型草稿及最终 Actor 草稿不流出，程序展示当前问题或核对摘要。新体验暂用 `http://localhost:8003/`，保留旧服务数据。第一部分来源校验错误尚待单独修复。

普通轮次一次模型调用；触发课内反思时增加 Reflector 与最终 Actor，共三次。确定性本人操作不调用模型。`CBT_REFLECTION_POLICY` 支持 `none`（部署默认对照）、`per_turn`、`per_task_step`、`event_driven`；新会话冻结策略，隔离体验默认按事件触发。课后复盘仍独立，不能把离线流程通过当成反思效果证据。

第 5、7 课须本人选择路径，重选会撤回本课旧记录、确认和课后安排。计划不代表执行或有效；第 8 课不预设疾病或复发诊断，没有前课也可独立完成。专项理解测试留待下一阶段，当前规则预览不能测量真实理解。

第 1 课检验每次判读最多调用一次模型，450 tokens，不触发课内 Reflector/Actor，不提前反馈；本地提示、跳过和目标操作零调用。课后独立复盘读取检验、本人记录、目标和来源消息，增加可核对的情境假设，上限 1200 tokens。其余课复盘仍为 600 tokens。检验、课后复盘失败分别恢复，不撤销已保存成果。

设计与验收依据：第 1 课见[005 设计](../specs/005-course-learning-design/spec.md)及[实现与体验说明](../specs/005-course-learning-design/implementation-lesson-1.md)，其余课见[004 八课实现规格](../specs/004-eight-lessons/spec.md)。从代码入门：[原基线阅读指南](../specs/004-eight-lessons/code-walkthrough.md)；后续工作：[专项理解测试清单](../specs/004-eight-lessons/understanding-tests.md)。
