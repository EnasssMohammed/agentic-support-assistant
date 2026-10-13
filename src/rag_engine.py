import hashlib
import json
import os
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.logging_config import get_logger
from src.settings import load_settings

logger = get_logger("rag_engine")

SUPPORTED_PROVIDERS = ("ollama", "openai")
OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 300
CHUNK_OVERLAP = 50
INDEX_DIR = Path("chroma_langchain")  # gitignored; one sub-folder per provider


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

    def _get_embeddings(self):
        if self.provider == "ollama":
            return OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL)
        elif self.provider == "openai":
            return OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)
        else:
            raise ValueError("Provider not supported. Choose 'ollama' or 'openai'.")

    def _fingerprint(self) -> str:
        """Identifies everything the index depends on: the source text, the provider,
        the embedding model and the chunking settings. If any of them changes, the
        stored index is stale and must be rebuilt."""
        embedding_model = (
            OLLAMA_EMBEDDING_MODEL if self.provider == "ollama" else OPENAI_EMBEDDING_MODEL
        )
        digest = hashlib.sha256(Path(self.file_path).read_bytes())
        digest.update(f"|{self.provider}|{embedding_model}|{CHUNK_SIZE}|{CHUNK_OVERLAP}".encode())
        return digest.hexdigest()

    def _build_index(self):
        """Load the persisted index if it is still valid; otherwise build and store it.

        Embedding the knowledge base is the slow part (minutes on a local model), so it is
        done once and reused. Reusing instead of re-adding also avoids duplicate chunks,
        which an in-memory index accumulates every time a second engine is created.
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

        # 1. Load the source document
        docs = TextLoader(self.file_path).load()

        # 2. Split the text into small chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        chunks = text_splitter.split_documents(docs)

        # 3. Store the chunks in ChromaDB (persisted on disk)
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

    def retrieve(self, query: str, k: int = 3) -> str:
        """Search the indexed document chunks for the k most relevant matches.
        k=3 (not 1) because a single nearest chunk can land on the wrong
        policy section entirely when the query is short or ambiguous."""
        results = self.vector_store.similarity_search(query, k=k)
        return "\n---\n".join([doc.page_content for doc in results])


if __name__ == "__main__":
    print("--- Testing Local RAG Engine via Ollama ---")
    rag = RAGEngine()
    response = rag.retrieve("What should I do if Error 500 appears?")
    print(response)
