"""Azure client boundary for the freeform experiment."""

from cbt_course.azure_chat_client import AzureChatCompletionsClient as BaseAzureClient, ChatCompletionResult
from daily_agent.azure_chat_client import AzureChatCompletionsClient as DailyAzureClient


class AzureChatCompletionsClient(BaseAzureClient):
    # Reuse the existing SSE transport with the course client's verified TLS opener.
    stream_with_metadata = DailyAzureClient.stream_with_metadata

__all__ = ["AzureChatCompletionsClient", "ChatCompletionResult"]
