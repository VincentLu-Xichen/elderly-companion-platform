# 工作清单

- [x] 三课配置与契约
- [x] 普通轮次、可配置触发与反思/Actor
- [x] 成果引用、本人操作与加密审计
- [x] 网页、离线预览及轨迹脚本
- [x] 回归、页面验证及代码讲解

## 验证记录（2026-10-15）

- `scripts/run_regression.py`：通用 38、课程 44，共 82 项通过；包括三课完成、四种策略、来源撤回、拒绝分类、显式修订、失败不提交与同键重试，以及短反思窗口之外的审计保留。
- `scripts/trace_course_workflow.py`：none/per_turn/per_task_step/event_driven 均完成 26 轮固定虚构流程、生成 3 份成果。教学工作流模型调用分别 9/27/19/11 次，另各有 3 次独立课后复盘；这些是规则客户端的调用次数，不是质量或实际成本评估。
- `compileall -q daily_agent cbt_course cbt_course_llm_freeform webapp tests scripts` 与 `node --check webapp/static/cbt_course/course.js` 通过。
- `git diff --check` 通过，只有 Git 行尾转换提示。
- 桌面浏览器走完三课与课间采用；第 3 课核对候选、选择不确定、确认并完成。刷新后状态保留。
- 手机视窗 390×844：页面文档宽度等于可视宽度，分类核对/确认/课后选择/完成均可操作；测试后恢复视窗。
- 页面证据：`test-results/course-workflow-review.png`、`course-workflow-mobile.png`；轨迹为 `test-results/course-workflow-策略.json`。均使用虚构测试数据。
- 没有数据库表结构变化，未重复执行迁移；没有调用真实付费模型，尚不支持策略效果或教学收益结论。

交付讲解：[从一次回答读懂代码](../../docs/course-code-walkthrough.md)。
