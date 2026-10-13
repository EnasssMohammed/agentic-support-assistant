"""Configuration is validated once, with clear errors, before any slow work starts."""
import pytest

from src.model_client import OllamaClient, OpenAIClient, get_model_client
from src.settings import ConfigError, load_settings


def test_defaults_to_local_ollama():
    settings = load_settings()
    assert settings.model_provider == "ollama"
    assert settings.resolved_model_name == "llama3.1"


def test_openai_settings_are_read_from_the_environment_case_insensitively(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "OpenAI")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = load_settings()
    assert settings.model_provider == "openai"
    assert settings.resolved_model_name == "gpt-4o-mini"


def test_openai_without_a_key_fails_with_a_clear_message(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_settings()


def test_a_blank_key_line_counts_as_missing(monkeypatch):
    """.env.example ships with `OPENAI_API_KEY=` empty."""
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_settings()


def test_an_ollama_model_name_left_in_env_is_rejected_for_openai(monkeypatch):
    """The easy mistake when switching providers: forgetting to change MODEL_NAME."""
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_NAME", "llama3.2:1b")
    with pytest.raises(ConfigError, match="looks like an Ollama model"):
        load_settings()


def test_fine_tuned_openai_model_names_are_accepted(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_NAME", "ft:gpt-4o-mini:acme::abc123")
    assert load_settings().resolved_model_name == "ft:gpt-4o-mini:acme::abc123"


def test_an_openai_model_name_is_rejected_for_ollama(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "gpt-4o-mini")
    with pytest.raises(ConfigError, match="looks like an OpenAI model"):
        load_settings()


def test_an_unsupported_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "banana")
    with pytest.raises(ConfigError, match="MODEL_PROVIDER"):
        load_settings()


def test_a_blank_provider_line_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "")
    assert load_settings().model_provider == "ollama"


def test_the_api_key_is_not_leaked_by_repr(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-very-secret")
    settings = load_settings()
    assert "sk-very-secret" not in repr(settings)
    assert "sk-very-secret" not in str(settings)


def test_the_factory_builds_the_client_the_settings_describe(monkeypatch):
    assert isinstance(get_model_client(), OllamaClient)

    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = get_model_client()
    assert isinstance(client, OpenAIClient)
    assert client.model_name == "gpt-4o-mini"


def test_the_factory_reports_a_missing_key_as_a_config_error_not_an_sdk_error(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        get_model_client()
