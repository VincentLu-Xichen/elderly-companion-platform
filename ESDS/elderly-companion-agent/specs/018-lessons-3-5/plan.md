# 实施方案

skill_flow独立管理3—5教学子步骤，沿用外层check_in/learn/practice/review/plan/summary状态。材料与问题分别配置，普通一轮一次结构化LLM；没有隐藏修复请求，失败事务不提交。最终回复校验保存后渐显，避免程序校正后暴露错误草稿。按钮零调用，普通自然语言通过同一判读器；模型可报告漏检互动反馈。

runtime在既有安全/互动判读之后分派skill_flow，所有新控制经阶段校验；boundaries/interaction接口对应技能任务，保留原功能。confirmed_ready识别skill暂留、memory仅导出可追溯本人字段；课末复盘加入活动上下文但不自动采用。页面复用材料容器、既有确认与输入框，skill活动单独显示，不侵入前两课呈现。

验证后在新端口运行真实模型，写完整案例与report。原始记录留忽略test-results，合成对话整理入specs，不输出密钥或用户真实数据。不提交推送。
