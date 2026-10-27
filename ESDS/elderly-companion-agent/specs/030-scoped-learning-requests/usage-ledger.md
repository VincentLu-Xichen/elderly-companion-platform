# 030 调用、tokens和等待登记

新预算总上限12，实际12，已关闭；不沿用029余额。失败与辅助均计入；无自动重试。金额留待用户账单核对，未知不写0。

| run_id | 版本 | 请求 | 输入tokens | 输出tokens | 合计 | 整轮等待ms | 轮次/检查 |
|---|---|---:|---:|---:|---:|---:|---|
| 20261024-121208-030-A1-D01-t1-33e33d | 7.8-scoped-learning-requests | 1 | 6439 | 268 | 6707 | 2659 | success / True |
| 20261024-121225-030-A1-D01-t2-e6feb5 | 7.8-scoped-learning-requests | 1 | 6542 | 242 | 6784 | 2289 | success / True |
| 20261024-121241-030-A1-D01-t3-4e5969 | 7.8-scoped-learning-requests | 1 | 6727 | 384 | 7111 | 2814 | error / True |
| 20261024-121426-030-repair2-A1-D01-t1-f2c1c3 | 7.8.1-scoped-learning-requests | 1 | 6567 | 279 | 6846 | 2656 | success / True |
| 20261024-121441-030-repair2-A1-D01-t2-2f1a6c | 7.8.1-scoped-learning-requests | 1 | 6673 | 224 | 6897 | 2229 | error / False |
| 20261024-122433-030-repair3-A1-D01-t1-4aabc1 | 7.8.2-scoped-learning-requests | 1 | 6651 | 140 | 6791 | 1638 | success / False |
| 20261024-122616-030-repair4-A1-D01-t1-76cbeb | 7.8.3-scoped-learning-requests | 1 | 6651 | 137 | 6788 | 1647 | success / True |
| 20261024-122631-030-repair4-A1-D01-t2-6619de | 7.8.3-scoped-learning-requests | 1 | 6757 | 125 | 6882 | 1658 | success / True |
| 20261024-122646-030-repair4-A1-D01-t3-f126a9 | 7.8.3-scoped-learning-requests | 1 | 6934 | 171 | 7105 | 1882 | success / True |
| 20261024-122704-030-repair4-A1-D01-t4-ba1176 | 7.8.3-scoped-learning-requests | 2 | 4176 | 261 | 4437 | 2942 | success / False |
| 20261024-122901-030-repair5-A1-D01-t4-396579 | 7.8.4-scoped-learning-requests | 1 | 3617 | 242 | 3859 | 1745 | success / False |

合计：67734输入＋2473输出＝70207 tokens；整轮等待合计24.159秒，客户端请求等待合计24.076秒（彼此包含，不相加）。

所有12次提供商请求都返回；2轮程序异常，3轮程序虽成功但预定状态检查失败，6轮成功且全部程序检查通过。11条输入≠12次请求，停课失败曾触发一次原有case_review。

非流式，首字等待未知；费用未知，未取得逐请求缓存/账单价格分类。以上不是网站端到端等待，也不是速度/省tokens对照实验。最终7.8.5为0新增真实请求。

核实费用：________；账单日期/币种：________；备注：________。