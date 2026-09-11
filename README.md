# Agentic AI Technical Support Assistant

A modular, enterprise-grade AI Technical Support Assistant built with Python, LangChain, LangGraph, ChromaDB, and Local/Cloud LLM infrastructure.

---

## 🛠️ Tech Stack & Prerequisites

* **Language:** Python 3.11+
* **Environment & Package Manager:** `uv`
* **Vector Database:** ChromaDB (Local)
* **Embedding Providers:** Ollama (`nomic-embed-text`) / OpenAI (`text-embedding-3-small`)
* **Frameworks:** LangChain, LangGraph

---

## 📂 Directory Structure

```text
agentic-support-assistant/
├── data/
│   └── technical_docs.txt      # External knowledge base (Separation of Data & Code)
├── src/
│   ├── __init__.py
│   └── rag_engine.py           # Dual-provider RAG Engine (Ollama/OpenAI)

## Step-by-Step Setup & Phase 1 Execution
* **1. Environment Initialization**
Initialize the project virtual environment using uv:

├── .gitignore                  # Exclusion rules for secrets, DBs, and virtual envs
├── pyproject.toml              # Project dependencies managed via uv
└── README.md                   # Project documentation
