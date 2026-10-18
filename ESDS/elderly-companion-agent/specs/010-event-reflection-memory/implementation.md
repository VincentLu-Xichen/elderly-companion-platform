# 实现与验证（2026-10-18）

## 相对旧版改变了什么

| 旧版 | 本次实现 | 预期作用与边界 |
| --- | --- | --- |
| 6.4 整句规则／按钮触发“直接看解释／继续聊” | 八课自然反馈候选触发专用 LLM，判断互动对象、观察与原因假设，并直接回应；新版页面不再展示交流选项 | 无需用户配置；候选检测仍是有限规则，不是全量情绪识别 |
| 规则反馈保存在本课状态，不是新增 LLM Reflexion | 独立 `interaction_reflections` 表加密保存原话来源、观察、假设、其他解释、作用域与两个白名单指导参数 | 能独立审计、持久化和按用户检索；假设不是诊断，效果始终 not_measured |
| 反思可能在教学后再调用 Reflector、Actor | 明确反馈事件只做一次专用模型请求，同时返回即时回应；不提取课程事实、不消费答题或澄清次数 | 保留当前任务，降低该路径调用数；判为非反馈／不确定时回到正常教学，因此候选误触发会多一次调用 |
| 本课局部规则状态过期，后课不读取 | 每轮从数据库按参与者及活来源读取最多三条紧凑指导，采用最新一条；局部仅本会话，明确长期偏好可跨课 | 不每轮重新反思、不传前课对话；新反馈可恢复 standard，删除来源后不再检索 |
| 第 1 课个人练习由程序覆盖 Actor 输出 | 程序回复直接读取同一指导；Actor 被覆盖时不再标记已呈现 | 反思必须影响真实输出；model_context 仅表示注入，不表示语义服从或有效 |
| 课末已有异步 LLM 总结，主要最近 40 条与部分必要来源 | 保留原协议；补入本课最近三条互动反思的来源及其前一条上下文，即便早于最近 40 条 | 避免近期反思来源被窗口丢弃；不是全历史无限总结，课末新协议尚未设计 |

## 运行流程与代码入口

1. [services.py](../../cbt_course_llm_freeform/services.py) 仍先保存用户消息与 pending TurnEvent；每轮调用 [interaction_memory.py](../../cbt_course_llm_freeform/interaction_memory.py) 检索本人适用指导。
2. [runtime.py](../../cbt_course_llm_freeform/runtime.py) 保留高风险暂停、课程只读和确定性操作门禁；自然 chat 在课程答案提取之前进入 [interaction.py](../../cbt_course_llm_freeform/interaction.py) 候选检测。
3. [agent.py](../../cbt_course_llm_freeform/agent.py) 用 `interaction_reflection` 阶段调用当前 provider（本机已验证 DeepSeek），输出上限 850 tokens、继承 20 秒超时；内部判断不流出，无隐藏重试。
4. Pydantic 契约与来源、标签、作用域、回复边界校验后，确认反馈则生成本轮短回应。scope 默认为 lesson；没有明确“以后／每节课”等跨课表述不能升级为 cross_course。失败给中性回应并在加密 Trace 记录失败，不写入记忆。
5. 服务将消息、课程状态与独立记忆同事务提交，以 TurnEvent 唯一约束防重复。来源、参与者和会话键由服务提供，模型不能决定。
6. 后续普通教学通过 `context.interaction_guidance` 读取有限参数；[practice_flow.py](../../cbt_course_llm_freeform/practice_flow.py) 的程序回复也读取它。保留学习记录确认、检验和原话校验。
7. 完成本课后，原 [reflection.py](../../cbt_course_llm_freeform/reflection.py) 自动异步调用 LLM；失败可重试，不撤销已完成课程。新的课末输出字段、长期记忆合并和效果判据留待讨论。

`CBT_REFLECTION_POLICY` 控制原任务反思；本次互动事件独立运行，none 仍判断候选反馈。其他策略可能仍在普通轮触发旧三调用路径，不应把本次交付说成禁用了既有实验策略。

## 数据、版本和部署

- 用户确认同一数据库独立表，不增加向量库或外部服务。载荷 AES-GCM 加密，外键关联参与者、来源会话／消息和轮次。ORM 删除会话一并删除记忆；检索还会实时校验活来源。
- 迁移：[e72f981ad403](../../migrations/versions/e72f981ad403_add_interaction_reflections.py)，接在原 head `c82d1a4f907b` 后；PostgreSQL 启用 RLS、撤销 anon/authenticated 权限。已验证 SQLite 空库及回退再升级，未实测 PostgreSQL 部署。
- 第 1 课 `6.5-interaction-memory`，第 2 课 `5.1-interaction-memory`，第 3 课 `2.1-interaction-memory`，第 4—8 课 `1.1-interaction-memory`。旧课只读，学习成果仍遵循当前版本和授权规则；互动偏好按独立协议兼容。
- 本次未迁移或重启用户既有数据库／服务，未删除旧数据。部署执行 `.venv\Scripts\alembic.exe upgrade head`；本地启动已有 create_all 逻辑会创建缺少的新表。不能假定旧端口已加载新代码。

## 验证证据

- 隔离离线回归：公共 40＋课程 103＝143 项通过，见 [日志](../../test-results/interaction-memory-regression.log)。新增 15 项针对事件、失败、否定／转述、八课任务边界、指导采用、来源、幂等、加密、重启、用户隔离、跨课／局部作用域、更新、回滚及课末上下文。
- 临时 SQLite：空库 `upgrade head`、回退一版本、再升级通过，检查独立表四个外键；未操作真实用户数据库。
- Python compileall、课程 JS 语法与 Markdown 本地链接检查通过，未做新版浏览器端到端体验或语音真机验证。
- 真实 DeepSeek 三个固定合成案例共两批：第一批直接反馈和转述通过，否定表达一例触发 ValueError 校验拒绝；未保存其完整诊断，不能确定具体子原因。未放宽来源／结构校验。第二批三例全部通过，见 [最新输出](../../test-results/interaction-reflection-smoke.json)。这说明存在生成波动，不能只报告最后一批为稳定正确。
- 另一次真实 DeepSeek→课程服务→独立加密表→同键回放→下一课检索的临时数据库检查通过，单次模型调用，见 [集成结果](../../test-results/interaction-memory-integration.json)。共七次真实模型请求，均为虚构输入，没有发送用户既有课程历史。

## 尚未证明与后续讨论

候选规则无法覆盖所有表达；模型可能错误归因或被校验拒绝。当前核对的是实现边界和少量样例，不是用户满意、稳定语义性能或教学有效性。待实际体验验证自然反馈后的指导是否恰当。

课末建议先讨论三类内容：本课观察到的学习表现、互动方式与调整记录、供下一课核对的假设。它们应分别保留来源，区分计划／实际采用／效果；哪些进入长期记忆、冲突如何覆盖、何时撤回尚未定稿。本轮不把课末建议自动写成永久偏好，也不启动频率比较实验。
