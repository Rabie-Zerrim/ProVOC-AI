"""Tests for llm.agent — LLMAgent."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest

from llm.agent import LLMAgent, ModelUnavailableError


def _fresh_agent() -> LLMAgent:
    """Return a new LLMAgent with cleared singleton state and a mocked Groq client."""
    LLMAgent._instance = None
    agent = LLMAgent.__new__(LLMAgent)
    agent._client = MagicMock()
    return agent


def _make_groq_response(content: str) -> MagicMock:
    """Build a minimal mock that looks like a Groq chat completion response."""
    response = MagicMock()
    response.choices[0].message.content = content
    return response


def test_complete_returns_string() -> None:
    """complete() should return a plain string from the model response."""
    agent = _fresh_agent()
    agent._client.chat.completions.create.return_value = _make_groq_response(
        "This is a test response."
    )

    result = agent.complete([{"role": "user", "content": "Hello"}])

    assert isinstance(result, str)
    assert result == "This is a test response."


def test_fallback_model_used_on_primary_failure() -> None:
    """complete() should retry with FALLBACK_MODEL when the primary raises APIError."""
    import groq as groq_lib

    agent = _fresh_agent()
    # Pin distinct model names so the test is independent of env-var values
    agent.PRIMARY_MODEL = "primary-test-model"
    agent.FALLBACK_MODEL = "fallback-test-model"

    fallback_mock = MagicMock()
    fallback_mock.choices[0].message.content = "Fallback answer"

    # First call (primary) raises; second call (fallback) returns successfully
    agent._client.chat.completions.create.side_effect = [
        groq_lib.APIConnectionError(request=MagicMock()),
        fallback_mock,
    ]

    result = agent.complete([{"role": "user", "content": "Hello"}])

    assert result == "Fallback answer"
    calls = agent._client.chat.completions.create.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["model"] == "primary-test-model"
    assert calls[1].kwargs["model"] == "fallback-test-model"


def test_singleton_returns_same_instance() -> None:
    """get_instance() must return the exact same object on repeated calls."""
    LLMAgent._instance = None

    with patch("llm.agent.groq_lib.Groq"):
        first = LLMAgent.get_instance()
        second = LLMAgent.get_instance()

    assert first is second
