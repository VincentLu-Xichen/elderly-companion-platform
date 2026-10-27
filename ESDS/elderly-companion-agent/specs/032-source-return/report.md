# 032 验证记录

用户授权：修正前两项；multi-intent detection后置。第一课7.9.1-source-return，第二课6.2不变。

## 改动
- 无pending邀请时，来源有效的decline_return不再报错，单独保存return_preference，invitation仍为null；有pending时保留原declined记录。主动恢复后清除本次暂不返回偏好，不更改评分、案例或本人确认。
- 来源问题按讨论的第一步处理：Prompt明确quote逐字取最新text，禁止改写、拼接和历史请求复用，解释字段与原文分开；继续交流可沿用状态而不重复提交旧请求。校验不放宽、不自动修复旧ID；内部错误区分ID错误和非当前原文。
- 不做多意图识别、不改互斥组合、邀请措辞或页面提示，不更改.env、provider、模型参数、第二课或真实数据库。

## 验证
课程253＋公共56＝309项通过，新增3个测试方法（含多分支）；freeform源码compileall通过。原T06真实JSON所产生的意图记录回放保持pending邀请；另一个明确标为合成的无邀请拒绝分支通过。回放为状态层，不是整段真实模型网页测试。
初次公共测试7错误：本轮运行器误指定sqlite内存库，跨连接缺rate_limit_buckets；移除该覆盖后按测试自身独立临时文件库运行，56项通过，未修改业务测试来消除错误。

真实请求0；既有预算关闭，未重启服务、未修改真实库、未提交Git。当前页面尚未加载新版；版本升级后旧会话依现有规则只读，后续需使用新课程验证。

## 结论与限制
第二项明确程序规则冲突已被离线修正。第一项仅强化来源Prompt与诊断：用户两张截图对应的原始模型JSON未取得，不能确定是ID还是quote错误，更不能声称真实复现已修复。错误来源仍会被拒绝；新Prompt是否减少错误，需要另设请求预算进行真实验证。R-010保持Validating。

证据：test-results/dialogue-evals/20261027-032-source-return，包含前后快照、round.diff、manifest、两份回归日志、replay.json。无密钥或数据库入快照。

## Git保存指导
未执行暂存/提交/推送。先审阅git status --short、该run的round.diff及git diff；当前文件包含031/030等累计未提交修改，不宜将整份差异都称032。若决定保存，逐路径add上述3份实现、tests/test_source_return.py和specs/032-source-return；再git diff --cached --check并审阅cached。建议提交说明：fix(cbt): accept proactive return refusal and clarify source quotes；唯一候选标签cbt-l1-7.9.1-source-return-20261027-032，先查重再创建。原始test-results与根docs仍忽略，另行本机备份。


2026-10-27真实验证补充：run 20261027-032-live-cua，8请求均返回／49,998 tokens／16.038秒请求等待；8文字轮7成功1失败。原来源错误同句、无邀请暂不返回同句本次通过，但后者走listen，decline_return新分支仅离线覆盖。T07 conversation＋observations冲突失败保留；T08新输入主动继续成功，原案及评分暂留保留。余量4关闭，未重试或测试中改Prompt。R-010仍Validating。报告：reports/2026-10-27-lesson1/032真实网页验证/真实验证结果.txt。
