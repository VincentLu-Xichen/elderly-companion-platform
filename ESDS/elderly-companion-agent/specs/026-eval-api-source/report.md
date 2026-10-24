# 评测继承旧API凭据：原因、修复与限制

2026-10-23。用户发现评测费用记入旧API账户，并明确指定以后以模块`ESDS/elderly-companion-agent/.env`为准。已修复评测入口的配置优先级，**本轮模型请求0次，没有重采或新增模型费用**。没有修改.env内容、产品客户端、现有服务、课程Prompt或数据库；未提交Git。

## 实际核对

- 当前进程继承了DEEPSEEK_API_KEY，与模块.env中的值不同；核对只输出相同/不同，不输出密钥、前后缀或指纹。
- 旧运行器调用load_dotenv但不覆盖已有环境变量，客户端随后从os.environ取key；因此文件中的更新可被旧进程凭据遮蔽。旧--provider默认deepseek还会覆盖文件中的提供商选择。
- 023/024/025记录的提供商与模型均为deepseek/deepseek-flash，代码发送到DeepSeek官方chat/completions地址；这些记录不能证明用了哪个账户。当前差异与用户所见扣费方向相符，但旧manifest没有凭据来源/可验证账户身份，不能声称已追溯每次历史调用的确切账户。

此前只核对提供商和模型、未核对凭据来源，未能及时发现该问题。旧输出及usage是实际返回，仍作历史证据；025不能据此认定为用户指定新API账户的合格基线。保留失败及旧目录，不改写原始manifest或静默重跑。所有费用以用户账单为准，本地没有确切金额。

## 改了什么

`scripts/run_dialogue_eval.py`新增configure_eval_environment：只从显式配置文件解析客户端相关变量。默认路径是模块.env；--env-file可明确选择其他路径。程序只在本次评测子进程中采用文件中的密钥/模型/endpoint等配置，不修改文件或宿主环境。未选提供商的无关配置与应用设置不整体加载。

省略--provider时以文件为准；显式--provider必须与文件一致，否则联网前报错。密钥/模型/部署缺失时不回退继承值；相关配置的环境插值被拒绝，避免间接读入旧密钥。文件中缺失的可选API设置也会清除对应继承值，防止沿用旧Azure部署/API版本。

后续manifest的api_configuration只保存配置文件路径、来源、提供商及冲突变量名，**不保存密钥及其指纹**。它证明配置选择流程，仍不等于服务商账单账户核验。

## 验证

| 检查 | 结果 |
| --- | --- |
| 实际模块配置，不发请求 | 客户端密钥与文件相同，文件字节未改，network_requests=0 |
| 4项新增离线回归 | 文件覆盖旧key/model；缺少配置不回退；提供商冲突/环境插值先拒绝；可选Azure旧设置不泄入 |
| 完整离线回归 | 公共49＋课程208＝257项通过，分别4.886秒／7.439秒 |
| 默认评测入口 | 6个起点检查通过，api_calls=0 |
| 格式/静态 | 两个修改文件Ruff检查通过 |

首轮定向测试被沙箱临时目录写入权限阻止，未当作实现失败或测试通过；放行隔离本地回归后全部通过。测试只用虚构密钥并隔离数据库；真实配置检查仅创建客户端，不调用complete/stream。

日志：`test-results/dialogue-evals/026-regression.log`。实际零请求核对及最终源码快照在同目录下026交付目录，原始运行目录仍忽略。

## 对实验计划的影响

R-010方向及B/C/D设计保留；先修复API来源是025采集的前置纠正。023/024/025证据追加来源限制，不把旧结果删掉或冒充新账户结果。正确来源的A重采需另列调用预算，本轮不执行。常驻网页进程没有重启，也未验证其凭据来源；不能把本次评测脚本修复说成所有旧服务已切换。

## Git保存

本次功能变更只有`run_dialogue_eval.py`与`tests/test_dialogue_eval.py`；另增026规格/报告、给023/024/025报告补来源说明、025契约加验证状态、更新恢复入口和产品资料。旧源码已在025的A0/交付快照中保留，不能仅按HEAD比较本次变化。

当前仍有大量累计未提交依赖。先核对[逐文件候选清单](git-save-paths.txt)归属，再从工作区根目录执行；这些命令本轮未执行：

```powershell
git status --short
git diff --stat
$cbtSavePaths = Get-Content -LiteralPath 'ESDS/elderly-companion-agent/specs/026-eval-api-source/git-save-paths.txt'
$cbtSavePaths
git add -- $cbtSavePaths
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "保存前两课实验基线并修复评测API配置来源"
git tag -a experiment/api-source-20261023-026 -m "026零模型请求；历史A0凭据来源待核实"
git log -1 --oneline
```

新标签执行前如已存在须换名称，不能覆盖旧基线；源代码、合成报告可进Git，根docs和原始运行须另行备份。提交后再记录实际commit与025历史run及026零请求修复的关系。
