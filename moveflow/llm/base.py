from typing import Any, Protocol


class LLMError(Exception):
    """Raised when the model can't give a usable answer (network, refusal, bad JSON...).

    Every caller catches this and falls back to its rule-based path, so the
    product keeps working when the model is slow, down, or not configured.
    """


class LLMClient(Protocol):
    @property
    def model_name(self) -> str: ...

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...

    def generate_text(self, system: str, prompt: str) -> str: ...
