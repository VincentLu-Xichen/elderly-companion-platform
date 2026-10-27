# 前两课可复用测试数据

最新人工体验准备（2026-10-26）：[第一课7.9逐轮测试数据](manual.lesson1-dialogue.v1.md)及[结构化输入](manual.lesson1-dialogue.v1.json)。保留原女儿未接电话4条输入，另有条件式倾诉／返回分支；人工逐条发送，没有自动批跑或新通过结果。

**030（2026-10-24）**：[局部请求固定卡](cases.scoped-requests.v1.json)与[四轮查看](../../specs/030-scoped-learning-requests/conversation.md)。新卡独立版本，不改原cases.v1/case-review.v2；运行器`scripts/run_scoped_request_eval.py`默认离线0API。12次真实预算已关闭，最终7.8.5只经277项离线和原JSON回放；前三轮真实成功、停课真实失败保留，不能称完整真实多轮通过。


最新029（2026-10-24）：第一课7.7主Prompt修订、262项离线检查后，用户确认D01多轮＋D02变体两版总≤12请求；实际5次/29,304 tokens/10.224秒，接口全返回、课程1成功4失败。7.7 D01首轮正式成功且不追分，第二轮及D02被not_feedback＋pause协议拒绝；完整多轮未取得，0API回放复现、余量7次关闭，不改Prompt挑输出。见[真实报告](../../specs/029-responsive-single-prompt/live-report.md)、[JSON/最终/状态全文](../../specs/029-responsive-single-prompt/transcripts.md)及[显式执行组](cases.a1-responsive.v1.json)。程序/模型/参数/第二课不变，7.7仍Validating；旧案例和失败不改。029使用显式suite/case和冻结Prompt目录，旧028默认仍会拒绝版本漂移，不自动重跑。

最新A1-D01（2026-10-24）：用户确认新增新旧版≤12请求，实际2次/11,258 tokens/3.776秒，两版均首轮重复behavior摘录被运行时拒绝，未形成成功最终回复。按[体验卡](a1-distress-card.v1.md)停止，后续未跑、0重试，余量关闭；0API原JSON回放已复现，未改Agent。见[场景结果](../../specs/028-a1-prompt-style/distress-report.md)、[真实JSON/状态](../../specs/028-a1-prompt-style/distress-transcripts.md)。此结果不抹去用户此前对候选礼貌改善的反馈；以下待确认/0新增均为此前时点。

后续用户反馈（2026-10-24）：用户看过028后认为候选更礼貌、值得继续观察。已整理[强烈难过的多轮体验卡A1-D01](a1-distress-card.v1.md)：最多3条用户输入，观察承接、暂不评分与自主继续/暂停；原34张卡不改。新卡尚未执行/接入运行器，新增配对12请求提议待确认，当前0新增请求；A1仍为归档候选，运行代码保持恢复后的原版。下文“不采纳”是首轮Coding Agent收束，不代替此后用户评价。

最新实测（2026-10-24，028）：按授权完成旧E01-a及当前审阅卡R03/R05的真实前后对照，共9/12请求、45,247 tokens、17.704秒后端轮次等待。语气改善证据不足，两版都存在七分未采用/本项未暂留；本轮不采纳候选并恢复原Prompt，260项离线检查通过。完整[报告](../../specs/028-a1-prompt-style/report.md)、[真实JSON/展示/状态](../../specs/028-a1-prompt-style/transcripts.md)、[费用登记](../../specs/028-a1-prompt-style/usage-ledger.md)；新增`run_a1_style_eval.py`默认离线、显式live，前后共享12次总预算。本次授权预算已收束，不自动重跑。

此前设计时点（2026-10-24，未执行描述为028试验前）：用户同意[前两课测试样本cbt12-review/2](case-review.v2.md)按当前设计收束，之后合适位置再显式修订：两条条件式正常路径、8组34张局部分支，输入/卡数不变。当时尚未运行或接入运行器，不更换默认cases.v1；[v1意见稿](case-review.v1.md)和旧输出保留。随后恢复[A1优化设计028](../../specs/028-a1-prompt-style/spec.md)，第一步只检验第一课主Prompt表达风格段，实测进展以顶部为准，不构成批跑授权。

## 最新当前baseline：027（2026-10-24）

原cases.v1未改，以026显式模块.env配置执行一次：`20261024-100022-A-baseline-verified-source-64bcab`。9请求均返回usage，原8轮有1轮程序拒绝，既定检查5/6；E03混写/来源失败照存。31,201 tokens/16.447秒，用户自行补账单金额，原始目录不含真实密钥。本轮无重试/追加采集，代码/Prompt未改；局部baseline质量有失败，不能称整课验收。见[027数据报告](../../specs/027-baseline-data/report.md)、[对话全文](../../specs/027-baseline-data/transcripts.md)、[逐请求登记](../../specs/027-baseline-data/usage-ledger.md)。023/024/025历史凭据限制继续保留，不覆盖旧目录。

## API来源更正（026，2026-10-23）

用户确认后续以模块.env为准。评测入口现在从该文件明确读取API配置，阻止继承旧密钥/模型/endpoint；省略--provider取文件值，显式值必须与文件一致。需要其他文件可用--env-file明确指定。缺配置或相关环境插值时联网前失败，不回退进程旧值。默认离线仍0请求。023/024/025历史输出保留，但历史扣费凭据未核实，不能当作指定新账户基线；本轮没有付费重采。见[026报告](../../specs/026-eval-api-source/report.md)。

## 最新A0与架构实验口径（025，2026-10-23）

用户确认A为单教学Agent／每课统一主Prompt体系，原辅助机制与状态提醒保留。当前原cases.v1已再次采集：`20261023-224936-A0-unified-teacher-baseline-fee03b`，6例8轮10成功请求，32,197 tokens/17.631秒，费用未知。不是自动按今天模型/Prompt重跑的指令，也不把程序6/6当体验全通过。后续B主管多Agent和C单Agent分块分别对A，D模型/参数后置，方案未执行。见[025实验卡](../../specs/025-agent-architecture-baseline/experiment-design.md)、[实际输出](../../specs/025-agent-architecture-baseline/transcripts.md)及[报告](../../specs/025-agent-architecture-baseline/report.md)。下方12请求说明是单次基线采集的上限，不构成无限重复授权。

目标是每次调整后能够回答：**同样的困难，哪里变好了，哪里退步了，付出了多少调用与等待？** 数据用于评测和回放，当前不用于微调模型。

## 三层材料，各有用途

| 层次 | 保存什么 | 什么时候用 |
| --- | --- | --- |
| 固定局部案例 | [`cases.v1.json`](cases.v1.json)：6个语义起点、8轮固定输入、程序约束、人工标准；起点构造在运行器内 | 每次局部修改前后运行相同案例；比较承接、推进、状态及成本 |
| 条件式整课体验 | [`full-course-cards.md`](full-course-cards.md)：人物事实、逐环节回答素材和异常分支 | 局部通过后由人完整体验；不要在Agent换了问题时硬塞下一句 |
| 现有工程回归 | `scripts/run_regression.py`及前端脚本 | 验证隔离、加密、幂等、来源、状态、协议等；不替代自然对话评价 |

初始局部组为E01-a一次表达、E03-a暂时偏题再返回、E04-a追问投诉、E06-a确定确认、E06-b目标承接、E07-a小雨对照。E02错字/纠正、E05三种拒绝范围、E08跨课边界继续在I-005及既有回归里；本轮没有假装已把它们都变成真实模型评测。完整体验卡已写好，但本轮没有运行整课。

方法借鉴[Anthropic的一手评测说明](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)：对话轨迹和真实结果分别看，程序检查与人工评价互补。6个案例、三层材料和本项目的检查项由当前问题选择，不是该资料规定的数量或标准。

## 怎么运行

在`ESDS/elderly-companion-agent`中先做不联网检查：

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts\run_dialogue_eval.py
```

真实模型需要本机`.env`中的配置；密钥不要贴到聊天或写进案例。运行器只向现有服务端模型客户端发请求，不打开网站、不修改课程、不读写用户数据库。初版真实采集固定`none`任务反思策略，**互动事件Reflexion仍然启用**；与其他策略比较时须另建实验，不混成相同条件。使用当前`CBT_COURSE_MODEL`，不替用户更换模型。

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts\run_dialogue_eval.py --live --provider deepseek --max-calls 12 --label baseline
```

只测单个场景：

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts\run_dialogue_eval.py --live --provider deepseek --case E07-a --max-calls 2 --label candidate-E07
```

`--max-calls`是实际请求尝试的上限，失败也计入；不是只限制成功次数。无自动重试。一个场景可能含教学、事件反思和案例回顾等多个调用，不能用轮数代替调用数。本轮授权只采集一次最多12请求的基线；后续批量重复、模拟用户或裁判模型要先明确范围与预算。默认不联网，不启动自动定时任务。

## 文件怎样保存

纯合成案例、运行器、规格、汇报及本目录的任务Prompt可纳入Git；根`docs/`想法管理仍保持忽略。

每次真实运行创建一个新的`test-results/dialogue-evals/<run_id>/`，不覆盖旧文件：

```text
manifest.json   Git HEAD/分支/脏状态、源码文件指纹、案例版本、配置与时间
source.zip      当时实际工作目录中的未忽略模块文件，含未提交和新文件；无.env/数据库
cases.json      本次所用案例副本，避免原案例后来改动丢失依据
requests.json   调用层输入、参数、原始JSON输出、请求ID、usage和失败类型
results.json    每轮实际最终回复、前后状态、页面数据、trace及人工评价空位
summary.json    调用/tokens/耗时与程序检查汇总，费用未知时留空
```

`requests.json`保存适配器收到的逻辑消息；提供商客户端可能继续转换请求格式，不能把它称作网络抓包。正常模式为非流式采集，耗时是后端完整轮次等待，不提供首字延迟，也不验证前端SSE体验。产品数据库的真实保存/恢复、跨课检索仍由现有集成回归和页面体验验证；本脚本不写数据库，不能据此宣称独立表写入已验证。

源码指纹包含实际未提交文件。当前HEAD仍是`0cc68ed`，不能仅用这个提交号表示当前两课版本。原始目录被现有规则Git忽略：需要带去另一台机器时，单独备份所需合成运行目录；Git不会携带这些本地原始证据。真实用户原文不要直接添加到此案例库，应先做去标识和授权判断。

## 怎样评价

- **程序检查**只检查声明过的结构事实，例如没有混入新案例、没有代确认、零分保留；不是质量总分。尤其E04的复合确认是否正确推进，需要读第二轮，不能仅看停问标记。
- **人工比较**逐例看理解承接、自然展开/收束、教学覆盖，给“更好／相当／更差／无法判断”，写具体轮次。单版本基线先标具体问题，不虚构A/B胜负。
- **检查原始输出和最终回复**：模型答得好但程序覆盖，和模型本来就误解，是不同原因。案例回顾等内部结构化结果不作为对用户展示的回复。
- **保留不确定性**：未调用是0次；调用失败缺usage是未知；未知费用不是0元。首次小样只用于定位问题，不能证明稳定改善、教学掌握或疗效。

改动前固定案例、模型、策略、历史和语义起点；每次主要只改一个变量。若新架构必须改起点适配器，保留原版并显式升版/说明语义等价性，不能悄悄改题让结果变好。局部初步改善后再做有限重复及未参与调试的变体；尚未冻结保留集，不宣称有独立泛化证据。

## 每次大调整的Git检查点

先完成验证和改动报告，再提示用户保存；未明确要求时Agent不执行commit/tag/push。若下一次开始大改而上一版还没保存，先提醒并保留源码快照，不能将旧HEAD当基线。当前已明确授权的工作不用反复请求功能开发许可。

1. Agent报告“改了什么、哪些文件属于本次、测试和人工体验状态”，列出拟暂存范围与未解决问题。
2. 用户先看`git status --short`、`git diff --stat`；本项目有多轮累计修改，范围核对后再暂存。下面示例中的模块路径会包含其累计修改，不能盲目执行。
3. 暂存后检查`git diff --cached --stat`、`git diff --cached --check`，确认没有密钥、数据库、原始材料和本地想法；提交后记录实际提交号，再给已验证基线加唯一标签。

当前版本的保存示例（在工作区根目录，**本轮未执行**）：

```powershell
git status --short
git diff --stat
# 核对下列范围确实是想保存的累计版本后再执行
git add -- AGENTS.md ESDS/elderly-companion-agent
git diff --cached --stat
git diff --cached --check
git commit -m "收束前两课后端并建立可复用对话评测"
git tag -a baseline/cbt12-20261023 -m "前两课局部对话基线，原始证据另见本机run_id"
git log -1 --oneline
```

已有同名标签不能覆盖；标签指向提交，不包含忽略目录。大调整后采用新的`experiment/<问题>-<日期序号>`标签，不重复挪动基线标签。提交后将commit与run_id关联；若这次提交还包含采集之后新增的评测文档，只能说产品实现一致，不能伪称它与旧源码快照逐字节相等。推送到`harrison`或远端标签需要另行明确要求，不自动上传。

完整后续委托Prompt见[`AGENT_PROMPT.md`](AGENT_PROMPT.md)；本轮基线分析与原始证据位置见[023报告](../../specs/023-reusable-dialogue-evals/report.md)。
