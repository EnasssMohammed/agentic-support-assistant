"""
Typed, validated configuration, read from the environment and .env.

One place defines which settings exist and which combinations are valid, so a mistake
(a missing OPENAI_API_KEY, or an Ollama model name left in .env after switching to OpenAI)
fails immediately with a clear message, instead of after minutes of building an index or
as seven failed cases in an evaluation report.
"""
from typing import Literal

from dotenv import load_dotenv
from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Also exports OPENAI_API_KEY into os.environ, which the OpenAI SDKs read themselves.
load_dotenv()

DEFAULT_MODEL_NAMES = {"ollama": "llama3.1", "openai": "gpt-4o-mini"}


class ConfigError(ValueError):
    """The configuration is missing something or contradicts itself."""


class Settings(BaseSettings):
    # env_ignore_empty: a blank line such as `OPENAI_API_KEY=` counts as not set.
    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True, protected_namespaces=())

    model_provider: Literal["ollama", "openai"] = "ollama"
    model_name: str | None = None
    openai_api_key: SecretStr | None = None

    @field_validator("model_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, value):
        # "OpenAI" and " openai " in .env mean the same thing as "openai".
        return value.strip().lower() if isinstance(value, str) else value

    @property
    def resolved_model_name(self) -> str:
        return self.model_name or DEFAULT_MODEL_NAMES[self.model_provider]

    @model_validator(mode="after")
    def _check_provider_settings(self) -> "Settings":
        name = self.resolved_model_name
        if self.model_provider == "openai":
            if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
                raise ValueError("MODEL_PROVIDER=openai needs OPENAI_API_KEY (set it in .env).")
            # Fine-tuned OpenAI models are named "ft:...", so only other colons are suspicious.
            if ":" in name and not name.startswith("ft:"):
                raise ValueError(
                    f"MODEL_NAME={name!r} looks like an Ollama model. With MODEL_PROVIDER=openai "
                    "use an OpenAI model, for example gpt-4o-mini."
                )
        elif name.startswith("gpt-"):
            raise ValueError(
                f"MODEL_NAME={name!r} looks like an OpenAI model. With MODEL_PROVIDER=ollama "
                "use an Ollama model, for example llama3.2:1b."
            )
        return self


def _describe(error: dict) -> str:
    message = error["msg"].removeprefix("Value error, ")
    field = ".".join(str(part) for part in error["loc"]).upper()
    return f"{field}: {message}" if field else message


def load_settings() -> Settings:
    """Read the settings now (not cached, so a changed environment is picked up)."""
    try:
        return Settings()
    except ValidationError as e:
        problems = "; ".join(_describe(err) for err in e.errors())
        raise ConfigError(f"Invalid configuration: {problems}") from None
