"""
Documents with headings are chunked by section, and the knowledge base can be built from several files.

Real Chroma with a fake embedder: no Ollama or OpenAI needed, so it runs in CI.
"""
import hashlib
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

import src.rag_engine as rag_module
from src.rag_engine import SECTION_MAX_CHARS, RAGEngine, split_sections

DATA = Path(__file__).resolve().parent.parent / "data"


class FakeEmbeddings(Embeddings):
    def _vector(self, text):
        return [b / 255 for b in hashlib.sha256(text.encode()).digest()[:16]]

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture
def engine_env(monkeypatch, tmp_path):
    monkeypatch.setattr(RAGEngine, "_get_embeddings", lambda self: FakeEmbeddings())
    monkeypatch.setattr(rag_module, "INDEX_DIR", tmp_path / "index")
    return tmp_path


# ------------------------------------------------------------------------------ section splitter

def test_numbered_headings_become_one_chunk_each_with_the_document_title():
    text = "Account policy\n\n1. Password reset:\nUse the OTP code.\n\n2. Billing:\nPay within 5 days.\n"
    chunks = split_sections(text)
    assert [c["entry"] for c in chunks] == ["1. Password reset", "2. Billing"]
    assert chunks[0]["text"] == "Account policy\n1. Password reset\nUse the OTP code."


def test_markdown_headings_work_and_a_level_one_heading_is_the_title():
    chunks = split_sections("# Escalation\n\n## 1. Immediate\n* Rule A\n* Rule B\n\n## 2. Metadata\n* Ticket id\n")
    assert [c["entry"] for c in chunks] == ["1. Immediate", "2. Metadata"]
    assert all(c["text"].startswith("Escalation\n") for c in chunks)
    assert "Rule A" in chunks[0]["text"] and "Rule B" in chunks[0]["text"]


def test_numbered_steps_inside_a_section_are_not_headings():
    text = "# Guide\n\n## 1. Outage\n1. Check the lights\n2. Restart the router\n3. Call support\n"
    chunks = split_sections(text)
    assert len(chunks) == 1 and "2. Restart the router" in chunks[0]["text"]


def test_a_long_section_is_cut_between_lines_and_every_part_repeats_the_heading():
    body = "\n".join(f"* rule number {i}: " + "detail " * 20 for i in range(30))
    chunks = split_sections(f"# Doc\n\n## 1. Big section\n{body}\n")
    assert len(chunks) > 1
    assert all(len(c["text"]) <= SECTION_MAX_CHARS + 60 for c in chunks)
    assert all("1. Big section" in c["text"] for c in chunks)
    assert chunks[1]["entry"] == "1. Big section (part 2)"


def test_text_without_headings_falls_back_to_the_fixed_size_splitter():
    assert split_sections("just one long paragraph " * 40) == []


def test_the_real_arabic_policy_files_are_split_into_whole_sections():
    expected = {"Account_And_Billing_Policy.txt": 3, "Escalation_Rules_And_Limits.md": 2,
                "Network_Troubleshooting_Guide.md": 2}
    for name, count in expected.items():
        chunks = split_sections((DATA / name).read_text(encoding="utf-8"))
        assert len(chunks) == count, name
        assert all(len(c["text"]) < SECTION_MAX_CHARS for c in chunks)


# ------------------------------------------------------------------------------ several files

def test_the_engine_indexes_every_file_and_cites_each_source(engine_env):
    a, b = engine_env / "a.md", engine_env / "b.txt"
    a.write_text("# A\n\n## 1. Alpha:\nalpha text\n", encoding="utf-8")
    b.write_text("B title\n\n1. Beta:\nbeta text\n", encoding="utf-8")
    engine = RAGEngine(file_path=[a, b], provider="ollama")
    sources = {p.source for p in engine.retrieve_passages("anything", k=5)}
    assert sources == {"a.md > 1. Alpha", "b.txt > 1. Beta"}


def test_changing_any_file_rebuilds_and_the_order_of_files_does_not_matter(engine_env):
    a, b = engine_env / "a.md", engine_env / "b.md"
    a.write_text("# A\n\n## 1. X:\none\n", encoding="utf-8")
    b.write_text("# B\n\n## 1. Y:\ntwo\n", encoding="utf-8")
    first = RAGEngine(file_path=[a, b], provider="ollama")._fingerprint()
    assert RAGEngine(file_path=[b, a], provider="ollama")._fingerprint() == first
    b.write_text("# B\n\n## 1. Y:\nchanged\n", encoding="utf-8")
    assert RAGEngine(file_path=[a, b], provider="ollama")._fingerprint() != first


def test_a_single_file_keeps_the_fingerprint_it_always_had(engine_env):
    """Existing persisted indexes must stay valid: one file hashes exactly as before."""
    path = engine_env / "docs.txt"
    path.write_text("1. A:\ntext\n", encoding="utf-8")
    engine = RAGEngine(file_path=str(path), provider="ollama")
    legacy = hashlib.sha256(path.read_bytes())
    legacy.update(
        f"|ollama|{rag_module.OLLAMA_EMBEDDING_MODEL}|{rag_module.SPLITTER_VERSION}"
        f"|{rag_module.CHUNK_SIZE}|{rag_module.CHUNK_OVERLAP}".encode()
    )
    assert engine._fingerprint() == legacy.hexdigest()


def test_a_missing_file_is_reported_by_name(engine_env):
    present = engine_env / "a.md"
    present.write_text("# A\n\n## 1. X:\none\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="gone.md"):
        RAGEngine(file_path=[present, engine_env / "gone.md"], provider="ollama")


# ------------------------------------------------------------------------------ the Studio publishes through the engine

def test_publishing_through_the_studio_makes_the_new_policy_searchable(engine_env):
    from src.knowledge import KnowledgeStore

    builtin = engine_env / "technical_docs.txt"
    builtin.write_text("1. RULES\n--------\n- [Return Window]:\n  14 days.\n", encoding="utf-8")
    store = KnowledgeStore(engine_env / "knowledge", builtin=builtin)

    def verify(files):
        RAGEngine(file_path=list(files), provider="ollama")

    text = "# Delivery\n\n## 1. Courier delay:\nA late parcel is escalated after 5 working days.\n"
    store.publish_many([("delivery.md", text.encode())], "Enas", "first", verify=verify)
    engine = RAGEngine(file_path=store.files(), provider="ollama")
    assert any(p.source == "delivery.md > 1. Courier delay" for p in engine.retrieve_passages("late parcel", k=5))


def test_an_unreachable_embedding_service_rolls_the_publish_back(engine_env, monkeypatch):
    from src.knowledge import KnowledgeError, KnowledgeStore

    builtin = engine_env / "technical_docs.txt"
    builtin.write_text("1. RULES\n--------\n- [Return Window]:\n  14 days.\n", encoding="utf-8")
    store = KnowledgeStore(engine_env / "knowledge", builtin=builtin)

    class Unreachable(Embeddings):
        def embed_documents(self, texts):
            raise ConnectionError("embedding service unreachable")

        def embed_query(self, text):
            raise ConnectionError("embedding service unreachable")

    monkeypatch.setattr(RAGEngine, "_get_embeddings", lambda self: Unreachable())

    def verify(files):
        RAGEngine(file_path=list(files), provider="ollama")

    with pytest.raises(KnowledgeError, match="undone"):
        store.publish_many([("a.md", b"# A\n\n## 1. X:\nrule\n")], "Enas", verify=verify)
    assert store.documents() == [] and [p.name for p in store.files()] == ["technical_docs.txt"]
