# 031 Git保存指导

未执行add／commit／tag／push。当前分支harrison，HEAD为9469acb，工作区已有大量此前修改；本轮不是干净HEAD上的独立补丁。

建议先检查[本轮逐文件差异](../../test-results/dialogue-evals/20261026-031-dialogue-implementation-135600/round-source.diff)及[本轮清单](git-save-paths.txt)，再决定是否把所选文件的累计修改一并保存。清单包含本轮改过的文件；其中learning_request.py及其旧测试等仍带此前030未提交内容。不能把整个工作区status都解释为031。

run_id：`20261026-031-dialogue-implementation-135600`。第一课7.9／第二课6.2；306项离线检查和原4份JSON回放通过，新真实调用0；新模型体验尚未验收，R-010仍Validating，已知范围差异和其他历史问题保留。

在仓库根目录逐步执行并审阅：

```sh
git status --short
git diff --stat
git diff -- ESDS/elderly-companion-agent/cbt_course_llm_freeform
git diff --cached --stat
```

确认原暂存区没有无关内容后，使用指定路径清单暂存（不执行git add .）：

```sh
git add --pathspec-from-file=ESDS/elderly-companion-agent/specs/031-lesson1-dialogue-ownership/git-save-paths.txt
git diff --cached --stat
git diff --cached --check
git diff --cached
```

确认只包含想保存的累计内容后，可选提交说明：

```sh
git commit -m "feat(cbt): preserve model dialogue and sourced lesson return"
git tag -l 'cbt-l1-7.9-dialogue-20261026-031'
```

只有确认上述标签尚不存在，才创建本次唯一标签：

```sh
git tag -a cbt-l1-7.9-dialogue-20261026-031 -m "031 offline verified; live quality validating"
```

以上是保存指导，不是提交／推送已获执行的记录。需要远端保存时再明确决定推送分支与标签。

`test-results`和根`docs`仍被Git忽略。异机复现还需另备份整个run目录（含原／新源码zip、manifest、回归日志、原JSON回放、逐文件diff及docs副本）以及原观察run `20261026-123741-phone-observation-v1-bd81a2`；不要把.env或真实数据库放进源码备份。根docs尚无Git跟踪，按现状本机备份，不擅自强制加入Git。
