# 常规交互、触发与反思的结构化契约

> 历史草案字段，不是当前 API。已实现契约见 [schemas.py](../../cbt_course_llm_freeform/schemas.py)，运行流程见[代码阅读指南](../../docs/course-code-walkthrough.md)。

状态：设计 v0.3，尚未实现；这些字段不能直接提交到当前课程 API。每轮更新记录，是否调用反思由独立策略决定。架构与时序以[主规格](spec.md)为准，模型职责见[Prompt 草案](prompts.md)。

## 1. 对象及写入权

| 对象 | 主要字段 | 写入者与生命周期 |
| --- | --- | --- |
| `LessonSpec` | `lesson_id`、`version`、`goal`、`record_fields`、`phases`、`task_steps`、`allowed_strategies`、`completion_rules`、`dependencies` | 开发者配置，课内固定版本；子任务有稳定 ID、目标与退出条件 |
| `LearningState` | `revision`、`phase`、`draft_record`、`confirmed_record`、`missing_fields`、`authorized_sources` | 程序维护；模型提议原话补丁，`missing_fields` 由程序计算 |
| `TurnAssessment` | `target_relation`、`events`、`evidence_message_ids`、`comparison_context` | 常规模型输出任务反馈候选；程序核对来源，不作为用户能力评分 |
| `TriggerDecision` | `policy_id`、`policy_version`、`triggered`、`reason_codes`、`evidence_refs`、`scope_turn_ids` | 程序根据实验配置执行；每轮记录，模型不能任意更换策略或阈值 |
| `ReflectionRecord` | `reflection_id`、`scope_turn_ids`、`task_step_id`、`evidence_message_ids`、`brief`、`next_strategy`、`open_items` | 仅触发时由模型提出短结论；程序赋 ID、校验并记录应用；不绑定每 turn |
| `ReplyResult` | `reply`、`intent` | Actor 生成下一条可见回复；不能携带状态写入指令 |
| `CourseArtifact` | `artifact_id`、`lesson_id`、`version`、`revision`、`record`、`source_refs`、`confirmation` | 程序冻结本人确认的成果；后课可按相关性和权限引用 |

课程领域候选（例如第 3 课的思维分类）另设 `domain_candidates`，标明 `kind`、白名单类别、依据引用和本人的核对状态。候选属于可纠正假设，不放进本人原话，也不放进关于教学策略的 `ReflectionRecord`。第 3 课需要的字段从[课程材料](lesson-material.md)配置，通用循环不硬编码分类名称。

`TurnAssessment.target_relation` 可选 `answers_target`、`needs_clarification`、`explicit_correction`、`unknown`。事件候选包括明确不理解、纠正记录、新的相关证据、同上下文潜在冲突、反复无进展及任务切换；保留未知，不将这些信号直接压成一个未校准的质量分。

`comparison_context` 保存或引用问题意图、事件 ID、任务 ID、目标字段与讨论时间范围；这些上下文由程序从当前任务确定，模型只能提出事件匹配候选。比较前核对可比性，题型或讨论对象变化不能直接标为状态矛盾。

`TriggerPolicy` 是独立版本化配置，取值候选为 `none`、`per_turn`、`per_task_step`、`event_driven`，具体阈值待实验。时间和轮次可记录为辅助信号，不能直接代表 importance。触发输入及实际使用的上下文对所有实验条件可追踪。

## 2. Reflector 输入

只有触发策略决定调用反思后，程序才组装此输入，包含：

- `lesson_spec`：本课与当前阶段目标、允许字段、策略和完成条件。
- `state_before`：经验证的结构化状态。引用来源在本轮使用前重新核对。
- `previous_reflection`：最近一次有效反思，首轮为 `null`。可补充最多两条仍有依据且相关的近期反思，替代无限拼接。
- `previous_guidance`：上一条 Agent 消息、意图与实际使用的策略；首轮可为欢迎消息。
- `learner_message`：本次回答及真实消息 ID；不能将其固定称为整个 task step。
- `trigger_decision`、`interaction_batch`：为什么触发，以及范围内有来源的多轮问答/任务反馈。子任务跨多轮时覆盖相关交互；不能只看最后一句。
- `recent_messages`：必要的近期本课交互和真实 ID，初始建议最多六条；不足时补取相关的本课证据，跨课只用获准成果。
- `controller_feedback`：当前允许的阶段建议、重要本人操作、先前策略应用记录和可以确定的规则检查结果。不能把字段齐全标成语义正确。

`state_before`、本轮已校验的候选 `state_after` 和修订号均随请求冻结。网络重试不能使用更新后的状态却沿用旧反思。

## 3. 常规输出与 Reflector 输出分开

常规轮次返回 `observations`、`domain_candidates`、`assessment`、`phase_proposal` 和 `draft_reply`，所有实验条件均保留这些能力。Reflector 只返回 `reflection`，不承担必须每轮进行的记录抽取，也不直接改写事实或阶段。

| 字段 | 约束与含义 |
| --- | --- |
| `observations` | 最多四条；字段必须属于当前课/阶段，`value` 为本次回答中的连续原话，`source_message_id` 必须是本轮学习者消息 |
| `domain_candidates` | 最多两个；类型/类别由课程配置限定；每条有 `basis_refs`，只引用本轮输入、已验证的本课记录或获准成果，不从反思推导本人事实 |
| `assessment` | 针对当前任务的反馈候选及证据，包含可比上下文；格式通过不等于语义判断必然正确 |
| `draft_reply` | 常规 `ReplyResult`；未触发时校验后可发送，触发后不能在反思应用前当作最终回复发送 |
| `reflection.update` | `replace`、`no_change`、`insufficient_evidence`；不强迫每轮生成新的批评 |
| `reflection.evidence_message_ids` | 来自触发范围内实际提供的本课证据。对指导方式的观察可引用 Agent 消息；对本人状态的声称必须有学习者依据 |
| `reflection.feedback_kind` | `answered`、`unclear`、`corrected`、`preference`、`none`；是本轮交互描述，不是能力标签 |
| `reflection.previous_strategy_result` | `helped`、`not_helped`、`unknown`；没有明确反馈时使用 `unknown`，不能因推进阶段就判为有效 |
| `reflection.brief` | 最多 160 汉字的可审查短结论；允许空字符串，不保存完整推理过程 |
| `reflection.next_strategy` | `continue_current`、`clarify_missing_field`、`rephrase_plainly`、`ask_concrete_fact`、`acknowledge_correction`、`summarize_for_confirmation`；程序再按阶段筛选 |
| `reflection.focus_field` | 本课允许的目标字段，或 `null`；不能借此任意创建字段 |
| `reflection.open_items` | 最多三个短事项，表明尚未解决什么；不能直接修改 `missing_fields` 或将旧猜测写成事实 |
| `phase_proposal` | `stay` 或 `next`；是提议，程序核对阶段条件后才接受；不包含“完成课程” |

常规提取示例：本次回答 `u8` 为“我只是猜的，不知道她怎么想。”。这里只展示 `observations` 子对象；该回答对当前任务可能已经充分，表达“不确定”本身不等于回答质量差或必须触发反思。

```json
{
  "observations": [
    {
      "field": "awareness_note",
      "value": "我只是猜的，不知道她怎么想。",
      "source_message_id": "u8"
    }
  ]
}
```

下面是策略决定触发后，Reflector 的输出示例；它不确认或授权任何记录，具体触发策略不是由该输出决定的。

```json
{
  "reflection": {
    "update": "replace",
    "evidence_message_ids": ["u8"],
    "feedback_kind": "answered",
    "previous_strategy_result": "unknown",
    "brief": "本人明确保留了不确定性，下一步核对记录时应保留这一表述。",
    "next_strategy": "summarize_for_confirmation",
    "focus_field": "awareness_note",
    "open_items": ["本人尚未核对分类候选与整份记录"]
  }
}
```

程序每轮接受观察后重新计算缺项；是否推进按常规阶段规则处理。缺项补齐不要求一定先做反思，候选核对与整份确认仍待用户完成。Reflector 未被调用时只保存 `TriggerDecision.triggered=false`，不会生成一次虚假的反思事件。

## 4. Controller 与 Actor 的交接

Controller 校验常规补丁及阶段提议，生成候选 `state_after` 并决定是否触发。未触发时也复核旧策略是否仍适用；已触发时校验新反思，再交给最终 Actor。`no_change` 只能来自被调用的 Reflector，`insufficient_evidence` 不新增持久偏好。

Actor 输入包含公共规则、本课/当前阶段配置、候选 `state_after`、程序从有效反思映射出的指导策略、当前回答和必要的近期本课交互。反思原文作为数据，不能自行升级为 system 指令。

Actor 输出只包含自然回复和意图：

```json
{
  "reply": "我们先保留“我只是猜的”这个说法。记录里会分开显示您的经历和可能的思维习惯，您可以修改，也可以保留“不确定”。",
  "intent": "invite_review"
}
```

`intent` 初始白名单：`ask_missing_field`、`explain_example`、`clarify_answer`、`invite_review`、`respond_to_feedback`。Controller 按当前阶段给出子集，不能仅凭 Actor 的意图推进课程。`reply` 建议 30—100 汉字、每轮最多一个问题；长度限制属于输出控制，语义是否符合任务仍需要回归评估。

普通轮次的返回字段均禁止额外属性。未声明的字段、拒答、截断和解析错误进入失败分支，不调用第二个模型修复 JSON 来绕过已约定的调用预算。

## 5. 程序维护的状态与审计

模型不能写 `participant_id`、`turn_id`、`task_step_id`、状态修订号、确认、课间授权、完成状态、触发策略配置和策略应用成功与否。程序记录：

- 输入/输出与各阶段模型元数据、Prompt/契约/课程版本、原状态修订号。
- 原话摘录与领域候选的来源，反思依据和生效范围。
- Controller 接受或拒绝了哪些建议及规则理由。
- 每轮触发决定、比较上下文、采用的信号/阈值与策略版本；区分未触发、调用后无变化和调用失败。
- 哪条有效反思被用于哪条 Actor 回复，回复提交后才记为已应用。
- 未提交的候选状态与反思、失败阶段、同输入重试结果；不得将候选误作已完成的学习进度。

所有敏感内容继续加密保存。在线摘要有界，完整过程在审计中留存，不靠无限变长的 Prompt 保存系统状态。

## 6. 课间引用

`CourseArtifact` 与课内 `LearningState` 分开：前者是本人确认的版本化快照，后者可以包含待核对的草稿与临时问题。跨课时按 `LessonSpec.dependencies` 选择一个相关成果，核对所有者、版本、完成与确认状态，再由本人选择是否引用。

引用记录保存 `source_artifact_id`、`source_revision`、`source_field` 和本课选择依据；不能把前课原话伪装成本课新消息。第 3 课优先读取第 2 课三栏，缺失时提供第 1 课的相关字段；未接受引用时从新例子开始。

指导偏好迁移另行核对适用性，保留来源与有效期；不默认传整段 `ReflectionRecord` 轨迹。具体 JSON Schema 将在协议定稿后由 Pydantic 生成，目前文档仅确定字段含义、枚举及权责。
