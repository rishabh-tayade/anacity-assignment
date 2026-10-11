from types import SimpleNamespace

import anthropic
import pytest

from moveflow.llm.anthropic_client import AnthropicLLMClient
from moveflow.llm.base import LLMError
from moveflow.llm.factory import build_llm_client


class StubMessages:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def stub_client(text="", stop_reason="end_turn", error=None):
    response = SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )
    return SimpleNamespace(messages=StubMessages(response, error))


def test_json_output_uses_structured_output_and_parses():
    client = stub_client('{"intent": "confirm"}')
    llm = AnthropicLLMClient("claude-opus-5-5", client=client)
    assert llm.generate_json("system", "prompt", {"type": "object"}) == {"intent": "confirm"}
    sent = client.messages.calls[0]
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["model"] == "claude-opus-5-5"


@pytest.mark.parametrize("client", [
    stub_client("not json"),
    stub_client("", stop_reason="refusal"),
    stub_client("{}", stop_reason="max_tokens"),
])
def test_unusable_responses_raise_llm_error(client):
    with pytest.raises(LLMError):
        AnthropicLLMClient("claude-opus-5-5", client=client).generate_json("s", "p", {})


class FakeAPIError(anthropic.APIError):
    def __init__(self):
        Exception.__init__(self, "service unavailable")


def test_api_errors_become_llm_errors():
    client = stub_client(error=FakeAPIError())
    with pytest.raises(LLMError):
        AnthropicLLMClient("claude-opus-5-5", client=client).generate_text("s", "p")


def test_factory_runs_offline_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert build_llm_client() is None
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert build_llm_client() is None
