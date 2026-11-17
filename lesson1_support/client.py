"""Same DeepSeek model/timeout as the original first-lesson provider factory."""
import os
from .deepseek import DeepSeekChatCompletionsClient

def client_from_env():
    if os.getenv('CBT_COURSE_PROVIDER')!='deepseek':raise RuntimeError('本独立包的真实模式使用DeepSeek。')
    key=os.getenv('DEEPSEEK_API_KEY')
    if not key:raise RuntimeError('请先在本包.env中配置DeepSeek密钥。')
    return DeepSeekChatCompletionsClient(api_key=key,model=os.getenv('CBT_COURSE_MODEL') or 'deepseek-flash',timeout=20)
