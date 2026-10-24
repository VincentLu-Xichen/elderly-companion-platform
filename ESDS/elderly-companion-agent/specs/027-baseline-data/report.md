# 当前A基座baseline数据与失败记录

2026-10-24。已按用户要求先测试并记录当前baseline：**原6个局部案例、8轮全部尝试，9次模型请求均取得回复，7轮程序成功返回、1轮来源校验拒绝；5/6案例通过既定程序检查。** E03发生跨案例混写，baseline质量未通过。数据采集已完成，不将它说成基座可靠或整课验收完成。

本轮没有改课程、Prompt、模型配置、前端或产品运行代码，没有进入B/C/D，没有启动网站或使用真实用户数据库。没有为修饰结果重试/重采。下一修复建议因新证据优先考虑E03，E04等继续保留；本轮不实施这些修复。

## 版本、来源与证据入口

| 项目 | 本轮实际值 |
| --- | --- |
| run_id | `20261024-100022-A-baseline-verified-source-64bcab` |
| 开始时间 | 2026-10-24 10:00:22 +08:00 |
| 原始目录 | 本模块`test-results/dialogue-evals/`下同名目录，Git忽略 |
| 案例 | `cbt12-local/1`，原cases.v1，6例8轮，不改题或起点 |
| 课程 | 第一课7.5-two-lesson-backend／第二课6.2-contrast-reply |
| 配置/返回模型 | deepseek／deepseek-flash，所有请求实际返回deepseek-flash |
| 参数/策略 | temperature=1.0，thinking disabled，非流式；任务反思none，事件Reflexion启用 |
| API来源 | explicit_env_file，用户指定的模块.env；manifest含来源，不含密钥/指纹 |
| 预检 | 客户端密钥与文件相同，继承旧值有冲突但未采用，文件字节未改；不能代替服务商账单身份核对 |
| Git | harrison／0cc68ed＋累计未提交工作，HEAD不是完整实验版本 |
| 实际源码总指纹 | `b7bf1c96ff22f920c91d1eaeff8d6ab4305f42771a52202089dd8606dd80f803` |
| 上限/实际请求 | 上限12，实际9；失败处理后没有补跑，不用完预算也无需继续消费 |

修改前预检快照为`20261024-095943-baseline-preflight-50a2c2`；相对026快照仅三份方向说明变化，无产品Python/网页变化。采集目录保留manifest、source.zip、cases、requests、results、summary；另外保存Prompt全文/哈希、请求映射/职责汇总、独立Coding Agent审阅，以及E03旧JSON零调用回放诊断。原始记录不覆盖。

可随Git保存的入口：

- [8轮完整输入、模型JSON、最终展示和状态](transcripts.md)
- [逐请求tokens/时间与用户费用登记表](usage-ledger.md)
- [baseline配置/Prompt/版本契约](baseline-contract.v1.json)

## 每例实际结果

| 案例 | 程序检查 | 真实表现和限制 |
| --- | --- | --- |
| E01-a一次四要素/零分 | 通过 | 四项及相信程度0分保留，进入review，未代确认。回复主要复述；后续概念教学未由此轮证明 |
| E03-a暂聊→返回 | **失败** | 首轮虽标different_case，仍把室友情境/很烦写入考试case，保留考试旧想法；第二轮返回考试时，模型引用seed-user旧评分作为新摘录，程序拒绝。未产生第二轮正式回复 |
| E04-a投诉→确认 | 通过既有断言，体验未通过 | 停问、原例和缺项保留；但“记录准确，可以继续”仍停review，confirmed_record=null。既定断言不覆盖复合确认推进，不能当质量通过 |
| E06-a准确 | 通过 | 精确短确认0模型调用，进入assessment。属于程序路径，不是LLM理解证据 |
| E06-b目标 | 通过既有断言，体验有缺陷 | 模型将“有人打招呼时能想到一句简单回应”教学情境带入目标建议，未获用户提供该改善情境；程序又追加长参考目标。未代确认，不代表内容合适 |
| E07-a小雨比较 | 通过 | “并不评分，也不说明谁想得更好或更糟”完整保留，随后接原固定回看问题；无个人三栏，未确认。仍是局部验证 |

上述是本轮Coding Agent审阅；原始human_review仍pending，用户/教师体验未代评。单次采集不是稳定性或统计优劣证明。

## 关键失败：E03原始模型与程序分别做了什么

初始练习是考试，已知情境“数学考试最后一道题没做出来”、想法“别人肯定都会，只有我不会”、情绪“担心”，行为未知。

第1轮预设输入：

> 先不说考试了，今天室友在我休息时一直外放视频，我现在很烦，只想先聊一下这件事。

真实JSON同时给出：

```json
{
  "practice_origin": "different_case",
  "observations": [
    {"field":"situation","value":"室友在我休息时一直外放视频","source_message_id":"E03-a-user-0"},
    {"field":"emotion","value":"很烦","source_message_id":"E03-a-user-0"}
  ],
  "next_practice_field":"behavior"
}
```

这段是完整原JSON的关键字段节选，完整reply/assessment见对话全文。最终展示：

> 好，先聊这件。室友外放视频、您正在休息时被他打扰，这确实让人烦。那当时您做了什么，或者没做什么？

状态仍是原case_id，但situation和emotion已换成室友/很烦，thought仍是考试旧想法。`same_case=true`只证明编号没换，不能证明同一件事没混写；本轮`same_situation=false`确实发现了问题。

**定位：** 模型识别了different_case却仍输出可写个人摘录；程序第一课_teach在这里仅对fictional来源检查practice_origin，个人练习未同样拦截different_case，因此接受了来自当前原话、但属于另一事件的摘录。两处问题共同形成混写。来源忠实不等于案例语义正确。

第2轮输入明确返回考试并给出“考完一直翻答案”。模型没有采用本轮行为，反而提交旧消息seed-user的“相信程度7分”。`_apply_observations`要求本轮来源，抛出“课程记录的字段或原话来源无效，本轮进度未改变”。这是程序来源拒绝，**不是模型API连接失败**。本轮输入状态未被进一步改变，但第1轮已经混写的状态仍在，不能说守卫恢复了原始考试记录。

用同一份原始JSON离线重放，两轮请求/参数与记录一致，第1轮完整回复/状态一致，第2轮在相同位置拒绝。回放0次网络调用，诊断保存`E03-offline-diagnosis.json`。本轮只定位和记录，不放宽来源校验或改案例期望。

## 费用和等待

用户表示可以自行记录token花费金额；程序负责usage与调用轨迹，提供空白金额栏供账单核对，不估算费用。

| 职责 | 请求数 | 输入tokens | 输出tokens | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 第一课普通教学 | 4 | 21,820 | 564 | 22,384 |
| 第二课普通教学 | 1 | 2,794 | 88 | 2,882 |
| 自然案例回顾 | 2 | 1,500 | 100 | 1,600 |
| 互动反馈判断 | 1 | 2,556 | 156 | 2,712 |
| 目标导航 | 1 | 1,533 | 90 | 1,623 |
| 合计 | **9** | **30,203** | **998** | **31,201** |

9次均有usage；E03被程序拒绝的那次也计入。8轮完整等待合计**16,447ms**，含失败；非流式首字等待未知。请求等待与完整轮次等待分别保留，不能混用。金额未知、由用户补记，未知不是0元。

这轮比025少一次辅助回顾，是失败路径造成的调用轨迹变化，不能宣称优化省tokens。历史运行凭据受限、不同时间且模型存在随机性，即使返回名称和Prompt相同，也不能把表现差异归因于新旧密钥或账户。

## 工程验证与范围

- 默认离线6起点检查通过；完整隔离回归**257项**通过：公共49项5.862秒、课程208项8.236秒，日志`test-results/dialogue-evals/027-baseline-regression.log`。
- 原案例和主/辅助Prompt均未改，实际Prompt哈希与trace一致；API来源、源码zip及案例哈希、记录完整性另行核对。
- 运行器返回码1来自E03失败和5/6检查，并非应忽略的命令问题。9次提供商请求均成功，不能报告为9次课程轮次均成功。
- 局部起点直接构造，不走网站或真实数据库；不验证刷新、跨课记忆或固定课末Reflexion。当前存在关键局部失败，未追加整课付费测试。

**结果判断：** baseline证据已建立，基座质量仍Validating。优先建议修E03“暂时换话题时的案例保护与返回”，其数据混写严重性高于之前建议的E04复合确认；E04与目标污染仍保留。这是基于新证据的顺序建议，本轮没有转去实现。后续修复按一个主要变量、同案例对照推进，B/C/D继续后置。

## 复现和Git保存

本轮已执行的真实命令是在模块目录：

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts\run_dialogue_eval.py --live --env-file .env --max-calls 12 --label A-baseline-verified-source
```

上面记录实际运行方式，不是让你立即重复消费；每次执行会新建run_id。离线恢复去掉--live即可。正确源配置由026入口执行，不继承旧密钥。

本轮新文件集中于027：spec/plan/tasks、report、transcripts、usage-ledger、baseline-contract及git-save-paths；根管理资料与模块恢复入口仅更新事实。本轮产品/运行器/测试代码没有修改，保存的是原有累计代码＋当前合成证据。已有大量未提交依赖，只提交027文档不能声称源码已保存。

工作区根目录的具体保存步骤（本轮未执行暂存、提交、标签或推送）：

```powershell
git status --short
git diff --stat
$cbtSavePaths = Get-Content -LiteralPath 'ESDS/elderly-companion-agent/specs/027-baseline-data/git-save-paths.txt'
$cbtSavePaths
# 先核对这些逐文件路径对应的累计修改归属
git add -- $cbtSavePaths
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "保存当前A基座baseline数据与已知失败"
git tag -a baseline/A-20261024-027 -m "run 20261024-100022-A-baseline-verified-source-64bcab；E03失败，非质量验收"
git log -1 --oneline
```

指定清单见[git-save-paths.txt](git-save-paths.txt)，包括既有累计代码/删除/新文件，须核对，不用git add .。新标签如已存在换唯一名称，不覆盖旧标签。提交后再记录实际commit/run_id关系；后补报告意味着提交不与采集zip逐字节相等。

原始run目录、源码快照、根docs被忽略，需另外备份，Git不会保存它们。至少备份本次preflight和完整run；023/024/025旧证据照存。未解决事项：E03混写/返回失败、E04复合确认、E06-b教学材料污染目标、目标长段/固定末问、整课/页面/跨课及用户反馈。
