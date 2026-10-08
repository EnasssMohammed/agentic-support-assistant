import os

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


class RAGEngine:
    def __init__(self, file_path="data/technical_docs.txt", provider="ollama"):
        """
        provider: 'ollama' for local embeddings, or 'openai' for the cloud service.
        """
        self.file_path = file_path
        self.provider = provider.lower()
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
    rag = RAGEngine(provider="ollama")
    response = rag.retrieve("What should I do if Error 500 appears?")
    print(response)
