# 源码快照说明

- 打包日期：2026-09-01（Asia/Shanghai）
- `voice-gateway`：当前 ESDS 百炼 ASR/TTS、Agent Bridge、树莓派 ALSA 客户端源码快照。
- `elderly-companion-agent`：上游 `e05d4e9`（freeform CBT 第 1、2 课）与本地百炼 Daily Chat/树莓派 Voice Bridge 的合并工作树快照。
- Agent 工作树包含尚未提交到原上游仓库的集成修改，因此本包有意排除 `.git`；不能依赖一次普通 `git clone` 重建当前状态。
- 当前语音入口仍只调用 Daily Chat；CBT 和视觉没有接入语音链路。
- 原 `ESDS-Demo` 未包含，也没有在打包过程中修改。

排除：虚拟环境、Git 元数据、模型权重、工具运行时、缓存、日志、录音、真实 `.env`、API Key、数据库及加密密钥。

历史数据不属于源码包。若需要迁移树莓派对话数据库，必须另行使用安全渠道迁移数据库和对应加密密钥。
