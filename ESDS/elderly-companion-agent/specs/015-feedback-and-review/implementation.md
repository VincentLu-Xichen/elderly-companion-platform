# 第一课7.1：反馈恢复与自然回顾

2026-10-18。基线是014的未提交7.0工作区；本轮在原修改上继续，不自动提交或上传。

## 与此前相比

| 用户问题 | 此前实际路径 | 本次处理与价值 |
| --- | --- | --- |
| “白跑了一堂”等明显错字 | 共同练习虽有LLM，但没有明确区分语义理解和原话摘录的约束 | 教学/判题/回顾分别约束：按上下文理解明显错字，摘录仍逐字；回顾可自然表达明确原意。否定或真实不同意思不能擅自当错字纠正 |
| 回顾逐字段念原话、虚构评分“本次留空” | blueprint.review_text由程序列六项，无评分也显示留空 | 新case_review.py单次LLM生成一至两句案例回顾，带来源ID和内容指纹；原始记录留在侧栏，聊天不念表格。虚构模型不再显示材料未提供的评分；失败保留核对出口，不编造摘要 |
| 题量拒绝仍出概念提示 | 反馈候选未覆盖题量，专门判题无反馈出口；现有style参数没有停止本组题动作 | 候选→原专用Reflexion；漏检→判题模型同次输出interaction。程序采用stop_check/pause/continue，停止剩余题、保留已答、未答记未观察，投诉不计错答或提示。只嫌篇幅不跳题 |
| 否定/转述可能被当本题答案 | 判题缺少非作答状态 | not_answer明确保留当前题，不计作答；概念求助仍用提示；暂停保留当前题和进度 |

复用独立加密互动记忆表、消息事务、幂等、审计。新动作只开放第一课，第二至八课版本及完整教学Prompt与af0605d逐字一致，见本地`test-results/feedback-review-other-prompts.json`。没有新表或迁移。第一课版本为`7.1-feedback-review`，旧课只读；老师教学内容和逐题反馈未删减，拒绝剩余题是自愿出口。

## 三种结构化记录

1. **案例回顾**在现有加密课程状态`blueprint.case_review`：status、fingerprint、summary、source_message_ids。只概括已校验当前案例，不作为本人新证据，不直接写入偏好记忆；内容变化重新生成，单纯核对/刷新不增加调用。来源与个人/虚构身份有程序校验，语义忠实程度仍需模型专项验证。仅有来源ID校验不能证明全部文本语义正确。
2. **突发互动Reflexion**在原独立表：原话/消息来源、observation、hypothesis、alternative_explanation、scope、reply_length、follow_up、tone、response_type，加task_action和applied_action。它解释本次教学调整，effect仍为not_measured。题量停止动作不会自动成为后续每课跳题指令；局部拒绝不推断永久偏好。
3. **固定课末Reflexion**沿用每课结束后的独立异步LLM及结构化observations/suggestions/hypotheses。观察与建议带来源，假设包含context、alternative_explanation、next_action、verification，applied=false。本轮补入停止检验的上下文约束，不能把Agent案例摘要当用户独立掌握的证据，也不为避免跳过强制补练。课末LLM失败不撤销课程完成；现有重试/审计机制保留。

事件触发只解决及时调整，课末反思负责复盘整课；两者分工保留。案例回顾是给用户看的内容整理，不命名为Reflexion。LLM提出判读和文本，程序校验来源、动作、合法阶段并保存；不以节约token省略必要理解。

## 验证

离线回归210项通过（公共40、课程170，新增本轮专项10），见本地`test-results/feedback-review-regression-final.log`。专项涵盖候选/漏检单次判读、原答保存、不误记提示/错答、暂停恢复、否定转述、不越课启用新候选、摘要缓存/失效/外来来源/虚构身份、加密独立记忆及数据库重连/幂等。三项前端草稿/渐显/流式协议脚本及JS语法、Python编译通过。

真实DeepSeek使用十组合成检查，涵盖题量拒绝、规则漏检、否定、转述、只嫌长、求提示、暂停、错字、实质不同原意及虚构案例回顾。前两批发现：求助被误报反馈、暂停与旧personal_intent契约冲突、模型回复反问违反事件契约；修复后第三批10/10通过。第二批旧断言只验证未结束检验，曾把保护性暂停计入通过，收尾已收紧为不得暂停且保持当前题，不据旧计数宣称体验通过。

本地原始证据：`feedback-review-deepseek-first.json`、`feedback-review-deepseek-second.json`、`feedback-review-deepseek.json`。三批保存usage的调用共38次，76,340 total_tokens，88,213ms累计模型耗时；最后一批13次、26,726 tokens、29,232ms。无隐藏重试，失败记录保留；这些统计不含网页体验调用。

网页已完整走过：拒绝个人经历→明确仅本次→虚构案例含“白跑了一堂”→自然回顾并保留原话→确认→第一题正确→第二题表达题量拒绝→停止剩余题→跳过目标→拒绝作业→完成→固定课末LLM Reflexion成功。课末观察准确区分第一题已答与第二至四题未观察，保留其他解释与待核对建议，未自动跨课采用。验证会话为`116b0e61-e8dc-417f-a1f5-2f3233ebeade`，本地截图：[自然回顾](../../test-results/feedback-review-recap-browser.png)、[题量拒绝即时调整](../../test-results/feedback-review-stop-browser.png)、[完成及课末反思](../../test-results/feedback-review-completed-browser.png)。刷新核对阶段保留了摘要、原话和来源。

前端验证还发现评分暂留在侧栏显示“暂未辨认清楚”，本轮一并修复：材料未提供评分在结构化payload说明原因，虚构材料的评分暂留行不显示在侧栏。最终210项回归覆盖该最新代码；页面已刷新确认评分行不再出现。旧8013服务保留，新8014为隔离体验；最终重启临时服务加载全部代码，合成验证会话随该临时进程结束清除，截图保留。邀请码course-preview，可从头体验。

所有结果均为工程/有限模型验证，不代替用户/教师验收，不证明所有表达都稳定或教学效果已验证。来源ID及身份校验不等于全部语义正确；深层假设及指导收益仍需后续专项验证。
