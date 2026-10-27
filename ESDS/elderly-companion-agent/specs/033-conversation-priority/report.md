# 033 统一主Prompt中的交流优先级：实现与验证

## 范围与改动
用户明确授权修改Prompt和必要代码，并打开网页调用真实API验证。第一课7.9.2-conversation-priority，第二课6.2不变。保留每课统一主Prompt与现有辅助机制，没有任务分块、多意图检测、多Agent、模型/参数调整或新的调用类型。

统一主Prompt强调：倾诉不执行pending_task、不主动整理改写记录、不分析四要素、不催评分核对；不因字段齐全就回顾记录。现在的感受/新看法不自动覆盖当时的想法；含糊纠正先承接、必要时澄清。邀请须给本人选择并等待，不直接宣布返回。

必要代码：仅在已存在conversation状态、模型显式选择conversation但附带忠实当前原文的observations时，拒绝这些可选写入及分析信号，保存conversation_record_guard审计，保留未声称写入成功的自然回复。无来源/改写引用、advance、case_options、attempted_field和写入成功声明仍拒绝。非交流或真实作答不使用该处理。不自动重标answer或resume_course，不清洗来源，原始JSON保留。模型输出契约没有新增字段，guard仅为内部审计。

本人明确要求修改原记录可按已有resume_course路径处理，来源授权候选补充修改/更正等表达；不是交流中任意说法都恢复课程或改记录。

## 离线验证
课程260＋公共56＝316项通过；新增7项行为测试，含旧ID/改写引用、自动推进、冒充已写入仍拒绝；正常0分与明确修改仍可采用。freeform源码compileall通过。

032 request-006原始JSON逐字不改，在合成起点＋捕获上下文回放：旧resolve_turn发生non-answer写入冲突，新运行保留reply、拒绝候选thought与correction信号，案例、评分和待办不变。不是原完整网页状态重演，也不能说旧reply的措辞改善。

## 真实网页测试
run_id：20261027-033-conversation-priority。独立合成账户从课程目录开始，没有教学阶段/历史种子；模块.env显式覆盖加载；DeepSeek/deepseek-flash、policy none，其余参数保留。

9轮文字输入＋1开场按钮；9次真实请求（含辅助判读和一次案例回顾）均返回，文字轮9/9程序成功。67,246 tokens（输入65,321／输出1,925）；请求等待合计16.717秒，首字等待与金额未知。上限12，余量3关闭，无重试、无测试中候选修改。

- T03倾诉且不分析不评分：承接、不追分。
- T04持续倾诉：来源正确，不转四要素教学。
- T05原失败同句“我只是想念她，并不是认为她一定不在乎我”：原始JSON为conversation、observations=[]、signals=[]；没有程序过滤介入，记录不变。回复仍偏长并带少量解释性措辞，不能称完全自然。
- T06说轻松、暂时说完：reply给出继续或暂留的选择，未直接宣布恢复；JSON invite_return，持久化conversation＋pending，未获同意不推进。
- T07拒绝返回与T08请勿再问：继续承接，未立即重复邀请。本次通过listen，不能冒称decline_return新分支已真实覆盖。
- T09主动继续：原案保留，评分仍暂留，进入review且未本人确认。但reply再次询问暂留评分，量尺说成1—10（实际应0—10）；语言与状态仍有不一致。T02也出现量尺口误，保留为未解决问题。

## 结论及局限
本轮支持：原失败输入本次不报错且无写入候选；邀请与待答状态一致；此路径连续倾诉、拒绝和主动恢复通过。新增代码guard只有离线/原JSON回放证据，新模型本次没有触发它；未做同起点新旧配对，不推断稳定成功率或单Prompt优于分块。原评分暂留后追问、量尺口误、多意图互斥、页面错误及其他历史问题保留；整课/第二课/语音未在本轮实测，R-010仍Validating。

源代码前后实际脏快照、差异与哈希保留，不只按HEAD标识；测试期间源码无漂移。没有改.env、provider、前端、真实数据库；用户原服务不动。临时8050测试完成后停止，无commit/tag/push。

证据：test-results/dialogue-evals/20261027-033-conversation-priority（本机忽略目录）。对外合成副本：reports/2026-10-27-lesson1/033统一Prompt验证。.private-runtime.json及独立数据库仅本机，不入证据包。原始run和根docs仍Git忽略。

组会后研究：按任务分块Prompt的边界、共享状态、路由时机与混合意图，归并I-010；当前未实施分块。

补充工程检查：默认git diff --check将原有CRLF行尾报告为尾随空白；前后行尾形式保留，使用git -c core.whitespace=cr-at-eol diff --check通过。未为消除报告批量改行尾。
