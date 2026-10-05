"""
Model boundary layer.

Keeping all LLM calls behind one interface means we can swap providers
(Ollama now, OpenAI later) without touching baseline.py or agent.py.
Provider is chosen via the MODEL_PROVIDER env var, so switching later
is a one-line change in .env, not a code change.
"""
import os
from abc import ABC, abstractmethod
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


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
        resp = self._client.chat(model=self._model_name, messages=messages)
        return resp["message"]["content"]

    def generate_structured(self, messages: list[dict], schema: type[BaseModel]) -> BaseModel:
        resp = self._client.chat(
            model=self._model_name,
            messages=messages,
            format=schema.model_json_schema(),
        )
        return schema.model_validate_json(resp["message"]["content"])


class OpenAIClient(ModelClient):
    def __init__(self, model_name: str = "gpt-4o-mini"):
        from openai import OpenAI
        self._client = OpenAI()
        self._model_name = model_name

    def generate(self, messages: list[dict]) -> str:
        resp = self._client.chat.completions.create(
            model=self._model_name,
            messages=messages,
        )
        return resp.choices[0].message.content

    def generate_structured(self, messages: list[dict], schema: type[BaseModel]) -> BaseModel:
        resp = self._client.beta.chat.completions.parse(
            model=self._model_name,
            messages=messages,
            response_format=schema,
        )
        return resp.choices[0].message.parsed


def get_model_client() -> ModelClient:
    """Factory: reads MODEL_PROVIDER from .env (defaults to Ollama)."""
    provider = os.getenv("MODEL_PROVIDER", "ollama").lower()
    if provider == "openai":
        return OpenAIClient(model_name=os.getenv("MODEL_NAME", "gpt-4o-mini"))
    return OllamaClient(model_name=os.getenv("MODEL_NAME", "llama3.1"))
