"""Provider selection must follow .env, so the LLM and embeddings can't drift apart."""
import pytest

from src.rag_engine import resolve_provider


def test_defaults_to_ollama_when_nothing_is_set(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    assert resolve_provider() == "ollama"


def test_follows_model_provider_env_var(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "OpenAI")
    assert resolve_provider() == "openai"


def test_explicit_argument_overrides_env(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    assert resolve_provider("ollama") == "ollama"


def test_unsupported_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "banana")
    with pytest.raises(ValueError, match="not supported"):
        resolve_provider()
