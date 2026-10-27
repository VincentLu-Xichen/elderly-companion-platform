# 034 Git保存指导
本轮未add/commit/tag/push。工作区继承032/033及此前大量未提交修改，不能按HEAD将全部改动当034；先读run的implementation.diff，新测试和本spec单列。

根目录审阅：git status --short；git diff --stat；git diff --cached --stat。确认愿意保存所选文件累计变化后：
```sh
git add --pathspec-from-file=ESDS/elderly-companion-agent/specs/034-deferred-rating-scale/git-save-paths.txt
git -c core.whitespace=cr-at-eol diff --cached --check
git diff --cached --stat
git diff --cached
```
确认范围后可选commit说明：fix(cbt): preserve deferred ratings on return and clarify scales。候选唯一tag：cbt-l1-7.9.3-rating-scale-20261027-034，先git tag -l查重，不覆盖旧标签。前后源码和原始run/根docs仍本机忽略，复现另备份，不含密钥或真实库。320项离线与8真实请求证据限本次场景，不代表全质量验收。
