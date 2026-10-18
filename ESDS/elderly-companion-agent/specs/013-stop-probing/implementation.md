# 第 1 课 6.8：停问、同例回顾与渐进显示

范围：用户本轮要求的固定回复逐步显示、逐项按钮、追问反感、原事件保留及礼貌回应。R-003/I-003/I-004，状态 Validating，等待用户实际体验。

## 旧版 → 新版

| 旧行为 | 改动 | 作用 |
| --- | --- | --- |
| 截图“收到您的表达……”来自 `_interaction_event` 失败兜底；具体异常尚未从用户审计核实 | 风格/个人拒绝分流，风格失败不设个人拒绝 recovery，保留失败审计 | 不因抱怨追问而错误换成虚构案例 |
| 风格仅 reduce/standard，缩短后仍可能补问 | 增加 `follow_up=stop,response_type=review_current_case,tone=polite` | 保留同一 case_id 和原字段，缺项标未收集，进入待核对；不填造、不自动确认 |
| 个人练习仍常驻逐项“想不起/不谈”按钮 | 新版隐藏，保留自然语言拒绝、暂停及核对修改；旧 API 兼容 | 减少表单感，整体不满不再被当单字段暂留 |
| 虚构卡片可能混入用户另一件个人经历 | `practice_origin` 提交来源判断，程序拒绝不一致提取 | 个人故事保留对话，不冒充虚构人物；仍依赖模型来源判断 |
| 无模型增量的程序回复瞬间替换气泡 | 保存成功后前端分段显示，上限1.6秒，保留原 LLM SSE | 无新增调用；支持 emoji、减少动画、后台即时结束 |

## 应改哪些层

- [interaction.py](../../cbt_course_llm_freeform/interaction.py)：结构化理解、回复动作和语气，假设与观察仍分开。
- [agent.py](../../cbt_course_llm_freeform/agent.py)：实际边界候选/待确认才使用边界 Prompt，讲法不满用专用 Style Prompt。
- [runtime.py](../../cbt_course_llm_freeform/runtime.py) 与 [practice_flow.py](../../cbt_course_llm_freeform/practice_flow.py)：同例停问、保留原字段、未收集项留空及本人核对；后续模型仍提问时回到当前记录回顾。
- [interaction_memory.py](../../cbt_course_llm_freeform/interaction_memory.py)：可选 type/tone 兼容旧记忆，同库独立加密表不增列；不是个人询问禁令，不以 API temperature 表达礼貌。
- [schemas.py](../../cbt_course_llm_freeform/schemas.py)、[prompt.py](../../cbt_course_llm_freeform/prompt.py)：来源契约，强烈反馈承认负担、礼貌道歉、具体调整，不训诫、不推测能力。
- [course.js](../../webapp/static/cbt_course/course.js)、[stream.js](../../webapp/static/cbt_course/stream.js)：按钮显隐及 `courseRevealReply`。固定文本是保存后的渐显，真实模型流式仍按原 SSE；不把动画当成 LLM 实时生成。

拒绝整个案例继续按 011 处理；反感追问不更换案例。未说到的项只是本次未收集，允许核对修改，不能当理解差或已掌握。没有重写独立检验、课末协议或其他课设计。

## 验证

- [回归日志](../../test-results/stop-probing-regression.log)：**176 项（公共40＋课程136）通过**，包括同例保留、停问后不再重复询问、失败无隐私边界/记忆、否定转述、按钮、来源混用；原确认、检验、幂等和隔离继续回归。
- JS：`test_course_draft.cjs`、`test_course_reveal.cjs`、`test_course_stream_ui.cjs` 通过，覆盖草稿/重试、渐显分段、emoji、减少动画、后台完成和 SSE。Python compileall、JS syntax、diff 检查通过。
- 真实 DeepSeek 两组六个合成案例均通过。第一组7次调用、24136 tokens、18281ms；第二组7次、21579 tokens、21016ms。合计14次、45715 tokens、累计39297ms，不含浏览器调用，不是单次等待时间。
- 原始结果见 `test-results/stop-probing-deepseek-first.json` 与 `stop-probing-deepseek.json`。第一组“解释太长”走普通教学；补齐候选后第二组验证走风格判读。两项明确追问投诉实际得到 `review_current_case/polite/stop`；隐私拒绝仍独立确认；另一件个人故事触发来源守卫。

小样本不能证明全部语义、语气或教学效果。截图只能定位到旧失败出口，不能直接归因 API。来源守卫依赖模型判读，不能宣称完全解决所有材料混用。既有课末阶段归因问题仍在 I-004，本次不替代其专项验证。

## 体验

第一课 `6.8-stop-probing`，旧版只读，其他课版本不变，无新表迁移。隔离体验 `http://127.0.0.1:8011/`，邀请码 `course-preview`。8010 旧服务与记录保留；临时服务数据库/签名独立，切换可能需重新登录，正常关闭后临时数据清除。用户体验待反馈。

Edge 页面验证：新版个人练习不显示逐项按钮；输入三项后，明确投诉追问，实际礼貌回应并回顾原事件，三项记录均保留，第四项暂留，进入待本人核对。没有在这条反馈后换虚构材料；后续新检验只在本人确认记录后按既有课程路径进入。

证据：[按钮已移除](../../test-results/stop-probing-no-field-buttons.png)、[礼貌停问并保留原事](../../test-results/stop-probing-review-browser.png)。固定回复经暂停/恢复与进入检验观察到“已保存，正在显示回复”后恢复操作，逐帧分段和后台/减少动画分支由 JS 测试验证。未录制视频，不把完成态截图当作逐帧证据。

该网页路径随后本人确认三项及暂留项，四题检验均跳过，再用自然语言跳过目标/课后安排并结束，正常完成且复盘就绪，见[完成态](../../test-results/stop-probing-completed-browser.png)。这验证课程可继续，不证明四题判读或掌握；课末原因假设仍需专项核对，未自动应用。页面已返回目录，可点第一课“重新学习”开始新一轮。
