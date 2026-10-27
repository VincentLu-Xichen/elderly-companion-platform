# 030 Git保存指导（未执行）

当前harrison，HEAD仍9469acb90ca4e33f8f8189dcb7e3a961a8c9e59a。此前028/029和本轮030均有未提交工作。下面是**累计检查点**候选范围，先看归属与差异，不把旧HEAD标为任何脏工作区实验版本。

本轮主要文件：learning_request.py、runtime.py、schemas.py、agent.py、lesson_1.py、catalog.py、新回归/运行器、scoped-requests固定卡、030规格和报告，以及恢复入口/评测README。prompt.py和test_freeform.py的在途更改来自029；028/029资料与工具一并列出供核对。本轮没有修改它们的历史结果。

未解决：最终版本无完整真实四轮通过、有限重复/未见变体/本次正常评分/D02真实验证缺失；网站/刷新/整课及其他E03等历史问题继续保留。原始运行目录已另备份，根docs/源快照/原始输出Git忽略，不能说Git会保存它们。

本轮实验目录：`20261024-030-scoped-requests`；12真实请求的完整run_id见[费用登记](usage-ledger.md)，最终版0新增真实run。后续实际commit完成后，才把实际hash登记到result.v1.json及原始目录；当前不预填commit。

## 拟暂存文件（累计）

- `AGENTS.md`
- `ESDS/elderly-companion-agent/AGENTS.md`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/agent.py`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/catalog.py`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/learning_request.py`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/lesson_1.py`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/prompt.py`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/runtime.py`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/schemas.py`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/tests/test_freeform.py`
- `ESDS/elderly-companion-agent/cbt_course_llm_freeform/tests/test_learning_request.py`
- `ESDS/elderly-companion-agent/evals/cbt/README.md`
- `ESDS/elderly-companion-agent/evals/cbt/a1-distress-card.v1.md`
- `ESDS/elderly-companion-agent/evals/cbt/case-review.v2.md`
- `ESDS/elderly-companion-agent/evals/cbt/cases.a1-distress.v1.json`
- `ESDS/elderly-companion-agent/evals/cbt/cases.a1-responsive.v1.json`
- `ESDS/elderly-companion-agent/evals/cbt/cases.a1-style.v1.json`
- `ESDS/elderly-companion-agent/evals/cbt/cases.scoped-requests.v1.json`
- `ESDS/elderly-companion-agent/scripts/run_a1_distress_eval.py`
- `ESDS/elderly-companion-agent/scripts/run_a1_style_eval.py`
- `ESDS/elderly-companion-agent/scripts/run_scoped_request_eval.py`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-report.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-result.v1.json`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-transcripts.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-usage-ledger.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/experiment-result.v1.json`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/git-save.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/plan.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/report.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/spec.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/tasks.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/transcripts.md`
- `ESDS/elderly-companion-agent/specs/028-a1-prompt-style/usage-ledger.md`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/git-save.md`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/implementation-result.v1.json`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/live-report.md`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/live-result.v1.json`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/plan.md`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/report.md`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/spec.md`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/tasks.md`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/transcripts.md`
- `ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/usage-ledger.md`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/conversation.md`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/git-save.md`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/plan.md`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/report.md`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/result.v1.json`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/spec.md`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/tasks.md`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/transcripts.md`
- `ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/usage-ledger.md`
- `ESDS/elderly-companion-agent/tests/test_a1_style_eval.py`
- `ESDS/elderly-companion-agent/tests/test_responsive_eval.py`
- `ESDS/elderly-companion-agent/tests/test_scoped_request_eval.py`

## 核对、暂存、检查、提交、唯一tag

以下由用户决定保存时执行；本轮没有执行add/commit/tag/push。命令从工作区根目录运行。

```powershell
git status --short
git diff --stat
git diff -- AGENTS.md ESDS/elderly-companion-agent/AGENTS.md ESDS/elderly-companion-agent/cbt_course_llm_freeform
git ls-files --others --exclude-standard
```

审阅新文件后逐一指定路径（不用git add .）：

```powershell
git add -- "AGENTS.md"
git add -- "ESDS/elderly-companion-agent/AGENTS.md"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/agent.py"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/catalog.py"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/learning_request.py"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/lesson_1.py"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/prompt.py"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/runtime.py"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/schemas.py"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/tests/test_freeform.py"
git add -- "ESDS/elderly-companion-agent/cbt_course_llm_freeform/tests/test_learning_request.py"
git add -- "ESDS/elderly-companion-agent/evals/cbt/README.md"
git add -- "ESDS/elderly-companion-agent/evals/cbt/a1-distress-card.v1.md"
git add -- "ESDS/elderly-companion-agent/evals/cbt/case-review.v2.md"
git add -- "ESDS/elderly-companion-agent/evals/cbt/cases.a1-distress.v1.json"
git add -- "ESDS/elderly-companion-agent/evals/cbt/cases.a1-responsive.v1.json"
git add -- "ESDS/elderly-companion-agent/evals/cbt/cases.a1-style.v1.json"
git add -- "ESDS/elderly-companion-agent/evals/cbt/cases.scoped-requests.v1.json"
git add -- "ESDS/elderly-companion-agent/scripts/run_a1_distress_eval.py"
git add -- "ESDS/elderly-companion-agent/scripts/run_a1_style_eval.py"
git add -- "ESDS/elderly-companion-agent/scripts/run_scoped_request_eval.py"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-report.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-result.v1.json"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-transcripts.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/distress-usage-ledger.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/experiment-result.v1.json"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/git-save.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/plan.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/report.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/spec.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/tasks.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/transcripts.md"
git add -- "ESDS/elderly-companion-agent/specs/028-a1-prompt-style/usage-ledger.md"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/git-save.md"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/implementation-result.v1.json"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/live-report.md"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/live-result.v1.json"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/plan.md"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/report.md"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/spec.md"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/tasks.md"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/transcripts.md"
git add -- "ESDS/elderly-companion-agent/specs/029-responsive-single-prompt/usage-ledger.md"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/conversation.md"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/git-save.md"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/plan.md"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/report.md"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/result.v1.json"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/spec.md"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/tasks.md"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/transcripts.md"
git add -- "ESDS/elderly-companion-agent/specs/030-scoped-learning-requests/usage-ledger.md"
git add -- "ESDS/elderly-companion-agent/tests/test_a1_style_eval.py"
git add -- "ESDS/elderly-companion-agent/tests/test_responsive_eval.py"
git add -- "ESDS/elderly-companion-agent/tests/test_scoped_request_eval.py"
git diff --cached --stat
git diff --cached --check
git diff --cached
git status --short
git commit -m "checkpoint(cbt): preserve A evidence and scoped learning requests"
git tag cbt-a-030-20261024-7.8.5-396579
```

tag仅为已检查未占用的提议，不移动旧标签，不自动push。原始合成证据包另行备份；不要add忽略目录、.env、用户库或老师原稿。