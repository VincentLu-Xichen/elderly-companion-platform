# 老人陪伴 Agent：Daily Chat 与对话式 CBT 课程

## 最新：当前A基座baseline数据（027，2026-10-24）

已按用户要求、以模块.env为准，采集原6例8轮：9次模型请求均返回，7轮程序成功、1轮拒绝，既定检查5/6。E03发生考试/室友事实混写与返回来源失败，数据照实保留；257项离线回归通过不代表对话质量通过。共31,201 tokens、完整等待16.447秒，金额由用户按账单补记。本轮不改产品/Prompt或进入新架构。[报告](specs/027-baseline-data/report.md)、[完整原话](specs/027-baseline-data/transcripts.md)、[tokens/费用登记](specs/027-baseline-data/usage-ledger.md)。

## 最新：修复评测API凭据来源（026，2026-10-23）

用户确认评测以后以模块.env为准。已修复旧继承密钥遮蔽文件配置的问题；--provider必须与文件一致，缺配置不回退旧值。257项离线回归通过，实际配置检查0请求且未改.env。023/024/025历史输出照存，但账户来源未核实，不能当作指定新API账户的基线；没有付费重采或切换旧网页服务。[原因及验证](specs/026-eval-api-source/report.md)。

## 最新：单教学Agent基线与架构实验设计（025，2026-10-23）

当前A定义为每课统一教学主Prompt、保留既有辅助调用/程序约束。已用原6例8轮采集一次当前输出：10请求全部返回，32,197 tokens/17.631秒，费用未知；没有改产品代码、Prompt、模型或版本，质量缺口照存。后续先设计B主管协调任务Agent，再C单Agent任务分块，分别同模型对A；之后才是D模型/参数及效率优化。本轮后续方案未实施。[完整实验设计](specs/025-agent-architecture-baseline/experiment-design.md)、[A0真实输出与限制](specs/025-agent-architecture-baseline/report.md)、[合成逐轮全文](specs/025-agent-architecture-baseline/transcripts.md)。没有新网站或Git提交。

## 最新：第二课对照回应保留（024，2026-10-23）

第二课6.2-contrast-reply修复E07模型承接被固定问题覆盖：先呈现本轮解释，再接回看邀请。253项离线回归通过，原JSON新旧回放状态一致；4次真实尝试中3成功、1网络失败，原例重复及1个变体均保留承接。第一课7.5、Prompt和前端不变；没有新体验服务，当前只交付局部结果，等待用户体验。完整原话、失败/成本、运行过程及指定路径Git指导见[024报告](specs/024-lesson2-contrast-reply/report.md)。

## 当前：可复用对话测试与基线（2026-10-23）

新增[评测数据与运行说明](evals/cbt/README.md)、[两组整课人工体验卡](evals/cbt/full-course-cards.md)和[完整Agent推进Prompt](evals/cbt/AGENT_PROMPT.md)。6个固定局部场景已用当前DeepSeek取得真实基线，原始模型JSON、最终回复、状态和代码指纹分别保存；10次请求中一次辅助回顾失败也保留。发现的覆盖/复合确认等问题见[023实际报告](specs/023-reusable-dialogue-evals/report.md)，没有在本轮改课程或架构。

后续每次大调整都用同版输入比较并提示Git检查点；原始输出留现有忽略目录，合成案例和汇报可进Git。本轮不提交、不推送、不重启旧服务。

## 当前：前两课后端职责整理（2026-10-23）

在下方021两课基线上，已将初始状态与复用规则提取到`state.py`，页面/API数据提取到`presentation.py`，`runtime.py`保留轮次调度和兼容入口；第二课进一步拆开复习、自然语言操作、摘录及后续回应。统一活动后端格式、清理12处无用导入，方便后续理解和局部实验。完整旧→新对照与代码阅读顺序见[022报告](specs/022-backend-readability/report.md)。

第一课7.5、第二课6.1及Prompt契约保持不变。246项回归通过，6组38轮离线行为快照与重构前一致；14份前端文件、两份教学模块指纹不变。没有新增模型调用，未重启旧服务或提交推送；本次整理不代表已解决自然承接等体验问题。

## 当前：只保留前两课的可执行后端（2026-10-23）

按用户最新授权，已删除第3—8课内容、专属技能流程/材料，以及共享运行时中的分类、分路和多课回顾分支；活动目录只注册第一、二课。后端代码入口和完整前后对照见[021说明](specs/021-two-lesson-backend/report.md)。相对本轮开始的源码快照，freeform主后端净减少678行。

前两课教学素材、前端、拒绝/停问、流式回复、独立互动记忆和课末Reflexion保留。第一课因共享模型契约缩小升为`7.5-two-lesson-backend`，第二课仍为`6.1-xmind-flow`；旧版只读。历史后六课仅查看/导出及管理员删除，不再调用已删除的教学代码。老师的八课总览和历史规格/报告继续保留，不能据下方旧记录认为后六课仍可启动。

验证：246项离线回归（公共42＋课程204）及前端协议检查通过；14份前端文件指纹不变，第二课完整Prompt指纹不变。未重启旧服务、未运行新的真实模型实验，尚待用户体验。本轮未提交推送。

阅读顺序：`catalog.py/state.py` → `router.py/services.py` → `runtime.py` → 第一课`blueprint.py/teacher_flow.py/learning_check.py/navigation.py`或第二课`lesson2_flow.py` → `agent.py`及互动记忆/课末复盘 → `presentation.py`。路径均在`cbt_course_llm_freeform/`中；使用`scripts/run_regression.py`验证当前范围。

以下均为历史交付：旧版本、旧端口及第3—8课说明保留出处，不代表当前实现或服务已更新。

## 2026-10-23：目标承接修复

第一课`7.4-goal-handoff`：四题反馈中直接提出目标可进入目标讨论，不必先点击继续。独立修复课末时间锁异常。详见[变化、证据与限制](specs/020-goal-handoff/report.md)。新版：http://127.0.0.1:8020/，邀请码`course-preview`。旧8019及用户记录保留；274项回归及4个有限DeepSeek场景通过，待体验。

# 第一课自然回复试用（2026-10-23）

第一课升级为`7.3-natural-dialogue`：普通主诉、四要素和回顾优先保留LLM回复，目标访谈保留自然承接；程序继续维护材料、来源、状态和真实操作回执。明确核对上下文中的“准确”可以直接进入练习；不把“没有补充”当确认。其他课程不改。

体验：http://127.0.0.1:8019/，邀请码`course-preview`。原8018和记录保留，新预览临时数据随进程关闭清除。266项回归通过、6个有限真实模型场景通过（5调用/21,528 tokens）；尚未整课用户验收，未提交推送。已知目标提示可能重复，第二课和跨阶段导航待改项未合并处理。详见[019前后变化与限制](specs/019-lesson1-natural-dialogue/report.md)。以下为历史交付。

## 当前更新：第3—5课先教后练

第三课升级3.0-skill-course，第四、五课2.0-skill-course。相较此前通用六阶段加字段收集，新增各课可见的介绍、方法示范、共同练习、应用和核对步骤：第三课讲四类表达方式再提出可拒绝/不确定的候选；第四课区分行动冲动、实际行为与未来计划，先讲适用判断；第五课激活和暴露两路都提供难度排序教学与记录。三课可换事件，不把课程串成对同一件事的长分析。

自然语言判读、当前项/整段暂留、拒绝个人经历、同例停问、修改重确认和换路均接入新步骤，复用独立互动记忆与固定课末复盘；课末建议仍不自动跨课采用。旧3—5课只读，1/2和6—8教学Prompt、版本不变，无新增数据库表或迁移。

先看[完整设计与实际验证](specs/018-lessons-3-5/report.md)，再看[两组完整实际对话](specs/018-lessons-3-5/cases.md)：合成输入、实际系统/DeepSeek回复、每轮阶段与耗时分别标明。258项离线回归通过；真实专项修后7/7、两组完整案例修后6/6且六次课末复盘完成，首轮失败及费用保留。教学效果与教师/用户验收未完成。

独立体验：http://127.0.0.1:8018/，邀请码course-preview；原8015/8016不关闭。临时预览关闭后数据清除。本轮未提交推送，产品想法文档、原稿和原始测试日志继续Git忽略。以下为历史增量。

## 当前更新：前两课详细流程补齐（7.2 / 6.1）

用户体验纠错（2026-10-21）：多块材料合并到有界滚动区，普通教学默认折叠，保留全部原稿内容与展开状态；聊天列表使用剩余高度独立滚动，输入区不再被历史消息挤走。第一课回顾邀请按案例内容记录已展示，收到无补充的回应后提示核对，不再强制重复原问题，暂停恢复也不重新邀请；“没有了”不等于本人确认。输入区旁新增显式核对/修改入口。241项离线回归、前端脚本通过，实际页面及有限模型检查见017报告。原8015临时会话保留，前端刷新生效；新后端另在8016加载，不能把8015旧进程说成已更新后端。

本轮按两份XMind的展开分支补齐，修正此前以简要大纲代替详细教学的遗漏。第一课先介绍两大模块和老师八课练习总表，再由本人给上周状态打1—10分；第二课同样先评分。周状态分段回应、原话来源和量尺单独保存，不由泛泛描述猜分，也不混作本次事件的情绪强度。

四要素教学增加可展开的定义、考试场景示例、表达帮助和情绪词汇；不知道时先展示对应帮助，再回原事件，不只重复提问。第二课恢复“捕捉我的思维”的名称与自动思维心理教育，保留雨天双人对照、三栏、强度与关系核对。第一课九个参考目标分条展示；原有拒绝、暂停、同例停问、逐题反馈、流式/渐显及两层Reflexion继续。

完成第一、二课后，可在“课程练习”实际填写并回看四要素/三栏日记，个人与虚构来源分开。第二课经明确授权可回顾第一课最近三条记录，未做时最多自然询问一次困难，可拒绝，不将没有记录判为未完成。复用现有加密作业表；保存具备同意、归属、CSRF、版本、幂等与审计约束，无新表或迁移。

逐环节旧→新对照、原稿中延续此前决定的调整、失败案例与验证边界集中于[017交付报告](specs/017-xmind-flow/report.md)。第3—8课教学实现不改，旧版1/2课只读；课末建议仍未自动跨课采用。本轮未提交或推送。以下是历史增量说明。

本轮离线回归240项通过，另完成语法、三个前端脚本和空库迁移检查。真实DeepSeek专项首轮3/4通过，修正“未做事实/未做原因”混淆后两轮均4/4；三轮共15调用、43,817 tokens，35.093秒。少量模型样本和工程通过不等于教师验收或教学效果。

## 当前更新：第二课6.0对齐老师定稿

相较 `harrison/0cc68ed` 的通用第二课，新增作业回顾、三题逐题复习与原答汇总、雨天先表达后双人教学对照、独立个人三栏及可选0—10情绪强度、关系回顾与本人确认。雨天想象、预设小雨和当前个人/虚构案例分开保存，不把示范或复制旧答案当成训练结果。整体拒绝、同例停问、停止剩余复习题及课末固定LLM Reflexion接入第二课；作业回顾为教学调整提供证据，不计服从分。

实现变化、逐项蓝图对照、模拟案例的**理论预期**及**实际验证证据**集中在[第二课汇报文档](specs/016-lesson2-blueprint/report.md)。规格见[016](specs/016-lesson2-blueprint/spec.md)。新版隔离体验：`http://127.0.0.1:8015/cbt-course`，邀请码 `course-preview`；关闭隔离服务后临时数据清除。

工程回归228项通过，JS草稿/渐显/流协议及临时空库迁移检查通过。有限真实模型已走通完整正常路径与课末复盘，并发现、修复多栏漏收、重复摘录及局部停问误升级暂停的问题；修复后的专项四例通过。各轮失败、调用成本和验证范围在报告中分别保留，不将少量检查说成稳定理解或教学效果证据。

第一课与第三至八课版本/完整教学Prompt不变；无新表迁移。旧第二课只读。下方第一课7.1为此前已上传版本的历史说明；本轮第二课尚未提交或推送。

## 本轮更新：第一课7.1反馈恢复与自然回顾

相较上次上传到`harrison`的第一课6.8，本次合并了老师蓝图对齐（7.0）及体验问题修复（7.1）：

| 部分 | 本次变化 |
| --- | --- |
| 教学路径 | 从一件困扰展开同例教学，补充想法相信程度和情绪强度0—10、动态模型及关系回顾；已表达的内容不重复索取 |
| 练习与目标 | 恢复老师原社交场景与逐题反馈；支持一至五项整套课程目标、按编号修改和重新确认；保留评分、目标、作业的自愿出口 |
| 语义与呈现 | 明显错字按上下文理解，原话记录保留；LLM生成简短案例回顾，结构化原话与评分仍用于侧栏核对，虚构缺失评分不冒充用户留空 |
| 反馈与反思 | 检验阶段也能处理题量拒绝：突发反馈经LLM判读后采用合法调整；每课结束固定LLM Reflexion继续，观察、假设和建议保留来源及核对方式 |

本轮验证：210项离线回归通过；十组合成DeepSeek专项检查通过；网页走通过错字回答、拒绝剩余题、结束及课末反思。详细调用数、tokens、耗时、失败及修复见下方报告。工程与有限模型验证不代替用户、教师或教学效果验收。第二至八课版本和完整教学Prompt保持一致，无新增数据库表或迁移，旧第一课会话只读。

在老师蓝图对齐版7.0基础上，恢复检验阶段对题量拒绝的动态调整：候选触发原LLM Reflexion，判题模型也可报告漏检反馈；停止剩余题时保留已答，未答不计错。案例回顾改为有来源的LLM连贯概括，明显错字按语义理解、原话记录保留；虚构材料未提供评分不再显示为用户留空。每课结束固定LLM Reflexion与结构化假设/建议继续保留。

体验：`http://127.0.0.1:8014/cbt-course`，邀请码`course-preview`，临时数据与正式库隔离。详细前后对照、结构化设计和验证边界见[015实现报告](specs/015-feedback-and-review/implementation.md)。旧7.0以下内容作为历史；第二至八课未重写。

待改事项（本轮未实施）：共享安全机制仍按风险词直接暂停，尚缺少假设、转述、否定等语境判读及受限澄清恢复通道。用户已明确暂缓此项；后续须保留真实紧迫风险的保护路径，不简单放宽关键词。老师原始XMind、提取图片、本机密钥、测试记录和被忽略的产品想法文件夹不上传。

工作区产品管理：[产品与现状](../../docs/PRODUCT.md) · [想法收集](../../docs/IDEAS.md) · [当前目标与债务](../../docs/ROADMAP.md) · [设计决策](../../docs/DECISIONS.md)。新想法先记录，明确要求实施后再开发；下文和 `specs/` 保留模块技术与历史实现说明。

树莓派本轮情绪上下文的接口、兼容性与验证说明：[voice-emotion.md](docs/voice-emotion.md)。

这是一个用于课堂研究与角色扮演实验的 FastAPI 对话平台，包含两个相互独立的产品入口：

- **Daily Chat**：学生扮演老人，与简短、自然的日常陪聊 Agent 对话。
- **CBT 课程**：学生以学习者本人身份完成八课纯文字认知行为练习课程。

> 本项目用于系统测试、课程学习和课堂研究，不提供正式心理治疗、医疗诊断或紧急救援服务。

## 第一课 7.0：按老师蓝图恢复课程内容

在 6.8 交互版本上，第一课现按老师提供的 XMind 补回教学内容，详细对照见 [014 规格](specs/014-lesson1-blueprint/spec.md)。正常路径为：先选择一件困扰，在同一事件中学习情境、想法、情绪和行为，再回看模型、练习辨认、制定整套课程目标。

- 新增想法相信程度、情绪强度两项 0—10 评分，保留原话和对象来源。零分不等于未提供，改变想法或情绪后对应旧评分失效，也可以暂不评分。
- 右侧展示认知行为模型、概念示例、情绪词汇表及文字说明，邀请本人表达新的看法，不替本人断言因果循环。
- 四题恢复老师的社交场景，逐题反馈、最后汇总。原文“拼命想和人说话”最小改为明确实际动作的“不断找话题，和对方说话”；后续题注明此前已接受反馈，不称完全独立测量。
- 目标扩展为整套课程一至五项具体目标，支持改善方向、草稿、修改与本人确认。修改已确认目标会撤销确认并重新核对课后安排；仅确认目标可随授权摘要供后课参考，评分不跨课传播。
- 保留个人询问边界、同例停问、独立互动记忆、Reflexion、自然语言导航、即时清空输入和流式/渐显。课后日记可拒绝，虚构练习不冒充个人经历。

只升第一课为 `7.0-blueprint-aligned`，旧会话只读；第二至八课版本和完整 Prompt 保持原样。扩展数据使用现有加密状态，无新增表或迁移。验证及边界见 [014 实现报告](specs/014-lesson1-blueprint/implementation.md)。以下保留原始 main 与 6.8 阶段对照，冲突时以本节及最新规格为准。

## harrison 相比原始 main 的修改

对照基线为本次开发开始时下载的 `main`（`c87dd5f`），本节记录到 6.8 的交互改造；最新 7.0 内容对齐见上节。后续 main 如有更新，请按提交号比较，运行与部署说明继续保留。

原版已经有登录、记录同意、加密保存、审计、管理员后台及第 1、2 课的自由对话入口。本轮在这些能力上改进课程流程，重点是让第一课有明确的教学步骤，同时理解并尊重用户反馈。

### 主要变化

| 方面 | 原始 main | harrison 当前实现与作用 |
| --- | --- | --- |
| 课程推进 | 模型依据 Prompt 自由带领；程序解析回复中的附件与完成标记 | 引入明确阶段和合法动作，分开模型建议、程序校验与用户确认，减少模型自行宣布完成 |
| 第一课教学 | 主要由 Prompt 安排讲解和练习，没有当前独立的四题检验和结构化学习结果 | 九阶段串联示范、共同练习、核对、新例检验、反馈补练、目标与总结；练习和独立检验分别记录 |
| 用户不愿回答 | 没有专用的拒绝范围判读、一次确认与独立边界记忆，主要依赖教学模型回应 | 识别单项拒绝、整体拒绝、否定和转述；尊重当前拒绝，必要时用独立虚构案例继续 |
| 用户反感追问 | 没有独立的反馈判读与同例停问流程 | 区分拒绝个人经历与反感追问方式；后者停止补问，保留原事件与已有内容，礼貌回顾、等待核对 |
| 结构化输出 | 课程模型返回自由文本，通过文字标记控制附件与完成 | JSON Object + Pydantic 契约携带回复、摘录、来源及动作建议；服务端校验字段、证据与阶段 |
| Reflexion 与记忆 | 没有当前的事件反思、独立互动记忆与课末复盘机制 | 分开处理互动反馈、可配置课内反思和独立课末总结；同库独立加密表保存有来源、有范围的互动记忆 |
| 模型与回复显示 | 原有百炼/Azure 客户端，没有本轮 DeepSeek 适配和课程 SSE 路径 | 新增 DeepSeek、SSE 回复及程序回复保存后渐显；渐显本身不额外调用模型 |
| 前端操作 | 没有当前的阶段导航、记录核对和末段自然语言导航 | 显示当前任务与学习记录；目标、课后安排、总结支持有限自然语言推进；发送立即清空输入，保留失败重试 |
| 后续课程 | 目录列出八课，实际只开放第 1、2 课 | 补齐第 3—8 课基础流程、字段、路径和授权摘要引用；第一课仍是本轮重点细化对象 |

### 用户不想回答时，如何继续课程

**场景一：用户说“我不想说自己的事情”。**

1. 程序规则发现拒绝候选，由 LLM 结合当前问题与近期上下文判断含义；关键词本身不代表心理判断。
2. 明确整体拒绝时，立即停止当前个人案例，不继续逐项索取，也不把拒绝记为答错。
3. 自然确认一次：“以后课程也用虚构例子、不主动问您的个人经历，可以吗？”确认不是继续课程的必答门槛。
4. 明确同意后保存跨课边界；仅这次不谈、含糊回答或转移话题不推断长期同意。已明确说“以后都不要问”则直接采用，不重复确认。
5. 使用独立虚构案例继续，清空当前活动案例的收集进度并保留历史，虚构答案不保存为个人经历。单项拒绝只影响该项；明确要求停止课程则暂停。

**场景二：用户说“为什么一直追问，我三个要素都说了”。**

用户困扰的是追问方式，不代表不愿谈整件事。新版停止索取缺项，礼貌承认追问造成负担，围绕原事件回顾已有内容，等待用户核对；不会因此换成新故事或写入长期个人询问禁令。缺项保持未观察，不解释为判断能力差。

实现分工：[`boundaries.py`](cbt_course_llm_freeform/boundaries.py) 管理询问边界与案例来源，[`interaction.py`](cbt_course_llm_freeform/interaction.py) 定义反馈判读和表达调整，[`practice_flow.py`](cbt_course_llm_freeform/practice_flow.py) 收束练习，[`runtime.py`](cbt_course_llm_freeform/runtime.py) 校验并采用动作。

### 结构化输出、Reflexion 和记忆的关系

- **结构化输出**将模型建议变成可校验数据，不是执行权限。摘录必须有消息来源，模型不能代替用户确认记录或完成课程。
- **互动 Reflexion**从自然反馈中记录观察、原因假设、其他解释和本次调整。`response_type`、`follow_up`、`tone` 分别表达回应方式、是否继续追问与语气，不等于修改 API 的 temperature。确认反馈后直接回应，不必再叠加普通教学调用。
- **独立记忆**使用现有数据库的 `interaction_reflections` 加密表，按类别区分风格反馈与个人询问边界。仅明确表达或确认的长期边界供后课采用，新的篇幅反馈不会覆盖它；用户可明确修改或撤回，来源删除后相关记忆失效。
- **课内任务反思**由 `CBT_REFLECTION_POLICY` 独立控制，支持 none/per_turn/per_task_step/event_driven；选择 none 不关闭互动反馈判读或课末总结。候选判断不是每轮新增一次反思调用。
- **课末 Reflexion**独立调用 LLM，总结本课记录、检验与近期反馈，失败可重试。原因解释仍为待验证假设，默认不自动成为下一课教学决策。

相关代码：[`schemas.py`](cbt_course_llm_freeform/schemas.py)、[`interaction_memory.py`](cbt_course_llm_freeform/interaction_memory.py)、[`reflection.py`](cbt_course_llm_freeform/reflection.py)。

### 第一课当前流程与验证边界

```text
近况与回顾（可跳过） → 短示范与引导例子 → 共同练习
→ 本人核对记录 → 新例子四题检验 → 反馈与可选补练
→ 练习目标（可跳过） → 课后安排（可拒绝） → 回顾与显式结束
```

共同练习可以使用个人经历或虚构案例，检验使用新材料，不把示范中给过的答案作为独立掌握证据。目标—课后安排—总结这段可以说“目标先不设，也不安排课后练习，直接总结吧”；单说“完成了”需结合当前问题澄清，不直接填成学习目标，也不能任意跳过必要确认。

已完成 176 项离线回归（公共 40、课程 136）、前端草稿/渐显/流式协议检查、少量真实 DeepSeek 案例与第一课网页完整路径。用户已对第一课当前设计给予阶段性认可；这不代表所有模型语义、课末归因或教学效果都已验证。第 2—8 课的新差异化检验、完整理解测试与反思收益比较仍待开展。

已有数据库须执行 `.venv\Scripts\alembic.exe upgrade head`，应用独立记忆表及边界字段迁移。旧课程版本保持只读。本机 `.env`、数据库和测试产物不上传；产品想法目录 `../../docs/` 按要求保留本机并忽略，源码与技术规格随分支保存。

按主题查看详细对照：[八课基础流程](specs/004-eight-lessons/code-walkthrough.md) · [第一课教学检验](specs/005-course-learning-design/implementation-lesson-1.md) · [DeepSeek 与流式](specs/006-course-streaming/implementation.md) · [事件反思与记忆](specs/010-event-reflection-memory/implementation.md) · [拒绝与询问边界](specs/011-personal-boundary/implementation.md) · [自然语言推进与输入框](specs/012-course-navigation/implementation.md) · [同例停问与礼貌回应](specs/013-stop-probing/implementation.md)。

## 历史增量记录

以下保留各次交付时的版本、验证和临时端口，供追溯使用；当前状态以上面对照和 `catalog.py` 为准，临时端口不保证仍在线。

最新：[6.8 同例停问与渐进显示](specs/013-stop-probing/implementation.md)。抱怨追问方式时保留当前事件和原记录，缺项留空、礼貌回顾并待本人核对；不因此写入个人询问禁令或换案例。新版隐藏常驻逐项按钮，程序回复保存后渐进显示，真实 LLM 增量路径保留。176 项离线回归、JS 及有限模型检查通过，用户体验待验收。隔离新版体验 `http://127.0.0.1:8011/`，邀请码 `course-preview`；8010旧进程和数据保留。以下6.7为此前增量。

最新：[6.7 衔接与自然语言推进](specs/012-course-navigation/implementation.md)。第一课目标、课后安排、总结支持一次 LLM 意图判断，明确两项选择可进入总结，含糊“完成了”先澄清；程序仍校验来源、顺序和确认边界。发送时立即清空输入，失败保留同键重试，新草稿不被按钮或重试清除。虚构练习用辨认/跳过文案。170 项离线检查和有限真实模型验证完成，用户体验待验收。隔离新版体验为 `http://127.0.0.1:8010/`，邀请码 `course-preview`，临时数据不作正式留存。以下 6.6 为此前增量。

最新切片：[个人询问边界实现报告](specs/011-personal-boundary/implementation.md)。第 1 课升级为 `6.6-personal-boundary`，旧会话只读；整体拒绝后停止个人案例，自然确认一次后续边界，再用独立虚构案例继续。确认边界按类别检索，后课沿用；本次拒绝不推断长期偏好。共同练习保留模型回复，页面、成果和课末总结区分虚构与个人来源，独立检验题目不变。

已有数据库须运行 `.venv\Scripts\alembic.exe upgrade head`，自动建表不能替代已有表增列。本次 162 项离线回归、有限真实 DeepSeek 与 Edge 两条第 1 课完成路径已验证；用户体验待验收。最终代码隔离体验：`http://127.0.0.1:8008/`，邀请码 `course-preview`；服务关闭后临时数据清除。以下 010 为历史增量，不假定旧进程已加载新版。

当前新增[自然反馈事件反思与独立记忆](specs/010-event-reflection-memory/spec.md)：八课均支持候选反馈触发一次专用 LLM 判断，确认针对 Agent 时直接回应并保存加密记忆，不要求选择交流方式。第 1 课 6.5、第 2 课 5.1、第 3 课 2.1、第 4—8 课 1.1；旧版只读。局部反馈仅本课，明确跨课偏好才供后课参考；每轮检索不调用 LLM。课末仍自动异步 LLM 复盘，并纳入近期本课互动反思；新的课末协议待讨论。独立表使用现有数据库，部署前执行 `.venv\Scripts\alembic.exe upgrade head`。已有本机启动逻辑会创建缺少的表，但不能替代部署迁移。实现和验证边界见[报告](specs/010-event-reflection-memory/implementation.md)，不假定旧体验服务已加载新代码。

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| Daily Chat | 可用 | 使用最近 12 条对话生成简短陪聊回复。 |
| CBT 第 1 课 | 可用（结构化教学试用） | 九阶段、四题检验与可选补练、学习结果和课后反思；支持真实 LLM 与流式回复。 |
| CBT 第 2 课 | 可用（结构化教学试用） | 三栏记录，可显式承接第 1 课已确认成果。 |
| CBT 第 3 课 | 可用（结构化教学试用） | 核对推断依据与思维习惯；本人可以拒绝分类或保留不确定。 |
| CBT 第 4 课 | 可用（结构化教学试用） | 检查做法的帮助与代价，考虑尊重边界的替代回应。 |
| CBT 第 5 课 | 可用（结构化教学试用） | 本人选择行为激活/行为暴露路径，整理小步计划。 |
| CBT 第 6 课 | 可用（结构化教学试用） | 检查支持与不同信息，保留本人更平衡的新说法。 |
| CBT 第 7 课 | 可用（结构化教学试用） | 本人选择睡眠/放松路径，整理舒适且可调整的小步骤。 |
| CBT 第 8 课 | 可用（结构化教学试用） | 可授权回顾多个前课成果，形成再遇困难时的应对与支持计划。 |
| 历史 CBT 角色会话 | 只读 | 仅支持查看、导出和删除，不能继续发送消息。 |
| 管理员后台 | 可用 | 支持筛选、查看、导出和删除实验记录。 |

## 产品流程

### 学生端

1. 使用独立匿名邀请码登录。
2. 确认实验数据记录告知。
3. 选择 Daily Chat 或 CBT 课程。
4. Daily Chat 会话可结束、再次查看或删除。
5. CBT 课程自动保存进度；本人确认记录、选择课后安排并显式完成后，记录转为只读。

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

FastAPI 默认加载 `cbt_course_llm_freeform`，八课共享 `course-guided-v3` 工作流。第 1 课为 `7.0-blueprint-aligned`，第 2 课为 `5.1-interaction-memory`，第 3 课为 `2.1-interaction-memory`，第 4—8 课为 `1.1-interaction-memory`。第 1 课已接入[教学练习与检验设计](specs/005-course-learning-design/spec.md)，并按 010—013 补充互动记忆、询问边界、自然语言推进与同例停问；第 2—8 课仍按 [004 八课工作流](specs/004-eight-lessons/spec.md)，并支持互动记忆及有效询问边界。[代码阅读和前后对照](specs/004-eight-lessons/code-walkthrough.md)与[后续专项理解测试](specs/004-eight-lessons/understanding-tests.md)分别记录历史基线与待验证问题。

```text
学习者本轮输入
    -> 服务端保存用户消息和 pending 审计事件
    -> FreeformCourseAgent 接收本课最近 24 条消息、当前阶段与必要记录
    -> 一次模型调用返回 JSON 回复草稿、原话摘录、反馈信号和阶段建议
    -> 服务端校验来源和合法阶段，按会话冻结的策略评估是否反思
    -> 若触发：Reflector 形成短建议，程序校验后由 Actor 生成最终回复
    -> 保存加密状态、最终回复与各次调用审计
    -> 第 1 课在确认记录后进行四题检验、可选补练与目标确认
    -> 本人选择课后安排，再显式完成
    -> 单独生成一次课后教学复盘；失败可重试
```

职责边界：

- `FreeformCourseAgent` 负责自然解释与反馈；模型不能确认记录、完成课程或授予跨课权限。
- `FreeformCourseRuntime` 管理阶段和本人操作，第 1 课九阶段、其余六阶段；摘录必须来自本轮学习者消息，保留消息 ID 供追溯。
- 近况评分可跳过，课后练习可拒绝。支持暂停与恢复，安全暂停不会被普通恢复绕过。
- 第 2—7 课按配置选择相关前课摘要，第 8 课可回顾第 1—7 课每课最新的紧凑成果。仅同一参与者当前版本已完成且本人确认的成果；每次使用复核各来源。授权与实际沿用分开，采用只复制本课需要且语义相同的情境字段，不把计划变成已执行行为；不读取前课原文或角色语境卡。
- 第 5、7 课须本人显式选择路径；重选会撤回本课旧路径记录、确认和安排，从新路径示例开始。第 8 课没有前课或拒绝回顾也可独立完成。
- 学习记录保存在加密状态中；互动 Reflexion 与询问边界另存同库独立加密表，需要 Alembic 迁移。历史版本保留为只读。
- 原有确定性 `cbt_course` 保留在仓库中，但当前 FastAPI 不加载它的路由。

第 1 课在原六阶段的本人核对之后增加新案例四题检验、回看与可选两题补练、本人练习目标。每题提供反馈，四题结束后汇总；此前反馈、提示与补练分别保留；目标可确认或跳过。其余七课仍使用近况、示例、个人练习、核对、课后安排、回顾六阶段。界面进度不代表掌握程度，实际运用仍为 `application_status=not_measured`；八课均在模型前处理本地高风险信号。

普通教学未触发时一次调用，触发课内反思时共三次，本人按钮操作不调用模型。教学输出上限第 2 课 900、其余 1200 tokens，Reflector 600、Actor 350，每次超时 20 秒。`CBT_REFLECTION_POLICY` 支持 `none`、`per_turn`、`per_task_step`、`event_driven`；部署默认 none 对照，隔离体验默认事件规则。策略在新会话冻结，理由进入审计；不以时间、情绪或长度直接衡量 importance。真实理解、触发频率与反思收益留待专项实验。

第 1 课检验回答由独立判读调用返回 verdict/reason/source_message_id（上限 450 tokens）；原始回答由程序保存，判读失败不推进。概念提示、跳过和目标确认为零调用；检验不叠加课内 Reflector/Actor，每题判读后提供反馈。完成本课后独立 Reflexion 增加结构化学习结果、本人记录及目标输入，输出带来源的情境假设、其他解释、下一步和核对办法（上限 1200 tokens，其余课 600）。具有独立 `TurnEvent`，失败可重试，默认不自动应用于后课，不修改本人事实。`POST /api/cbt-course/conversations/{id}/reflection` 可重试复盘；重要操作提交最新 `expected_revision`，失败重试使用原幂等键与原输入。

无需真实密钥的隔离体验（Windows PowerShell，项目目录中执行）：

```powershell
.venv\Scripts\python.exe scripts\run_course_preview.py
```

访问 `http://127.0.0.1:8000/`，测试邀请码 `course-preview`。这是明确标注的离线规则演示，展示真实状态、确认、跨课授权和复盘流程，不代表真实模型理解能力；可用“填入一条体验示例”体验。数据库放在独立临时目录，关闭服务后清除，真实配置不被改写。正常部署继续使用原有百炼/Azure 配置。

在独立临时数据库执行全部离线回归：`.venv\Scripts\python.exe scripts\run_regression.py`。

真实 DeepSeek 体验：在本机 `.env` 设置 `CBT_COURSE_PROVIDER=deepseek`、`CBT_COURSE_MODEL=deepseek-flash`、`DEEPSEEK_API_KEY`，再执行：

```powershell
.venv\Scripts\python.exe -B scripts\run_course_preview.py --port 8001 --provider deepseek --policy none
```

访问 `http://localhost:8001/`，邀请码仍为 `course-preview`。使用隔离临时数据库，密钥仅在服务端读取；页面标明 DeepSeek，真实模式不提供检验示例答案。普通模型回复通过新 `POST .../messages/stream` SSE 接口分段显示，原 JSON 接口保留；完整结构与来源校验后才提交学习记录。生成中内容可能由服务端最终回复替换，断流时同键重试恢复已保存结果，不自动换成规则模拟。检验判读与反思过程不展示为流式教学内容。详见[实现对照与验证](specs/006-course-streaming/implementation.md)。

第 1 课 6.2 将示范与引导案例分开，见[007 前后对照](specs/007-lesson1-guided-example/spec.md)。当前 6.3 增加九阶段重点、个人练习有限澄清、字段暂留和真实缺失范围，见[008](specs/008-lesson1-stage-focus/spec.md)。新版隔离体验使用 `--port 8003`（访问 `http://localhost:8003/`），既有 8001、8002 进程和用户数据保留。个人练习由程序展示有边界的提问，模型草稿不流出；其他支持流式的环节保持原机制。来源校验失败问题仍单独待办。

前端流式协议验证：`node scripts/test_course_stream_ui.cjs`。真实联通检查：`.venv\Scripts\python.exe -B scripts\check_deepseek_course.py`（会发起两次计费模型请求，仅用虚构输入）。

逐轮查看八课状态与调用：`.venv\Scripts\python.exe scripts\trace_course_workflow.py --policy event_driven`。输出 `test-results/course-workflow-event_driven.json`；可替换反思策略，或加 `--activity-path exposure --wellbeing-path relaxation` 检查另两条路径。固定虚构案例用于流程与审计验证，不是理解或策略效果实验。

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
  design.py                 八课/分支材料配置、动态字段与任务标识
  schemas.py                模型与 API 的结构化契约
  runtime.py                候选状态校验、本人操作与完成门禁
  feedback.py               可配置触发与反思建议适用性
  agent.py / prompt.py      教学、Reflector、Actor 的独立调用和 Prompt
  memory.py                 成果摘要、授权、采用与来源复核
  reflection.py             独立课后教学复盘
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
| `CBT_COURSE_AGENT_VERSION` | 保留给旧确定性实现；当前课程版本由 services.py 的 AGENT_VERSION 冻结。 |
| `CBT_REFLECTION_POLICY` | 新课程会话的课内反思策略，默认 none。 |
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
- 成功、失败和超时均保留审计，各次模型调用与采用的短反思存入加密 Trace；本地高风险信号在模型前暂停课程，不据此声称覆盖所有风险语义。
- 同一会话使用幂等键和数据库串行处理，避免重复消息和并发模型调用。
- 应用日志只记录匿名 participant ID、conversation ID、request ID 和状态，不记录聊天正文。
- 不同邀请码不能读取彼此的会话。
- 管理员删除行为会写入审计日志。

当前课程使用 JSON Object、Pydantic 与阶段/来源校验，并非提供方原生 strict JSON Schema 输出。完成由本人操作和服务端门禁决定，历史完成标记不再用于完成当前课程。

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
- 八课及第 5、7 课全部路径的确认、完成和课后复盘，路径重选、越界字段、来源撤回与旧版只读。
- 课程状态刷新恢复、幂等、失败审计和完成后只读。
- 本课有界历史、授权成果摘要、多课回顾及角色语境隔离。
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
- 八课工程流程已开放；真实模型专项理解测试与反思效果实验尚未执行，需后续据结果迭代。
- 已有授权的课程成果摘要复用；尚无通用长期跨 session Memory。
- 网页应用本身不直接采集或播放音频；树莓派通过独立 `voice-gateway` 提供百炼 ASR/TTS，并只接入 Daily Chat。
- 历史 Prompt-only CBT 会话仅保留兼容读取能力。
