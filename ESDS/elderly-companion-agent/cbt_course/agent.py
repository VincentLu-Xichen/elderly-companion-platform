from __future__ import annotations

import json
import os
from typing import Any

from cbt_course.azure_chat_client import AzureChatCompletionsClient
from cbt_course.prompt import COURSE_TUTOR_SYSTEM_PROMPT, build_course_prompt
from cbt_course.schemas import CourseAgentResult, CourseTurnDecision


class CourseModelResponseError(RuntimeError):
    pass


class CourseTutorAgent:
    """Constrained language-understanding helper for deterministic course steps."""

    def __init__(self, *, client: Any | None = None):
        self.client = client or self._client_from_env()

    @staticmethod
    def _client_from_env() -> AzureChatCompletionsClient:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_COURSE_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        if not endpoint:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT is not set.")
        if not api_key:
            raise RuntimeError("AZURE_OPENAI_API_KEY is not set.")
        if not deployment:
            raise RuntimeError("AZURE_OPENAI_COURSE_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT is not set.")
        return AzureChatCompletionsClient(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        )

    def evaluate(
        self,
        *,
        step: str,
        rubric: str,
        allowed_outcomes: list[str],
        content: str,
        relevant_state: dict[str, Any],
    ) -> CourseAgentResult:
        schema = {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": allowed_outcomes},
                "extracted_values": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "acknowledgement": {"type": "string"},
                "safety_category": {
                    "type": "string",
                    "enum": ["none", "self_harm", "medical_emergency", "fraud"],
                },
            },
            "required": ["outcome", "extracted_values", "acknowledgement", "safety_category"],
            "additionalProperties": False,
        }
        messages = [
            {"role": "system", "content": COURSE_TUTOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_course_prompt(
                    step=step,
                    rubric=rubric,
                    allowed_outcomes=allowed_outcomes,
                    content=content,
                    relevant_state=relevant_state,
                ),
            },
        ]
        completion = self.client.complete_with_metadata(
            messages,
            max_completion_tokens=350,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "course_turn_decision",
                    "strict": True,
                    "schema": schema,
                },
            },
        )
        try:
            raw = json.loads(completion.text)
            decision = CourseTurnDecision.model_validate(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise CourseModelResponseError("课程模型返回了无法验证的结构化结果。") from exc
        if decision.outcome not in allowed_outcomes:
            raise CourseModelResponseError("课程模型返回了当前步骤不允许的 outcome。")
        return CourseAgentResult(decision=decision, completion=completion)
