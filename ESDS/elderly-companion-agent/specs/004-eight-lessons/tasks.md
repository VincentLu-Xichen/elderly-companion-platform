# 工作清单

- [x] 八课配置、材料、分支与公共契约
- [x] 运行时路径操作、阶段门禁与反思适用性
- [x] 单课采用及多课回顾、来源失效与成果审计
- [x] 页面、离线预览和八课轨迹
- [x] 回归、语法、电脑/手机页面
- [x] 报告对照、代码讲解、专项理解测试计划（专项测试本身仍待执行）

## 本轮验证（2026-10-16）

- 基线 82 项；完成后 `scripts/run_regression.py` 通用 39 + 课程 59 = **98 项通过**。新增课程/分支的实际 API、持久化、独立课后复盘和完整导出均覆盖。
- 重点覆盖：八课和第 5、7 课全部分支可独立完成；路径未选、跨路径字段与静默改选被拒；确认/课后选择后重选会撤回旧记录；采用不将计划变成行为；第 8 课拒绝/缺课、同归属与版本校验、来源逐项删除/失效及成果引用。
- 八课固定虚构流程四种策略均走完 74 轮，生成 8 份成果，第 8 课记录 7 份参考来源。普通工作流调用次数 none/per_turn/per_task_step/event_driven 为 27/81/63/29，另各 8 次独立课后复盘。规则客户端没有真实 tokens 或质量分数，不能推论策略优劣。
- 另一组 exposure + relaxation 路径在 per_turn 下也走完八课；全部路径另有运行时和 API 回归，不依赖某一条默认路线。
- 轨迹：`test-results/eight-lessons-{none,per_turn,per_task_step,event_driven,alternate}.json`，均标注规则演示和虚构数据。
- `compileall`（daily_agent、cbt_course、cbt_course_llm_freeform、webapp、tests、scripts）、两份 JavaScript 的 `node --check`、`git diff --check` 通过。当前文档的相对链接与 18 条种子案例 JSON 解析通过。
- 桌面：八课目录；第 5 课 activation 确认/课后选择后重选 exposure，旧记录撤回，再按新路径确认完成；第 8 课接受两份来源、展开记录、填写本人应对计划并完成。
- 手机视窗 390×844：第 7 课 relaxation 选择、填写、核对和完成；文档宽 375、scrollWidth 375，无页面横向溢出。结束后恢复视窗。
- 长摘要和多课回顾使用可展开记录，来源、路径与“计划尚待实际反馈”保持可见。页面证据为 `test-results/eight-lessons-catalog.png`、`eight-lessons-path-review.png`、`eight-lessons-mobile.png`、`eight-lessons-review.png`、`eight-lessons-completed.png`。
- 没有数据库表结构变化，未重复迁移；未修改真实模型配置、未调用付费模型。原 8000 体验保留，新版可在 8001 独立临时数据库体验。

## 后续边界

[专项理解测试](understanding-tests.md)与[18 条种子案例](understanding-cases.json)均为准备状态 `not_run`。下一轮先测基础理解与纠错，再分开比较反思频率和内容；尚无真实模型指导质量、学习效果或临床效果结果。

[代码阅读及前后对照](code-walkthrough.md)用于报告，不把本轮继承的六阶段、加密或反思策略写成本轮新发明。
