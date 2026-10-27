# 033 Git保存指导

当前继承大量未提交修改；本轮差异请先看test-results/dialogue-evals/20261027-033-conversation-priority/implementation.diff，而非把HEAD以来全部修改当本轮。新增test_conversation_priority.py和033规格另看新文件。未自动暂存/提交/推送。

在根目录依次审阅：
```sh
git status --short
git diff --stat
git diff --cached --stat
git diff -- ESDS/elderly-companion-agent/cbt_course_llm_freeform
```
确认接受上述文件携带的累计改动后，才按清单暂存并检查：
```sh
git add --pathspec-from-file=ESDS/elderly-companion-agent/specs/033-conversation-priority/git-save-paths.txt
git diff --cached --check
git diff --cached --stat
git diff --cached
```
可选提交说明：fix(cbt): prioritize listening in the unified lesson prompt。候选唯一标签cbt-l1-7.9.2-conversation-20261027-033，先git tag -l查重；不要覆盖旧标签。原始run与根docs被忽略，复现还需另备份；报告和快照中不含.env/真实库/私有运行密钥。

证据：316项离线、原JSON回放、9次真实请求/9文字轮，本次原澄清句通过；恢复后重复评分及量尺口误仍未解决。R-010质量Validating，不以保存代码作为效果验收。
