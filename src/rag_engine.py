import os

from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

SUPPORTED_PROVIDERS = ("ollama", "openai")


def resolve_provider(provider: str | None = None) -> str:
    """Explicit argument wins; otherwise MODEL_PROVIDER from .env; otherwise ollama.

    The LLM (model_client.py) and the embeddings read the same switch, so changing
    MODEL_PROVIDER in .env moves both together and they can't drift apart.
    """
    resolved = (provider or os.getenv("MODEL_PROVIDER", "ollama")).strip().lower()
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
            return OllamaEmbeddings(model="nomic-embed-text")
        elif self.provider == "openai":
            return OpenAIEmbeddings(model="text-embedding-3-small")
        else:
            raise ValueError("Provider not supported. Choose 'ollama' or 'openai'.")

    def _build_index(self):
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: {self.file_path}")

        # 1. Load the source document
        loader = TextLoader(self.file_path)
        docs = loader.load()

        # 2. Split the text into small chunks
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
        chunks = text_splitter.split_documents(docs)

        # 3. Store the chunks in ChromaDB
        self.vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            collection_name=f"technical_docs_{self.provider}"
        )

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
