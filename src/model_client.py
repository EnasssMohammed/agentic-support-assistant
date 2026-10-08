"""
Model boundary layer.

Keeping all LLM calls behind one interface means we can swap providers
(Ollama now, OpenAI later) without touching baseline.py or agent.py.
Provider is chosen via the MODEL_PROVIDER env var, so switching later
is a one-line change in .env, not a code change.
"""
import os
import json
from abc import ABC, abstractmethod
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from src.logging_config import get_logger

load_dotenv()
logger = get_logger("model_client")


class ModelClientError(Exception):
    """Raised when the model provider can't be reached or returns something
    unusable. Callers should catch this specifically rather than a bare
    Exception, so other bugs don't get silently swallowed."""


class ModelClient(ABC):
    @abstractmethod
    def generate(self, messages: list[dict]) -> str:
        """messages: [{"role": "system"|"user"|"assistant", "content": str}]"""
        raise NotImplementedError

    @abstractmethod
    def generate_structured(self, messages: list[dict], schema: type[BaseModel]) -> BaseModel:
        """Same as generate(), but forces the reply to match `schema` and
        returns a parsed instance of it instead of raw text."""
        raise NotImplementedError


class OllamaClient(ModelClient):
    """Local model via Ollama. No API key needed. Requires `ollama serve` running."""

    def __init__(self, model_name: str = "llama3.1"):
        import ollama
        self._client = ollama
        self._model_name = model_name

    def generate(self, messages: list[dict]) -> str:
        try:
            resp = self._client.chat(model=self._model_name, messages=messages)
            return resp["message"]["content"]
        except Exception as e:
            logger.error(f"Ollama generate() failed (model={self._model_name}): {e}")
            raise ModelClientError(
                f"Could not reach Ollama model '{self._model_name}'. "
                f"Is 'ollama serve' running and is the model pulled? Original error: {e}"
            ) from e

    def generate_structured(self, messages: list[dict], schema: type[BaseModel]) -> BaseModel:
        try:
            resp = self._client.chat(
                model=self._model_name,
                messages=messages,
                format=schema.model_json_schema(),
            )
        except Exception as e:
            logger.error(f"Ollama generate_structured() failed (model={self._model_name}): {e}")
            raise ModelClientError(
                f"Could not reach Ollama model '{self._model_name}'. "
                f"Is 'ollama serve' running and is the model pulled? Original error: {e}"
            ) from e

        raw_content = resp["message"]["content"]
        try:
            return schema.model_validate_json(raw_content)
        except (ValidationError, json.JSONDecodeError) as e:
            logger.error(
                f"Model returned invalid structured output for schema "
                f"{schema.__name__}. Raw content: {raw_content!r}. Error: {e}"
            )
            raise ModelClientError(
                f"Model '{self._model_name}' returned output that doesn't match "
                f"{schema.__name__}. This can happen with small models under load. "
                f"Raw output was: {raw_content[:200]}"
            ) from e


class OpenAIClient(ModelClient):
    def __init__(self, model_name: str = "gpt-4o-mini"):
        from openai import OpenAI
        self._client = OpenAI()
        self._model_name = model_name

    def generate(self, messages: list[dict]) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI generate() failed (model={self._model_name}): {e}")
            raise ModelClientError(f"OpenAI API call failed: {e}") from e

    def generate_structured(self, messages: list[dict], schema: type[BaseModel]) -> BaseModel:
        try:
            resp = self._client.beta.chat.completions.parse(
                model=self._model_name,
                messages=messages,
                response_format=schema,
            )
            return resp.choices[0].message.parsed
        except Exception as e:
            logger.error(f"OpenAI generate_structured() failed (model={self._model_name}): {e}")
            raise ModelClientError(f"OpenAI structured API call failed: {e}") from e


def get_model_client() -> ModelClient:
    """Factory: reads MODEL_PROVIDER from .env (defaults to Ollama)."""
    provider = os.getenv("MODEL_PROVIDER", "ollama").lower()
    logger.info(f"Initializing model client: provider={provider}")
    if provider == "openai":
        return OpenAIClient(model_name=os.getenv("MODEL_NAME", "gpt-4o-mini"))
    return OllamaClient(model_name=os.getenv("MODEL_NAME", "llama3.1"))
