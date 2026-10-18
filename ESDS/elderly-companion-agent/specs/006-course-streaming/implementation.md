# DeepSeek 接入与流式回复：改动、运行与验证

日期：2026-10-16。已实现并验证第 1 课真实模型网页完整流程，当前课次版本 `6.1-learning-check`。公共 Agent 与 Runtime 标记保持 `course-guided-v3` / `guided_cbt_v3`。本轮新增的是模型服务与传输能力，八课教学内容不统一改写。

## 相比原代码的变化

| 原来 | 现在 | 带来的作用 |
| --- | --- | --- |
| 客户端支持百炼/Azure，隔离脚本只运行规则预览 | 增加独立 `DeepSeekChatCompletionsClient`；可显式启动真实 DeepSeek 模式 | 使用用户已有 API，教学、检验与课后复盘均走真实模型；没有密钥就报配置错误，不自动改用模拟 |
| 网页等待整轮 JSON 后显示回复 | 新增 POST `messages/stream`，模型 SSE 经后端转发为回复片段和最终结果 | 模型生成中即可阅读，无人为延时或打字模拟；确定性按钮仍直接给出结果 |
| JSON 一次性解析 | 仅从不完整 JSON 中投影顶层 reply，正确处理转义、中文与跨块字符 | 不向页面流出字段、评分、Reflector 或模型思考内容；完整结构仍交原有 Pydantic 与来源校验 |
| 整轮完成才更新页面和记录 | 临时显示文字，最终持久化成功事件才更新记录；错误撤下临时文字 | 失败不推进，断流后同键重试可恢复已保存结果，避免重复扣调用和重复记录 |
| 历史 assistant 消息用 `{id,text}` 包装 | DeepSeek 适配层将角色化历史打包为 course_history 数据，保留每条 id/role/content | 真实测试发现模型会模仿历史封装，返回 id/text 而缺少 reply；将历史作为输入数据可避免这种格式冲突 |
| 第 1 课检验 Prompt 没有明确 JSON 字样 | 补充 JSON 输出契约标识，第 1 课升为 6.1 | DeepSeek JSON 模式要求明确 JSON 指令，修复实测 400；旧第 1 课只读，其他课版本不变 |
| 非流式服务统一使用请求 DB 会话 | 流式工作线程独立创建 DB 会话，队列上限 32 | 不跨线程共享 Session；浏览器断开后可继续保存，重连按幂等恢复 |

结构化结果和 Reflexion 继续区分：前者保存任务表现，后者保存有依据、限于情境、可核对的解释与建议。流式只是呈现方式，不改变确认权、判据、反思策略或跨课权限。

## 本机运行

本机 `.env` 已由用户填写，受 Git 忽略。只需这些模型设置，密钥值不写入报告：

```dotenv
CBT_COURSE_PROVIDER=deepseek
CBT_COURSE_MODEL=deepseek-flash
DEEPSEEK_API_KEY=<仅在本机填写>
```

```powershell
.venv\Scripts\python.exe -B scripts\run_course_preview.py --port 8001 --provider deepseek --policy none
```

入口 `http://localhost:8001/`，邀请码 `course-preview`。服务仅监听回环地址，使用随机应用密钥与隔离临时数据库；页面显示“模型服务：DeepSeek”。8000 保留原离线服务，两者不要混用；同一浏览器的 localhost 登录 cookie 按主机共享，切换服务后可能需要重新登录。

DeepSeek 使用官方 `https://api.deepseek.com/chat/completions`，`thinking.type=disabled`、`response_format.type=json_object`。模型名默认依当前官方文档设为 deepseek-flash，也可按实际账号修改 `CBT_COURSE_MODEL`。API 密钥只随服务端请求发送，不进入 HTML、JavaScript、日志或报告。

## 一轮运行的代码连接

```text
course.js → stream.js 发 POST（内容、操作、修订号、幂等键、CSRF）
  → router.py 检查登录、归属、同意、长度与速率
  → streaming.py 工作线程创建独立 Session
  → services.py 保存本人消息和 pending TurnEvent，获取串行租约
  → runtime.py 按课程阶段分流
  → agent.py 调用 DeepSeek；reply_stream.py 只提取可显示的 reply 增量
  → streaming.py 推送 reply_delta；页面暂时显示文字
  → 完整结果通过 Schema、来源、阶段和回复规则校验
  → services.py 保存加密状态、消息与审计
  → result 事件 → 页面以最终回复收口并更新学习记录
  → 完成课程后，独立生成并轮询显示课后 Reflexion
```

事件类型是 start/reply_delta/result/error，长等待可以有 heartbeat。原 `messages` JSON 接口仍可使用。任何 HTTP 或流式错误都不触发自动改走另一个接口，避免同一轮发起两次模型请求。浏览器只有收到 result 才认为本轮成功；掉线后保留原请求重试。

none 策略的普通教学可流式显示；如果配置其他课内反思策略，教学草稿不会提前流出，仅在确实触发时由最终 Actor 流出。若未触发，该轮在完成后一次显示。判读结果、Reflector 和课后复盘的内部数据均不作为教学文字流出。按钮、提示与目标确认不增加模型调用。所有片段都是生成中内容，最终服务端可能因阶段切换或回复约束替换它。

## 已验证

- 113 项离线后端测试：公共 40、课程 73。日志：`test-results/course-stream-regression.log`。回归子进程显式清空真实密钥，避免误计费。
- 6 项前端协议检查通过：中文/emoji 的字节分块、SSE 跨块、服务端错误、缺少终止结果；命令 `node scripts/test_course_stream_ui.cjs`。
- JS 语法与 Python 编译检查通过。数据表没有变化，不新增迁移。
- 后端覆盖流式片段早于模型结束、结构字段不泄漏、反思草稿隔离、无效来源/结构不推进、断连后保存与同键回放、CSRF、归属与真实客户端参数。
- 最终协议的真实 DeepSeek 检查成功：一次教学返回 32 个可见片段，首段 1478 ms、教学轮总计 1843 ms；检验判读为 matches 且来源正确。此为单次联通样例，不是延迟或质量基准。记录：`test-results/deepseek-course-smoke.json`；复现脚本 `scripts/check_deepseek_course.py` 会产生两次计费请求。
- 浏览器实际完成一条真实路径：示范回答 → 四要素提取 → 本人核对 → 四题判读 → 统一反馈 → 目标确认 → 课后安排 → 本人反馈 → 完成 → 真实课后复盘。最终协议的这条路径没有发生格式错误。截图：`test-results/deepseek-course-complete.png`。

首次真实网页测试曾发生输出格式不符；校验按预期阻止推进。问题定位为历史 assistant 的 id/text 封装诱导，适配层已改为带来源的历史输入数据，并新增回归。还发现虚构例子显式标记后，模型可能邀请换本人经历而不摘录；这属于后续教学提示专项理解问题，本轮没有降低原话校验或把虚构案例自动写成真实经历。

## 实际限制

目前验证了 DeepSeek 的第 1 课完整路径，百炼/Azure 的流式复用由离线检查覆盖，尚未做它们的真实调用。第 2—8 课真实教学、复杂拒绝/纠正、多轮长历史、提示稳定性、不同反思策略与真实学习收益仍需专项测试。有效 JSON 仍可能违反应用 Schema 或来源要求，系统会拒绝该轮，不承诺模型永不出错，也没有隐藏修复重试。

参考：[DeepSeek 首次调用与模型名](https://api-docs.deepseek.com/zh-cn/)、[JSON 要求](https://api-docs.deepseek.com/zh-cn/guides/json_mode/)、[流式、用量与思考模式参数](https://api-docs.deepseek.com/api/create-chat-completion/)。
