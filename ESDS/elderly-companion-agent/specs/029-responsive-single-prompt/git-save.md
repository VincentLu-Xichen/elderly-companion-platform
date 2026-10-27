# Git保存范围：028证据＋029主Prompt与真实结果（未执行）

当前分支harrison、HEAD9469acb。028资料仍有22条未提交路径，029累计新增16条课程/测试/规格/真实汇报路径，共38条；根/module AGENTS、eval README和未跟踪运行器含跨轮工作。以下为核对过的累计检查点，不能把整个文件都冒称只有029改动。根docs/密钥/数据库/原始运行目录继续忽略，不使用git add .。

当前第一课7.7工作候选、第二课6.2，262项离线检查通过。029真实5/12请求、29,304 tokens、10.224秒，1轮正式成功4轮失败；首轮局部改善，完整多轮未取得，余量7次已关闭。尚未解决暂停动作协议，以及原有R03/R05/E03/E04和目标材料问题，不将标签称为已验收基线。

029实际run_id：

- `20261024-114620-A1-D01-before-t1-3a9e7a`
- `20261024-114627-A1-D01-after-t1-a483be`
- `20261024-114653-A1-D01-after-t2-8fb3ac`
- `20261024-114751-A1-D02-before-t1-7bedc8`
- `20261024-114800-A1-D02-after-t1-d2c4e9`

028六个历史run继续见028报告，不能改标成7.7。实际源码身份以各run快照/Prompt哈希为准，HEAD不包含当前未提交改动。原始数据与源码快照另行备份，Git不会携带。

以下在工作区根逐步执行并检查；本轮未执行add/commit/tag/push：

```powershell
git status --short
git diff --stat
$savePaths = @(
    'AGENTS.md'
    'ESDS/elderly-companion-agent/AGENTS.md'
    'ESDS/elderly-companion-agent/evals/cbt/README.md'
    'ESDS/elderly-companion-agent/evals/cbt/case-review.v2.md'
    'ESDS/elderly-companion-agent/evals/cbt/cases.a1-style.v1.json'
    'ESDS/elderly-companion-agent/evals/cbt/a1-distress-card.v1.md'
    'ESDS/elderly-companion-agent/evals/cbt/cases.a1-distress.v1.json'
    'ESDS/elderly-companion-agent/scripts/run_a1_style_eval.py'
    'ESDS/elderly-companion-agent/scripts/run_a1_distress_eval.py'
    'ESDS/elderly-companion-agent/tests/test_a1_style_eval.py'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/spec.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/plan.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/tasks.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/report.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/transcripts.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/usage-ledger.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/experiment-result.v1.json'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/git-save.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-report.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-transcripts.md'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-result.v1.json'
    'ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-usage-ledger.md'
    'ESDS/elderly-companion-agent/cbt_course_llm_freeform/catalog.py'
    'ESDS/elderly-companion-agent/cbt_course_llm_freeform/lesson_1.py'
    'ESDS/elderly-companion-agent/cbt_course_llm_freeform/prompt.py'
    'ESDS/elderly-companion-agent/cbt_course_llm_freeform/tests/test_freeform.py'
    'ESDS/elderly-companion-agent/evals/cbt/cases.a1-responsive.v1.json'
    'ESDS/elderly-companion-agent/tests/test_responsive_eval.py'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/spec.md'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/plan.md'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/tasks.md'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/report.md'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/implementation-result.v1.json'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/git-save.md'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/live-report.md'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/live-result.v1.json'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/transcripts.md'
    'ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/usage-ledger.md'
)
git add -- $savePaths
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m '保存A1对照证据与第一课回应Prompt及失败分析'
git tag --list experiment/lesson1-responsive-20261024-029
# 确认同名标签不存在再执行；存在则另选唯一名称，不移动旧基线标签。
git tag -a experiment/lesson1-responsive-20261024-029 -m '第一课7.7，262离线检查，5请求真实对照含4失败，基座仍Validating，原始证据另备份'
git log -1 --oneline
```

未自动提交或推送。以后保存后记录实际commit与以上run的关系；若提交还包括采集后报告，只能说教学实现一致，不能冒称提交内容与原快照逐字节相同。原始目录仍需单独备份。

已另存本机`test-results/dialogue-evals/20261024-029-responsive-pair-0bd924-live-evidence.zip`，SHA256 `fa4e7c7d3fd887243e099a922cf558f0be60ac41ac1d9507cfe1fb3ff90cfc5c`；含五个真实run、修改前/候选源码及诊断/回归。包仍被Git忽略且未上传，不由上述add携带；此前028与029离线备份不覆盖。
