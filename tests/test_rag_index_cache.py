"""
The knowledge-base index is built once and reused, never re-embedded or duplicated.

Uses real Chroma with a counting fake embedder, so it needs no Ollama/OpenAI and runs in CI.
"""
import hashlib

import pytest
from langchain_core.embeddings import Embeddings

import src.rag_engine as rag_module
from src.rag_engine import RAGEngine


class CountingEmbeddings(Embeddings):
    """Deterministic fake embedder that counts how many texts it was asked to embed."""

    def __init__(self):
        self.texts_embedded = 0

    def _vector(self, text: str) -> list[float]:
        self.texts_embedded += 1
        return [b / 255 for b in hashlib.sha256(text.encode()).digest()[:16]]

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


POLICY_V1 = "\n\n".join(
    f"Section {i}: policy text number {i}. " + "Detailed rule wording. " * 12 for i in range(6)
)


@pytest.fixture
def embedder(monkeypatch, tmp_path):
    fake = CountingEmbeddings()
    monkeypatch.setattr(RAGEngine, "_get_embeddings", lambda self: fake)
    monkeypatch.setattr(rag_module, "INDEX_DIR", tmp_path / "index")
    return fake


@pytest.fixture
def docs_file(tmp_path):
    path = tmp_path / "docs.txt"
    path.write_text(POLICY_V1, encoding="utf-8")
    return str(path)


def chunk_count(engine: RAGEngine) -> int:
    return len(engine.vector_store.get()["ids"])


def test_second_engine_reuses_the_index_without_embedding_again(embedder, docs_file):
    first = RAGEngine(file_path=docs_file, provider="ollama")
    embedded_after_first_build = embedder.texts_embedded
    assert embedded_after_first_build > 0

    second = RAGEngine(file_path=docs_file, provider="ollama")

    assert embedder.texts_embedded == embedded_after_first_build
    assert chunk_count(second) == chunk_count(first)  # no duplicated chunks


def test_changed_source_file_triggers_a_rebuild_with_the_new_content(embedder, docs_file):
    RAGEngine(file_path=docs_file, provider="ollama")
    embedded_before = embedder.texts_embedded

    with open(docs_file, "w", encoding="utf-8") as f:
        f.write("A completely different knowledge base about refunds. " * 12)
    rebuilt = RAGEngine(file_path=docs_file, provider="ollama")

    assert embedder.texts_embedded > embedded_before
    assert "refunds" in rebuilt.retrieve("refunds")
    assert "Section 0" not in rebuilt.retrieve("Section 0")  # old content is gone


def test_providers_are_stored_separately(embedder, docs_file, tmp_path):
    RAGEngine(file_path=docs_file, provider="ollama")
    RAGEngine(file_path=docs_file, provider="openai")

    assert (tmp_path / "index" / "ollama" / "manifest.json").exists()
    assert (tmp_path / "index" / "openai" / "manifest.json").exists()


def test_missing_manifest_forces_a_rebuild(embedder, docs_file, tmp_path):
    """A crash mid-build leaves no manifest; the next run must rebuild, not trust the leftovers."""
    RAGEngine(file_path=docs_file, provider="ollama")
    (tmp_path / "index" / "ollama" / "manifest.json").unlink()
    embedded_before = embedder.texts_embedded

    rebuilt = RAGEngine(file_path=docs_file, provider="ollama")

    assert embedder.texts_embedded > embedded_before
    assert chunk_count(rebuilt) > 0
