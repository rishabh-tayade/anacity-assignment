import os

from moveflow.llm.base import LLMClient

DEFAULT_MODEL = "claude-opus-5-5"


def build_llm_client() -> LLMClient | None:
    """Returns the configured model client, or None to run fully rule-based.

    LLM_PROVIDER=none forces offline mode even when a key is present, which is
    handy for demos and tests.
    """
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "none":
        return None
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None
        from moveflow.llm.anthropic_client import AnthropicLLMClient

        return AnthropicLLMClient(
            model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
            effort=os.getenv("LLM_EFFORT", "low"),
        )
    raise ValueError(f"Unsupported LLM_PROVIDER '{provider}'")
