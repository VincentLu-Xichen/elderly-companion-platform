# 前两课后端可读性整理

2026-10-23，按用户“清晰化优美一下剩余代码”的要求实施。工程整理完成，仍属于R-010；两课自然对话质量继续待体验，不因本次重构关闭原有问题。本次比较基线为021完成后的工作目录快照，包含此前尚未提交的修改，不以Git HEAD冒充本轮旧版。

## 旧代码 → 本次变化 → 用处

| 原来的阅读负担 | 本次变化 | 带来的用处 |
| --- | --- | --- |
| `runtime.py`同时定义初始状态、组装页面数据和处理对话 | 提取[`state.py`](../../cbt_course_llm_freeform/state.py)与[`presentation.py`](../../cbt_course_llm_freeform/presentation.py)；原runtime导入入口继续可用 | 想看“保存哪些状态”“页面展示什么”“一轮怎么推进”时可以分别阅读 |
| `process`里既有前置分派，又有普通教学的细节 | 前置检查、控制、反馈和课程分派保留在`process`，普通教学提取为`_teach`，执行顺序不变 | 先读主入口理解各类请求去哪里，再进入教学细节 |
| 第二课一段长函数混合复习、用户操作、摘录和回应 | 提取`_process_recall`、`_handle_natural_action`、`_apply_observations`、`_reply_after_observations` | 后续定位“复习没结束”“摘录没收全”“回应太死板”时能找到对应职责 |
| 第二课大量局部`f`、`d`、`q`增加理解负担 | 按语境改为`flow`、`decision`、`quiz`或`question_spec` | 阅读时能区分流程状态、模型判断和题目，不改协议中的字段名 |
| 压缩的单行条件和连写语句不便检查 | 对32个活动后端模块统一Black格式，使用100列、保留字符串引号；Ruff清理12处无用导入 | 条件、分支和调用参数更容易逐项核对；没有增加格式工具依赖 |
| 课程成果记忆为了取常量依赖整个runtime | `memory.py`改从`state.py`导入`IMPLEMENTATION` | 缩小模块依赖，记忆读写不必依赖对话调度入口 |

两个教学文件`lesson_1.py`、`lesson_2.py`逐字节不变；两个完整生成Prompt、六份共享Prompt和三份公开模型契约的指纹均不变。第一课仍为`7.5-two-lesson-backend`，第二课仍为`6.1-xmind-flow`。没有更换模型、增加模型调用或修改数据库结构。

此次展开语句后部分文件行数增加，不能把行数作为简化效果。仍保留第一课普通教学内部的较长分支；没有为追求短函数继续引入通用流程框架，也没有借整理删除程序守卫或覆盖机制。第二课回应模板等已知体验问题仍在。

## 现在怎样读代码

按一次请求的方向阅读即可：

1. [`catalog.py`](../../cbt_course_llm_freeform/catalog.py)：当前开放哪两课、各自版本是什么。
2. [`state.py`](../../cbt_course_llm_freeform/state.py)：创建会话时有哪些状态，什么成果允许复用。
3. [`router.py`](../../cbt_course_llm_freeform/router.py)与[`services.py`](../../cbt_course_llm_freeform/services.py)：请求进入后，如何检查身份、读写加密数据、处理幂等和审计。
4. [`runtime.py`](../../cbt_course_llm_freeform/runtime.py)的`process`：先处理安全、控制、互动反馈，再分派本课教学。第一课普通教学进入`_teach`；第二课进入[`lesson2_flow.py`](../../cbt_course_llm_freeform/lesson2_flow.py)的`process`。
5. [`agent.py`](../../cbt_course_llm_freeform/agent.py)与[`schemas.py`](../../cbt_course_llm_freeform/schemas.py)：模型看到什么、允许返回什么；运行时仍校验来源、动作和状态。
6. [`presentation.py`](../../cbt_course_llm_freeform/presentation.py)：把当前状态组装成页面/API响应。流式传输继续由[`streaming.py`](../../cbt_course_llm_freeform/streaming.py)与[`reply_stream.py`](../../cbt_course_llm_freeform/reply_stream.py)承接。

这里的函数拆分只是代码职责整理，不是新增多个Agent或多次模型请求。互动反馈和课末Reflexion仍沿用既有机制；课末建议仍不自动跨课采用。

## 验证结果

| 检查 | 实际结果与范围 |
| --- | --- |
| 重构前后离线行为对照 | 6组、38轮记录完全一致：第一课正常13、第二课正常14、同例停问/暂停恢复3、个人边界2、评分/修正5、无效来源失败1 |
| 对照内容 | 回复、附件、完整状态、页面payload、trace和调用顺序逐项相等；固定UUID，只排除真实耗时字段。使用离线客户端，不涉及真实模型波动 |
| 契约指纹 | 两课完整Prompt、六份共享Prompt及`TeachingDecision`、第二课`Decision`、`CourseMessageCreate`的JSON Schema相等 |
| 完整现有回归 | 公共42项＋课程204项，共246项通过；两套分别耗时4.709秒、7.491秒 |
| 格式和静态检查 | 32个模块Black检查通过；Ruff全部检查通过，清理12处F401无用导入 |
| 编译与前端协议 | Python编译、JS语法、输入草稿、SSE协议和渐显检查通过 |
| 修改范围 | 14份模板/前端文件指纹不变；两份纯教学模块指纹不变；测试源文件未在022中修改 |

可重复的现有回归入口：

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts\run_regression.py
node scripts\test_course_draft.cjs
node scripts\test_course_stream_ui.cjs
node scripts\test_course_reveal.cjs
```

本机忽略目录`test-results/`保留`readability-manifest.json`、源码备份`backend-before-readability-20261023-220109.zip`、对照脚本`readability_contract.py`、三份快照`readability-before/extracted/formatted.json`及回归日志`readability-regression-first.log`。备份指纹已核对；这些本地证据不是仓库运行依赖，未上传。

本轮没有真实DeepSeek调用，新增API调用及API费用为0；没有据此测量真实tokens、响应耗时或费用变化。38轮相等是这些场景内的重构防回归证据，246项工程通过也不代表Agent听懂所有表达或课程效果提升。

没有重启旧预览、打开新端口、修改用户数据库、提交或推送。正在运行的旧进程不能据此视为已加载022。下一次体验需要加载当前代码；现有自然承接、目标重复、安全语境等待办继续由R-010收束。
