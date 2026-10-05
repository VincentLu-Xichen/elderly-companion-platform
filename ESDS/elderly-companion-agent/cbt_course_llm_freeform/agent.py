from __future__ import annotations

import os
from typing import Any

from cbt_course_llm_freeform.azure_chat_client import AzureChatCompletionsClient
from daily_agent.dashscope_chat_client import DashScopeChatCompletionsClient
from cbt_course_llm_freeform.prompt import FREEFORM_SYSTEM_PROMPT
from cbt_course_llm_freeform.schemas import AgentResult


class FreeformCourseAgent:
    def __init__(
        self,
        *,
        client: Any | None = None,
        system_prompt: str = FREEFORM_SYSTEM_PROMPT,
        max_completion_tokens: int = 1200,
    ):
        self.client = client or self._client_from_env()
        self.system_prompt = system_prompt
        self.max_completion_tokens = max_completion_tokens

    @staticmethod
    def _client_from_env() -> Any:
        provider = os.getenv("CBT_COURSE_PROVIDER", "dashscope").strip().lower()
        if provider == "dashscope":
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                raise RuntimeError("DASHSCOPE_API_KEY is not set for CBT course.")
            return DashScopeChatCompletionsClient(
                api_key=api_key,
                model=os.getenv("CBT_COURSE_MODEL", "qwen-plus"),
                base_url=os.getenv(
                    "DASHSCOPE_CHAT_BASE_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                ),
            )
        if provider != "azure":
            raise RuntimeError("CBT_COURSE_PROVIDER must be dashscope or azure.")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_COURSE_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        if not endpoint or not api_key or not deployment:
            raise RuntimeError("Azure OpenAI CBT course configuration is incomplete.")
        return AzureChatCompletionsClient(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        )

    def reply(self, history: list[dict[str, str]]) -> AgentResult:
        messages = [{"role": "system", "content": self.system_prompt}]
        for item in history:
            role = item.get("role")
            if role not in {"learner", "agent"}:
                continue
            content = str(item.get("content", "")).strip()
            if content:
                messages.append({"role": "user" if role == "learner" else "assistant", "content": content})
        completion = self.client.complete_with_metadata(
            messages,
            temperature=1.0,
            max_completion_tokens=self.max_completion_tokens,
        )
        reply = completion.text.strip()
        if not reply:
            raise RuntimeError("自由课程模型没有返回回复。")
        return AgentResult(reply=reply, completion=completion)
