import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.intents import policy_topic, topic_compatible
from src.logging_config import get_logger
from src.settings import load_settings

logger = get_logger("rag_engine")

SUPPORTED_PROVIDERS = ("ollama", "openai")
OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 300          # fallback splitter only
CHUNK_OVERLAP = 50
SPLITTER_VERSION = "entries-v2"   # bump when chunking logic changes, so the index rebuilds
INDEX_DIR = Path("chroma_langchain")  # gitignored; one sub-folder per provider


@dataclass(frozen=True)
class Passage:
    """One retrieved chunk with enough provenance to cite it and to audit retrieval."""

    text: str
    source: str                    # "<file> > <section> > <entry>"
    distance: float | None = None  # lower is closer; None if the store gave no score
    topic: str = "general"         # router | account | billing | general


# ----------------------------------------------------------------- chunking

_SECTION_RE = re.compile(r"^\d+\.\s+\S")
_ENTRY_RE = re.compile(r"^-\s*\[(?P<title>[^\]]+)\]")
_RULE_RE = re.compile(r"^[-=\s]{8,}$")


def split_policy_entries(text: str) -> list[dict]:
    """Split a policy manual into one chunk per `- [Entry]:` item.

    Fixed-size splitting cuts rules in half (Policy Rule #1 is longer than 300 characters).
    Each entry is kept whole and prefixed with its section title, so the model always
    sees a complete rule with its context. Returns [] when the text has no such entries.
    """
    entries: list[dict] = []
    section = ""
    title: str | None = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal title, lines
        if title is not None and lines:
            body = "\n".join(line.rstrip() for line in lines).strip()
            entries.append(
                {
                    "text": f"{section}\n{body}".strip(),
                    "section": section,
                    "entry": title.strip(),
                }
            )
        title, lines = None, []

    for line in text.splitlines():
        if _RULE_RE.match(line):
            continue
        if _SECTION_RE.match(line.strip()):
            flush()
            section = line.strip()
            continue
        match = _ENTRY_RE.match(line.strip())
        if match:
            flush()
            title = match.group("title")
            lines = [line.strip()]
        elif title is not None:
            lines.append(line)
    flush()
    return entries


def resolve_provider(provider: str | None = None) -> str:
    """Explicit argument wins; otherwise MODEL_PROVIDER from .env; otherwise ollama.

    The LLM (model_client.py) and the embeddings read the same switch, so changing
    MODEL_PROVIDER in .env moves both together and they can't drift apart.
    """
    resolved = (provider or load_settings().model_provider).strip().lower()
    if resolved not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Provider '{resolved}' not supported. Choose one of: {', '.join(SUPPORTED_PROVIDERS)}."
        )
    return resolved


def _max_distance() -> float | None:
    """Optional relevance cutoff (VELO_MAX_DISTANCE). Unset = never drop a result.

    Calibrate it on your eval set before enabling: distances depend on the embedding model.
    """
    raw = os.getenv("VELO_MAX_DISTANCE", "").strip()
    return float(raw) if raw else None


class RAGEngine:
    def __init__(self, file_path="data/technical_docs.txt", provider: str | None = None):
        """
        provider: 'ollama' (local) or 'openai' (cloud). If omitted, follows the
        MODEL_PROVIDER setting in .env.
        """
        self.file_path = file_path
        self.provider = resolve_provider(provider)
        self.vector_store = None
        self.embeddings = self._get_embeddings()
        self._build_index()

    def _embedding_model(self) -> str:
        return OLLAMA_EMBEDDING_MODEL if self.provider == "ollama" else OPENAI_EMBEDDING_MODEL

    def _get_embeddings(self):
        if self.provider == "ollama":
            return OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL)
        return OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)

    def _fingerprint(self) -> str:
        """Identifies everything the index depends on: the source text, the provider,
        the embedding model and the chunking logic. If any of them changes, the
        stored index is stale and must be rebuilt."""
        digest = hashlib.sha256(Path(self.file_path).read_bytes())
        digest.update(
            f"|{self.provider}|{self._embedding_model()}|{SPLITTER_VERSION}"
            f"|{CHUNK_SIZE}|{CHUNK_OVERLAP}".encode()
        )
        return digest.hexdigest()

    def _load_chunks(self) -> list[Document]:
        docs = TextLoader(self.file_path, encoding="utf-8").load()
        source_name = Path(self.file_path).name

        entries = split_policy_entries(docs[0].page_content) if docs else []
        if entries:
            return [
                Document(
                    page_content=e["text"],
                    metadata={
                        "source": f"{source_name} > {e['section']} > {e['entry']}",
                        "section": e["section"],
                        "entry": e["entry"],
                        # lets retrieval keep a router rule out of an account conversation
                        "topic": policy_topic(f"{e['entry']} {e['text']}"),
                    },
                )
                for e in entries
            ]

        # Unstructured text: fall back to fixed-size chunks.
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        chunks = splitter.split_documents(docs)
        for chunk in chunks:
            chunk.metadata["source"] = source_name
            chunk.metadata["topic"] = "general"
        return chunks

    def _build_index(self):
        """Load the persisted index if it is still valid; otherwise build and store it.

        Embedding the knowledge base is the slow part, so it is done once and reused.
        Reusing instead of re-adding also avoids duplicate chunks.
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: {self.file_path}")

        persist_dir = INDEX_DIR / self.provider
        manifest_path = persist_dir / "manifest.json"
        collection_name = f"technical_docs_{self.provider}"
        fingerprint = self._fingerprint()

        store = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=str(persist_dir),
        )

        if self._manifest_matches(manifest_path, fingerprint) and store.get(limit=1)["ids"]:
            logger.info(f"Reusing persisted index ({persist_dir})")
            self.vector_store = store
            return

        logger.info(f"Building index for {self.file_path} with {self.provider} embeddings...")
        # Drop whatever is stored (stale or half-built) before adding, so chunks never pile up.
        store.delete_collection()

        chunks = self._load_chunks()
        self.vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            collection_name=collection_name,
            persist_directory=str(persist_dir),
        )

        # Written last: a crash mid-build leaves no manifest, so the next run rebuilds.
        manifest_path.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
        logger.info(f"Index built and persisted ({len(chunks)} chunks)")

    @staticmethod
    def _manifest_matches(manifest_path: Path, fingerprint: str) -> bool:
        if not manifest_path.exists():
            return False
        try:
            stored = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return stored.get("fingerprint") == fingerprint

    def retrieve_passages(self, query: str, k: int = 3, topic: str | None = None) -> list[Passage]:
        """The k closest chunks for the customer's current topic, de-duplicated, with provenance.

        When `topic` is router, account or billing, only passages about that topic (or general
        rules) are returned. Without this, an Arabic account question could be answered with
        router steps whenever the embedding ranks a router entry first. An empty list means
        "no relevant evidence".
        """
        cutoff = _max_distance()
        passages: list[Passage] = []
        seen: set[str] = set()
        # Over-fetch, then filter by topic, so the filter cannot starve the result.
        for doc, distance in self.vector_store.similarity_search_with_score(query, k=max(k * 4, 12)):
            passage_topic = doc.metadata.get("topic", "general")
            if doc.page_content in seen or not topic_compatible(passage_topic, topic):
                continue
            if cutoff is not None and distance > cutoff:
                continue
            seen.add(doc.page_content)
            passages.append(
                Passage(
                    text=doc.page_content,
                    source=doc.metadata.get("source", "unknown"),
                    distance=float(distance),
                    topic=passage_topic,
                )
            )
            if len(passages) == k:
                break
        return passages

    def retrieve(self, query: str, k: int = 3, topic: str | None = None) -> str:
        """Retrieved passages as text for the prompt and the ticket, each labelled with its source."""
        passages = self.retrieve_passages(query, k=k, topic=topic)
        if not passages:
            return "NO RELEVANT POLICY PASSAGE FOUND."
        return "\n---\n".join(f"[Source: {p.source}]\n{p.text}" for p in passages)


if __name__ == "__main__":
    print(f"--- Testing RAG engine ({resolve_provider()}) ---")
    rag = RAGEngine()
    for p in rag.retrieve_passages("What should I do if Error 500 appears?"):
        print(f"{p.distance:.3f}  {p.source}")
