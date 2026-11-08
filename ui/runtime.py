"""Cached runtime objects shared by the UI pages: the knowledge-base index and the agent built on it.

Both are keyed by the knowledge-base version, so publishing a document gives the next customer message a
freshly indexed agent without restarting the app.
"""

from __future__ import annotations

import streamlit as st

from src.agent_loop import VeloAgent
from src.knowledge import KnowledgeStore


def provider_name() -> str:
    from src.settings import load_settings

    provider = getattr(load_settings(), "model_provider", "openai")
    return getattr(provider, "value", provider)


def current_kb() -> tuple[str, tuple[str, ...]]:
    """(version, files) of the knowledge base as it is on disk right now."""
    store = KnowledgeStore()
    return store.version(), tuple(str(p) for p in store.files())


def build_rag(files: tuple[str, ...]):
    """Build (or reuse the persisted) index for these files. Raises if embeddings are unreachable."""
    from src.rag_engine import RAGEngine

    return RAGEngine(file_path=list(files), provider=provider_name())


@st.cache_resource(show_spinner="Indexing the knowledge base…")
def load_rag(kb_version: str, files: tuple[str, ...]):
    return build_rag(files)


@st.cache_resource(show_spinner="Starting Velo…")
def load_agent(kb_version: str, files: tuple[str, ...]) -> VeloAgent:
    from src.model_client import get_model_client
    from src.topic_classifier import model_topic_classifier

    model = get_model_client()
    return VeloAgent(
        model=model, rag=load_rag(kb_version, files), topic_classifier=model_topic_classifier(model)
    )


def clear_caches() -> None:
    load_agent.clear()
    load_rag.clear()
