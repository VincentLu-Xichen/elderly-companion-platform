# E07最小修复与前后对照

> 2026-10-23 API来源更正：用户发现费用记入旧账户。当前进程继承的DeepSeek密钥与模块.env不同，旧运行器load_dotenv默认不覆盖继承值；历史记录未保存凭据来源，不能仅凭模型名确认账户。本文原始输出/usage照存，但不能认定为指定新API账户的合格基线。用户已确认以后以模块.env为准，026已修评测入口并完成零请求离线核对；没有重采。详见[026来源修复](../026-eval-api-source/report.md)。

2026-10-23。第二课 **6.2-contrast-reply** 已保留对照后的模型承接；253项离线回归通过，同一旧JSON回放证明只改变展示，3次成功的真实模型检查均保留承接。当前为局部结果，R-010／本切片 **Validating**，等待用户体验。没有启动新网站或改动旧服务；原预览不自动加载本版。第一课仍7.5，前端、Daily Chat、API配置和用户数据库未改，没有commit/tag/push。

## 证据身份与问题定位

023基线 `20261023-221700-baseline-022-27128e` 的manifest、requests、results及source.zip均在本机。249个原快照文件逐一核对：仅根AGENTS、模块AGENTS、模块README、023/tasks四份后续说明变化；课程/网页源码与案例一致，压缩包哈希一致。修改前冻结 `20261023-E07-prechange-3415fb`，源码总指纹 `204d416ea941a5b44e32992409a8ceef4d5490f994c460bc6e22ca66f053edbb`；另存实际未提交diff及Git状态。仍为harrison／0cc68ed加累计修改，不能把HEAD当实验版本。

本轮直接核对E07原始JSON：intent=answer、observations=[]、interaction=null；没有接口失败或来源拒绝。`lesson2_flow._reply_after_observations` 原代码在contrast分支先推进rain_insight，再用 `question(state)` 替换reply。因此该轮是明确的**程序覆盖**。E04复合确认和E06-b目标串入材料仍留在023，未在本切片修复或重新作因果诊断。

## 改了什么、为何这样改

旧版：模型生成承接 → Schema/来源校验 → 推进到回看对照 → 固定问题覆盖承接。

新版：模型生成承接 → 相同校验 → 相同推进 → **保留承接，再接原有问题**。

产品代码只改回复组合一行，以及catalog第二课版本号。已有Prompt明确要求“reply只承接本轮、不提下一问题，程序追加下一问题”，因此这次无需改Prompt、加Actor或换模型。暂停、帮助、继续、来源失败和本人确认仍走既有分支。版本号用于区分旧/新行为，服务端旧6.1只读；无数据迁移、无删除。

这是针对已定位问题的局部责任修正，不是任务分块、多Agent或模型路由实验。唯一主要变量为contrast普通回答的最终回复组合；新旧原例真实请求的messages和parameters也逐项相等。

## 相同输入的可回看对照

预设输入（原 `cbt12-local/1` E07-a，未改）：

> 我发现小雨心态比我好，我是不是想得太糟糕了？

023真实模型JSON的reply（完整）：

> 同一场雨里，您想到“安排泡汤了”、感到失望；小雨想到“可以做其他事情”、感到平静。这是两种并行存在的解释，对照是用来帮我们看清想法和情绪如何相扣，不是给谁的心态打分。您问是不是想得太糟糕了，这份怀疑本身就值得留意，先按原样放着，不用急着评判。

旧版最终展示（完整）：

> 看完对照，您注意到什么联系或不同？没有新发现、不同意也可以直接继续。

同一旧JSON回放新版：最终展示为上面**完整模型reply＋换行＋完整旧版问题**。没有重新生成或编辑模型文字。回放同时验证请求、参数与完整输出状态相等，旧代码重现了023最终回复。两个回放run为 `20261023-223514-E07-replay-db4fd0` 与格式整理后的 `20261023-223953-E07-replay-6d80d9`，API均0次。后者 `comparison.json` 可查看输入、旧原始JSON、新旧完整状态与trace。回放保持原6.1状态只为隔离展示变量，不写应用数据库，也不证明旧会话可在新版服务继续。

新版重新真实调用 `20261023-223740-E07-candidate-network-28dc10` 的完整模型reply：

> 不是谁“想得太糟糕”的问题。这里的小雨是教学示范，她的平静用于对照，不是拿来给你打分的标准。你刚才的“安排泡汤了、失望”已经被作为你想象情境中的想法和感受记录下来。看到不同解释后，产生“我是不是更糟”的念头也很常见。

最终展示逐字保留该段，再追加上述回看问题。第二次原例 `20261023-223837-E07-repeat-7f4f3f` 的模型reply：

> 你在拿自己和小雨的解读作比较。这个对照是用来看清同一场雨里不同想法和情绪的，不是评分，也没有哪种情绪更正确；所以不需要判断谁的心态更好或谁的更糟。

最终同样完整保留并接回看问题。三个原例版本最终均为 `stage=learn, step=rain_insight, draft_record={}, confirmed_record=null, completed=false`；想象练习与小雨材料保持独立来源，不因回答表达得好就标记掌握。

## 新表达与失败照实保留

版本化变体文件 [`cases.e07-variants.v1.json`](../../evals/cbt/cases.e07-variants.v1.json) 在实现完成后冻结，复用原second-contrast起点，评判要求不传入教学模型；不是独立盲测集。

实际只执行E07-v1：

> 可我就是很期待这次出游，取消了当然会失望。我不想硬学小雨那么乐观，这样也可以吗？

`20261023-223855-E07-variant-d8c22e` 的完整模型reply：

> 当然可以。你的失望来自你确实很期待这次出游，这和你自己的体验是连着的；小雨的平静只是另一种解释方式，不是要你照着变成乐观。这里只是把两种想法和感受并排看看，没有哪种情绪需要被改掉。

最终完整保留并追加回看问题，未填个人三栏。该回复能回应“不想硬学乐观”，但“你自己的体验”对想象练习的来源标注仍不如原例明确，这是措辞限制，不据此声称所有来源表述已完美。

首个真实尝试 `20261023-223610-E07-candidate-2c6c84` 在384ms请求等待后RuntimeError，整轮386ms，无模型输出/usage。记录只保存异常类别；随后无密钥公开连接诊断得到PermissionError／WinError 10013，支持沙箱网络受限的判断，不能把未保存的原始异常详情说成已读。工具放行后才完成余下请求。该失败计入4次总额，因此E07-v2未执行，没有增加预算。没有自动重试，网络放行后的重新运行有独立run_id。

## 验证、成本与取舍

| 层次 | 实际结果 | 限制 |
| --- | --- | --- |
| 离线工程 | 253项通过：原246项行为/集成回归＋023的3项运行器检查＋本次4项。公共45项4.681秒，课程208项7.455秒 | 工程约束不等于对话质量 |
| 确定性回放 | 旧JSON、新旧完整请求及状态相等，旧展示精确复现，新展示保留全部reply | 旧模型样本回放，不是新增模型证据 |
| 有限真实模型 | 3成功、1失败；成功的2次原例及1次变体均保留完整reply，来源/未确认检查通过 | 非整课、非页面、非真实参与者 |
| Coding Agent文字审阅 | 原例理解承接：更好；教学方向：相当；衔接：更好但仍有固定问题。理由是用户疑问现在先获回应，且没有改变任务 | 非用户盲评；两次原例不证明统计稳定性。变体无旧版真实配对，语义优劣不能独立归因 |

保留这次修复：同一原始JSON回放给出明确的覆盖因果证据，改动极小且未改变状态规则。继续保留“固定末问仍可能机械”“模型措辞可能过强”及E04/E06-b问题，不扩大到其他阶段。

| 本轮尝试 | 输入tokens | 输出tokens | 整轮等待ms |
| --- | ---: | ---: | ---: |
| 首次网络失败 | 未知 | 未知 | 386 |
| 原例成功 | 2794 | 111 | 1891 |
| 原例重复 | 2794 | 87 | 1751 |
| E07-v1 | 2803 | 99 | 1803 |
| 已知合计 | 8391 | 297 | 5831 |

总计4次尝试，已知8,688 tokens；失败usage未知，总消费不以0代替未知。模型均为deepseek-flash，temperature=1.0、输出上限1200、任务反思none，事件Reflexion机制保留，本次未触发。未更改模型配置。非流式采集，首字等待未知；费用未知，无可核实逐请求计费细项。023原例是2,912 tokens／2,959ms；不能用这几个单次样本声称系统提速或省钱。回放没有新模型消费。

工程过程保留的失败：新增定向测试曾误把下一步文案预期写为“自动思维”，改为实际三栏教学文案；全回归曾有一个写死6.1的断言，改为当前版本常量，并增加6.1旧课只读检查。首次沙箱回归长时间无输出后停止，未把它算通过。最终隔离回归日志在 `test-results/dialogue-evals/024-regression-final.log`。venv没有Black/Ruff，系统Black执行受环境阻碍后停止；使用系统Ruff完成新增文件格式与静态检查，不安装依赖或改运行配置。

## 按这次请求理解代码

1. [`run_dialogue_eval.py`](../../scripts/run_dialogue_eval.py) 从固定案例构造雨天想象记录和已展示的小雨对照；只把实际历史及本轮输入交给runtime。评分标准保存在评测端。
2. [`runtime.py`](../../cbt_course_llm_freeform/runtime.py) 复制状态并分派到第二课流程，沿用暂停、互动反馈等入口；本轮没有候选互动事件，进入教学调用。
3. [`lesson2_flow.py`](../../cbt_course_llm_freeform/lesson2_flow.py) 的process用当前step、允许字段与最近24条历史调用 `agent.lesson2_turn`。本请求只产生一次DeepSeek JSON调用，模型返回reply、intent=answer、observations=[]。
4. Schema及 `_apply_observations` 先检查结构与来源；空摘录意味着没有新三栏事实。`_reply_after_observations` 只将contrast推进到rain_insight；本次改动在这里保留reply并接下一问。
5. runtime返回reply、状态、trace和页面payload。评测器将原请求/JSON和最终回复分别保存。网站服务另有加密、幂等及审计层，本次局部采集没有调用该数据库层；相关集成回归通过不能代替真人网页体验。

自动思维讲解、三栏、课末Reflexion及跨课记忆未改。定向回归验证继续按钮仍可到personal，既有回归覆盖两课离线路径；没有执行两张整课卡或新页面验收。

## 复现入口与Git保存

在模块目录：

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts\run_dialogue_eval.py
.venv\Scripts\python.exe -X utf8 -B scripts\check_contrast_replay.py
.venv\Scripts\python.exe -X utf8 -B scripts\run_regression.py
```

回放需要单独备份023原始目录；缺失会失败，不自动造数据。新API调用应另列预算，本轮4次已用完。变体运行复用原运行器，将其SUITE指向 `evals/cbt/cases.e07-variants.v1.json`，不暗改原cases.v1。

本切片产品改动为catalog.py、lesson2_flow.py；测试为新增test_contrast_reply.py、同步test_freeform.py和test_lesson2_blueprint.py；新增回放脚本、变体案例、024规格/报告/Git路径清单，以及模块README/AGENTS恢复说明。根ROADMAP/IDEAS更新被忽略，不会进入提交。

目前有多轮未提交依赖，**只提交024文件不足以重现当前版本**。拟保存范围是之前累计两课实现/清理、评测素材，加上024；逐文件候选清单见 [`git-save-paths.txt`](git-save-paths.txt)。它列出本次检查时root AGENTS及模块内全部未提交文件（含删除项），不包含根docs、原始运行、数据库、密钥、老师原稿。请先审阅归属；这不是自动批准提交。

在工作区根目录逐步执行（本轮均未执行暂存、提交、标签或推送）：

```powershell
git status --short
git diff --stat
git diff -- ESDS/elderly-companion-agent/cbt_course_llm_freeform/catalog.py
$cbtSavePaths = Get-Content -LiteralPath 'ESDS/elderly-companion-agent/specs/024-lesson2-contrast-reply/git-save-paths.txt'
$cbtSavePaths
# 审阅逐文件范围及累计修改后，再暂存这些指定路径
git add -- $cbtSavePaths
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "保存前两课基线并保留第二课对照回应"
git tag -a experiment/e07-reply-20261023-024 -m "E07局部验证；原例run 20261023-223740-E07-candidate-network-28dc10；待用户体验"
git log -1 --oneline
```

该标签名本次核查尚未使用；执行前如已存在请换新名称，不覆盖。提交后再记录实际commit与上列run_id的关系；后补文档意味着提交不与采集时source.zip逐字节相同。未解决：E04/E06-b、其他第二课覆盖点、整课及网页体验、用户验收。原始合成运行、源码快照和根docs需另行备份，Git不会保存忽略目录。
