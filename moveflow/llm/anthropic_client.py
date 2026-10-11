import json
import logging
from typing import Any

import anthropic

from moveflow.llm.base import LLMError

logger = logging.getLogger(__name__)


class AnthropicLLMClient:
    """LLMClient backed by Claude through the official Anthropic SDK."""

    def __init__(self, model: str, effort: str = "low", client: anthropic.Anthropic | None = None):
        self._model = model
        self._effort = effort
        self._client = client or anthropic.Anthropic(timeout=30.0, max_retries=1)

    @property
    def model_name(self) -> str:
        return self._model

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        text = self._complete(
            system,
            prompt,
            output_config={"effort": self._effort, "format": {"type": "json_schema", "schema": schema}},
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise LLMError(f"Model returned invalid JSON: {error}") from error

    def generate_text(self, system: str, prompt: str) -> str:
        return self._complete(system, prompt, output_config={"effort": self._effort})

    def _complete(self, system: str, prompt: str, output_config: dict[str, Any]) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config=output_config,
            )
        except anthropic.APIError as error:
            logger.warning("Claude request failed: %s", error)
            raise LLMError(str(error)) from error

        if response.stop_reason in ("refusal", "max_tokens"):
            raise LLMError(f"Unusable response (stop_reason={response.stop_reason})")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LLMError("Empty response")
        return text
