from __future__ import annotations

import os
import urllib.request
from typing import Any, Callable, Dict, Iterator, List, Optional

from daily_agent.agent_runtime import AgentTurnResult, complete_with_metadata_compat
from daily_agent.azure_chat_client import AzureChatCompletionsClient, ChatCompletionResult
from daily_agent.dashscope_chat_client import DashScopeChatCompletionsClient
from daily_agent.prompt import DAILY_CHAT_SYSTEM_PROMPT
from daily_agent.emotion_context import VoiceEmotionContext


class DailyChatAgent:
    """LLM-only daily companionship agent."""

    def __init__(
        self,
        *,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        deployment: Optional[str] = None,
        api_version: str = "2024-12-01-preview",
        opener: Callable = urllib.request.urlopen,
        client: Optional[Any] = None,
    ):
        if client:
            self.client = client
        elif endpoint and api_key and deployment:
            self.client = AzureChatCompletionsClient(
                endpoint=endpoint,
                api_key=api_key,
                deployment=deployment,
                api_version=api_version,
                opener=opener,
            )
        elif os.getenv("DAILY_CHAT_PROVIDER", "azure").lower() == "dashscope":
            self.client = DashScopeChatCompletionsClient.from_env(opener=opener)
        else:
            self.client = AzureChatCompletionsClient.from_env(opener=opener)
        self._streamed_turn: Optional[AgentTurnResult] = None

    def reply(self, dialogue_history: List[Dict[str, str]]) -> str:
        return self.reply_turn(dialogue_history).reply

    def reply_turn(
        self, dialogue_history: List[Dict[str, str]], *,
        voice_emotion: Optional[VoiceEmotionContext] = None,
    ) -> AgentTurnResult:
        messages = [{"role": "system", "content": DAILY_CHAT_SYSTEM_PROMPT}]
        if voice_emotion is not None:
            messages.append({"role": "system", "content": voice_emotion.model_message()})
        messages.extend(self._to_chat_messages(dialogue_history))
        completion = complete_with_metadata_compat(
            self.client,
            messages,
            temperature=0.8,
            max_completion_tokens=500,
        )
        return AgentTurnResult(
            reply=completion.text, mode="daily_chat", completion=completion,
            trace={"voice_emotion": voice_emotion.to_dict()} if voice_emotion is not None else {},
        )

    def stream_reply(
        self,
        dialogue_history: List[Dict[str, str]],
        *,
        voice_emotion: Optional[VoiceEmotionContext] = None,
    ) -> Iterator[str]:
        messages = [{"role": "system", "content": DAILY_CHAT_SYSTEM_PROMPT}]
        if voice_emotion is not None:
            messages.append({"role": "system", "content": voice_emotion.model_message()})
        messages.extend(self._to_chat_messages(dialogue_history))
        kwargs = {"temperature": 0.8, "max_completion_tokens": 500}
        self._streamed_turn = None
        stream = getattr(self.client, "stream_with_metadata", None)
        if stream is None:
            completion = complete_with_metadata_compat(self.client, messages, **kwargs)
            self._streamed_turn = self._stream_result(completion, voice_emotion)
            yield completion.text
            return

        completion: Optional[ChatCompletionResult] = None
        pieces: list[str] = []
        for chunk in stream(messages, **kwargs):
            if chunk.delta:
                pieces.append(chunk.delta)
                yield chunk.delta
            if chunk.completion is not None:
                completion = chunk.completion
        if completion is None:
            text = "".join(pieces).strip()
            if not text:
                raise RuntimeError("Daily Chat stream returned no reply.")
            completion = ChatCompletionResult(text=text)
        self._streamed_turn = self._stream_result(completion, voice_emotion)

    def streamed_turn_result(self) -> AgentTurnResult:
        if self._streamed_turn is None:
            raise RuntimeError("Daily Chat stream has not completed.")
        return self._streamed_turn

    @staticmethod
    def _stream_result(
        completion: ChatCompletionResult,
        voice_emotion: Optional[VoiceEmotionContext],
    ) -> AgentTurnResult:
        return AgentTurnResult(
            reply=completion.text,
            mode="daily_chat",
            completion=completion,
            trace={"voice_emotion": voice_emotion.to_dict()} if voice_emotion is not None else {},
        )

    def _to_chat_messages(self, dialogue_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        messages = []
        for item in dialogue_history[-12:]:
            role = item.get("role")
            content = item.get("content", "")
            if not content:
                continue
            if role == "elderly":
                messages.append({"role": "user", "content": content})
            elif role == "agent":
                messages.append({"role": "assistant", "content": content})
        return messages
