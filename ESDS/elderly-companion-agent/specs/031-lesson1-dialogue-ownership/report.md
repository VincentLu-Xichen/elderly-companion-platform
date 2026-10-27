# 031 第一课六项交流要求：修改说明与验证

2026-10-26，R-010。第一课为 **7.9-dialogue-ownership**，第二课维持 **6.2-contrast-reply**。本轮代码实现与离线验证完成，真实模型及用户体验仍为 **Validating**。

用户最终纠正的范围是最早确认的六项行为要求。本轮同时调整主Prompt、交流动作协议、上下文和程序采用逻辑，让这些要求能实际运行。它不是单独一句Prompt的对照实验，不能把未来收益独立归因于Prompt。

## 六项要求分别落在哪里

| 要求 | 旧实现的问题 | 本轮修改 | 已取得的证据 |
| --- | --- | --- | --- |
| 1. 模型决定何时邀请返回 | 缺少明确保存的临时交流状态、返回点与邀请记录 | 同次模型输出可提出invite_return；保存原阶段、案例和邀请，不设置10／20轮门槛 | 可在第2轮邀请，邀请后仍处于交流状态；重复待答邀请被拒绝 |
| 2. 正常语言由LLM主导 | 主教学保留部分模型回复，但导航、检验反馈等仍常被固定文字替代；上下文给出完整下一问 | 主教学、导航及原判题调用组织正常表达；程序执行合法动作，普通教学提供结构化待办 | 模型短／长回复原样保留；导航语言与实际动作分别核对；检验反馈保留模型文字 |
| 3. 篇幅按情境、可零问 | 通用Prompt建议30—80字，容易让解释与关心都套同一长度；缺项提示容易催促 | 去掉统一字数目标，以必要、低负担提问为原则，允许零问；保持原有token及结构长度上限 | Prompt检查、短回应和完整解释保持原文；未改变provider参数 |
| 4. 六种交流情况 | 倾诉、额外思考和恢复学习没有统一的状态表达 | 有来源的本轮意图覆盖概念问题、交流、邀请、拒绝邀请、恢复；与已有learning_request贯通 | 主练习、辨认题、反馈、目标、安排、总结中的交流与返回路径；否定和转述拒绝用例 |
| 5. 简短回应也可完成一轮 | 没有新增字段容易被记作当前缺项未回答；反复求助可能耗完机会 | 分开“是否真正尝试作答”“是否允许教学推进”“如何回复”；非作答不耗次、不自动暂留／推进 | 连续3个概念问题不耗次；原真实JSON第2轮从计1次改为0次；真正失败作答仍保留有限出口 |
| 6. 邀请与同意分开 | 没有独立的邀请／接受状态，难以保证自然返回的授权和位置 | 邀请只保留返回点；恢复核对本人本轮依据及同一阶段／case_id；明确愿意即可恢复，仍然难过也可以 | 情绪好转不能直接恢复；否定／转述／截断否定拒绝；明确继续、回应真实邀请及直接回原题作答可恢复；加密重开和幂等检查 |

六种情况沿用用户认可的表：与课程有关的额外思考先回应；伤心且仍需表达时继续关心；事情说完或明确好转后可邀请；明确愿意学习时恢复；持续交流由模型寻找时机；暂不返回时继续交流并避免反复催促。是否此刻提问由模型结合上下文决定。

## 各修改板块的职责

### 主Prompt与教学上下文

[prompt.py](../../cbt_course_llm_freeform/prompt.py)、[lesson_1.py](../../cbt_course_llm_freeform/lesson_1.py)去掉“每轮补问一个缺失字段”的常规要求，明确先解释概念或回应感受，再判断是否适合继续。错别字／同音字理解放入实际生效的通用规则；用于持久化的摘录仍保留原文。第一课开头的“蓝图”说明改为运行状态／教学知识的职责说明；没有删除必需的状态与教学素材。

[runtime._context](../../cbt_course_llm_freeform/runtime.py)在第一课learn／practice／review不再调用并发送完整的next_question，而使用[blueprint.pending_task](../../cbt_course_llm_freeform/blueprint.py)：待办字段、建议项目、对应的想法或情绪、0—10量尺及question_required=false。模型知道评分对象和未完成目标，但不被一整句下一问牵着走。固定任务材料、按钮与兼容路径仍使用原问题生成器。

“每轮至多一问”改为“必要时聚焦一个具体问题，不连串盘问”，允许完全不问。放宽的是风格建议；没有提高1200等现有输出token预算，也没有取消Schema长度、来源或安全约束。完整第一课主Prompt从12,906增至15,173字符（包含JSON Schema），本轮没有取得实际token／延迟收益证据。

### 本轮交流意图与保存的返回点

[dialogue.py](../../cbt_course_llm_freeform/dialogue.py)集中新增TeachingTurn与classroom_dialogue。模型用turn_intent说明本轮是answer、concept_question、conversation、invite_return、decline_return或resume_course，并提供最新learner消息id与连续原话quote。它利用原模型调用，不增加一个判断Agent。

classroom_dialogue保存mode、原stage／case_id及邀请pending／declined／deferred／accepted。程序校验来源、非法组合、返回位置和明显否定／转述；模型负责上下文中的含义与措辞。模型不确定意图时仍可能失败，本轮的规则及离线用例不能证明覆盖所有自然语言。

恢复也可以由用户主动明确提出，不必先收到邀请。直接回答原练习可表达继续意愿，随后仍经原字段来源与评分守卫。仅“好些了”不等于接受返回。显式暂停／继续等控制沿原权限执行；控制改变进度时清理过期返回点。

[state.py](../../cbt_course_llm_freeform/state.py)为新第一课初始化交流状态；[schemas.py](../../cbt_course_llm_freeform/schemas.py)与[navigation.py](../../cbt_course_llm_freeform/navigation.py)增加可选、有来源的动作字段。[catalog.py](../../cbt_course_llm_freeform/catalog.py)升第一课版本，原会话沿既有版本规则只读；没有自动迁移真实会话或数据库表。

### 回答机会、进度与回复分开处理

[runtime._teach](../../cbt_course_llm_freeform/runtime.py)先核对交流意图，再处理记录和教学状态；普通回复保留decision.reply。attempted_field仅表示用户确实尝试回答的项目，不能因为待办是评分就认定本轮也在回答评分。

[blueprint.after_turn](../../cbt_course_llm_freeform/blueprint.py)分别接受answer_attempt与progress_allowed：概念问题、倾诉、邀请等不耗次、不触发自动暂留或切阶段；真正尝试后仍缺项的回答保留原有有限帮助／暂留出口。记录已完整后的正常学习轮仍能进入review，避免另一种“必须再回答一次才前进”的卡死。

[feedback.decide_trigger](../../cbt_course_llm_freeform/feedback.py)不把非作答累加为连续无进展。原none／per_turn／per_task_step／event_driven策略保留；per_turn原有教学→Reflector→Actor三次调用仍可发生。[agent.py](../../cbt_course_llm_freeform/agent.py)给Actor保留同一待办和交流状态，[prompt.py](../../cbt_course_llm_freeform/prompt.py)也说明策略不要求每轮催评分。

旧捕获JSON没有turn_intent时，兼容原协议：已验证、来自本轮的confusion信号且无摘录，可作为概念问题，并标明origin=legacy_signal；其余旧答案沿兼容作答路径。没有将任意空observations都解释为倾诉，也未改写原JSON。

### 已有学习请求、导航及辨认练习

[learning_request.py](../../cbt_course_llm_freeform/learning_request.py)的倾听／继续使用同一交流状态，原评分暂留与请求范围守卫保留。明确整课暂停时设置真实paused并采用模型回应。此前030两条只检查固定暂停文案的测试改为检查模型文案，真实暂停和原记录断言继续保留。

[runtime._navigate](../../cbt_course_llm_freeform/runtime.py)在目标、课后安排、总结等阶段保留模型回应，由原白名单动作更新真实进度；也能先交流、邀请、拒绝或恢复。模型不能用聊天意图夹带目标写入或课程动作，不能冒称已确认／已完成。缺少可用回复或触及错误事实声明时仍保留原回执／错误处理。

[learning_check.py](../../cbt_course_llm_freeform/learning_check.py)及[agent.evaluate_answer](../../cbt_course_llm_freeform/agent.py)复用原判题调用：内部verdict／reason负责结果，reply负责给人的反馈与帮助；倾诉不是错答或提示，不推进题号。固定下一题材料与首次／帮助后表现记录保留。部分自然语言求助原先直接返回模板、0调用，现在走原判题调用、通常1调用；显式帮助按钮仍0调用，没有新增第二层判读。普通作答仍复用原判题调用。

第二课使用原LegacyCheckAnswerDecision及原判题Prompt；与修改前完整文本逐字相同。第二课专用主Prompt同样未变。截图里的第二课提前返回与未使用映射属于此前已解释的维护问题，本轮未据此删除分支或重写第二课。

[preview.py](../../cbt_course_llm_freeform/preview.py)仅配合离线演示的新上下文／求助输出；[test_natural_dialogue.py](../../cbt_course_llm_freeform/tests/test_natural_dialogue.py)调整旧固定目标文案断言，继续验证实际目标内容。没有通过删除状态断言来放宽数据安全。

## 验证与证据

本机run_id：`20261026-031-dialogue-implementation-135600`。模块目录运行：

```sh
.venv/bin/python -B scripts/run_regression.py
```

- 修改前公共56＋课程221＝277项；修改后公共56＋课程250＝**306项通过**，新增[29项行为／集成测试](../../cbt_course_llm_freeform/tests/test_dialogue_ownership.py)。[最终日志](../../test-results/dialogue-evals/20261026-031-dialogue-implementation-135600/regression-final.log)。测试使用临时数据库并隔离真实密钥。
- 覆盖早于10轮的邀请、拒绝后交流、明确继续但仍难过、否定／转述／来源错误、0分、不同案例不混写、原有有限作答出口、跨后续阶段的交流、原per_turn三调用上下文，以及服务层加密保存→重新加载→同键幂等→本人恢复。
- 当前freeform包60份Python文件语法编译通过；第二课主Prompt及旧判题Prompt／Schema完全一致，前端、Daily Chat、模型参数相关源码等按修改前实际快照核对。见[作用域核对](../../test-results/dialogue-evals/20261026-031-dialogue-implementation-135600/scope-verification.json)。
- 用先前7.8.5女儿未接电话的**原4份模型响应**执行[零API回放](../../test-results/dialogue-evals/20261026-031-dialogue-implementation-135600/original-json-replay.json)，没有编辑JSON或重新生成。第2轮旧程序unanswered包含该消息，新程序为空；第3轮conversation，第4轮course；同一case_id及四项记录保留，调用参数一致。
- 回放仅在合成起点副本中更新lesson_version并加入空交流状态；没有迁移真实旧课。旧第2轮回复仍邀请评分，因此不能宣称新Prompt已生成更合适的回复；trace中的usage为原调用历史值，不是新消费。
- 新增真实模型请求 **0**；本轮没有服务重启、网页／语音验收、真实库写入、.env修改或Git提交。此前观察的4请求／24,071 tokens／8.126秒属于7.8.5，金额未知，不能算作7.9真实结果。

## 已知限制与下一步

实现已为六项行为提供语言和状态支持，真实模型是否稳定选对意图、能否温柔自然地邀请与收束、是否仍过早追分，尚未取得本轮真实证据。待答邀请的重复提交有程序阻挡；拒绝后何时再次邀请主要由模型结合新上下文判断，没有写死冷却轮数，也不能宣称从此绝不催促。

此前观察第3轮原模型只暂留相信程度、第4轮才暂留两项的范围差异仍保留。本轮回放没有改原模型的范围，也没有证明该误读已解决。E04复合确认、其他原有语义和体验问题继续保留，不据本轮测试关闭全部缺陷。

第一课四要素学习、两项评分、关系回顾、辨认练习、目标与自愿课后环节仍在；不是四个字段填完即宣布整课完成。固定开场、教学题目材料、显式控制回执、错误和安全保护继续存在，不能把这轮表述为所有程序文字都已删除。

下一步建议以7.9为明确候选，逐轮人工查看概念求助→倾诉→自然邀请→暂不返回→愿意继续及后半课衔接；真实调用需另有明确预算。当前保留A体系，B／C／D继续后置。

源码基线是修改前的实际脏工作区，不只HEAD。修改前后快照、逐文件差异在该run目录，根产品docs另行本机备份。保存方式见[Git清单与命令](git-save.md)。原始证据及根docs被Git忽略，不能声称已随代码上传。
