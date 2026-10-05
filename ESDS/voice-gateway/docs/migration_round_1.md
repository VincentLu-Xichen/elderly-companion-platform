# 第一轮迁移记录

## 已迁移

- 音频特征、VAD、重采样、语音增强
- SenseVoice ASR
- 百炼 Qwen ASR
- emotion2vec 和多信号情绪融合
- Ollama 流式对话
- 百炼 Cherry TTS
- 百炼 Qwen Omni Realtime
- WebSocket 网关和半双工会话状态机
- 无摄像头浏览器音频客户端
- 模型评测脚本和核心单元测试

## 已删除

- Qwen-VL
- 一眼 / face-api
- JPEG 图像上传
- praise / yiyan / vision 控制事件
- 镜面 Canvas 动画
- 摄像头权限
- 夸夸视觉上下文和镜子专属人格

## 暂缓到第二轮

- 播放中语义打断
- thinking 阶段晚到语音
- 唤醒词与休眠状态
- DeepTalk、待办、主动话题
- 生产 TLS 部署模板
- 树莓派 ALSA 原生客户端或 systemd 服务

## 兼容性

设备协议暂时继续使用 `companion-audio/1`。第一轮的目标是先保持音频设备兼容；确认树莓派端行为后，再决定是否发布 `esds-audio/1`。
