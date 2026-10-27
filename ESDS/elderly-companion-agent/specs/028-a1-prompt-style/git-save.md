# 本轮实验记录的Git保存范围（未执行）

A1前检查点9469acb已按用户要求推送harrison。以下仅供之后保存本轮实验工具/报告；本轮没有执行这些命令。当前产品Prompt已恢复，提交名称不能写成风格优化成功。

已知问题：R03七分未采用、R05未暂留，以及此前E03/E04/E06-b保留。run_id：

- `20261024-110100-A1-before-f5dd09`
- `20261024-110142-A1-before-continue-160e3b`
- `20261024-110517-A1-after-bc45b6`
- `20261024-110609-A1-after-continue-9e184f`
- `20261024-112634-A1-D01-before-t1-da06ee`
- `20261024-112648-A1-D01-after-t1-cbc54a`

后续用户认为候选更礼貌且有意义，新增确认痛苦场景新旧版≤12请求；实际2次，两版首轮重复behavior而被程序拒绝，按卡停止，完整多轮未取得。候选归档、产品代码仍为原版；不能把Coding Agent最初“不采纳”写成用户最终否定。以上两组共六个原始run/各自共享预算/源码zip在忽略目录，分别另行备份；根docs仍忽略，不强制加入。拟暂存22条明确路径：

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
)
git add -- $savePaths
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m '记录A1风格与痛苦场景对照、用户反馈和失败'
git tag --list experiment/a1-style-20261024-028
# 确认没有同名标签后再执行下一条；存在则另选唯一名称，不能覆盖。
git tag -a experiment/a1-style-20261024-028 -m 'A1三例9请求及痛苦场景2请求，用户礼貌改善反馈与首轮失败分别保留，原始证据另备份'
git log -1 --oneline
```

commit/tag均未执行；此处不含自动push。用户以后明确要求推送时再执行。当前Git只保存先前检查点，不能声称已上传本轮忽略的原始证据。

痛苦场景原始目录已另备份为本机`test-results/dialogue-evals/20261024-A1-distress-pair-7f19c2-evidence.zip`，SHA256 `eeb0746b76e8bf4720dad5385af442563dc7e9286c3bc5b73ae6f678b2ae2809`。该包未上传，不能通过上述add携带；先前三例的独立证据包及哈希继续按原记录保留。
