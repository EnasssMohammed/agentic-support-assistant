# Velo — Agentic Technical Support Assistant

A domain-agnostic, policy-grounded AI support agent, built as an applied
implementation of the Fin.ai agentic pattern: knowledge retrieval, safe
diagnostics, a bounded resolution workflow, and escalation to a human with
a full context package when the agent can't resolve the issue itself.

Current version: **v1.0.0** — all minimum evidence requirements implemented
and evaluated. See [`reports/final_evaluation.md`](reports/final_evaluation.md)
for the full before/after analysis against a non-agentic baseline.

---

## Why an agent, and not a single LLM call?

See [`docs/00-problem.md`](docs/00-problem.md) for the full problem
statement, PEAS, and success contract. In short: a single LLM call can't
retrieve the right policy, run a diagnostic, and decide whether to escalate
based on the result — that requires a loop that observes tool output and
decides again. [`reports/baseline_results.md`](reports/baseline_results.md)
documents exactly how a single-call baseline fails (hallucinated policy
details, missed mandatory escalations).

## Architecture

```
Customer message
      │
      ▼
┌─────────────────┐     ┌──────────────────────┐
│  RAG retrieval   │────▶│  Structured decision  │
│  (src/rag_engine)│     │  (src/model_client +  │
└─────────────────┘     │   src/schemas)        │
      ▲                  └──────────┬───────────┘
      │                             │
      │                  ┌──────────┴───────────┐
      │                  ▼                       ▼
      │         run_diagnostic             escalate / answer
      │     (src/diagnostics, max 1x    (src/escalation writes
      │      per conversation — code-     a ticket to tickets/)
      │      level policy check)
      └─────────────────┘
      feed result back as new evidence, decide again
      (bounded to MAX_TURNS, src/agent_loop.py)
```

## Tech Stack

* **Language:** Python 3.12+
* **Package manager:** `uv`
* **Vector DB:** ChromaDB (local)
* **Embeddings:** Ollama (`nomic-embed-text`) or OpenAI (`text-embedding-3-small`)
* **LLM:** Ollama (local, e.g. `llama3.2:1b`) or OpenAI — switchable via `.env`, no code change
* **Frameworks:** LangChain (retrieval), Pydantic (structured output/schemas)

## Directory Structure

```text
velo/
├── data/
│   └── technical_docs.txt     # Knowledge base (policies, troubleshooting)
├── docs/
│   └── 00-problem.md          # Problem statement, PEAS, success contract
├── evals/
│   └── cases.jsonl            # Frozen evaluation set (used for every stage)
├── reports/
│   ├── baseline_results.md    # Non-agentic baseline raw output
│   ├── analysis.md            # Baseline failure analysis
│   ├── agent_results.md       # Full agent raw output
│   └── final_evaluation.md    # Baseline vs. agent comparison + limitations
├── src/
│   ├── model_client.py        # Provider-agnostic model boundary (Ollama/OpenAI)
│   ├── schemas.py             # AgentDecision structured output schema
│   ├── rag_engine.py          # Dual-provider RAG engine
│   ├── retrieval_agent.py     # Grounds decisions in retrieved policy
│   ├── diagnostics.py         # Mock router diagnostic tool
│   ├── escalation.py          # Escalation ticket (context package) tool
│   ├── agent_loop.py          # Bounded decide → diagnose → decide loop
│   └── baseline.py            # Non-agentic baseline (for comparison only)
├── tests/                     # One test file per component above
├── tickets/                   # Generated escalation tickets (gitignored)
└── run_eval.py                # Runs the full agent against evals/cases.jsonl
```

## Setup

```bash
uv sync
```

Create a `.env` file:
```
MODEL_PROVIDER=ollama
MODEL_NAME=llama3.2:1b
```
(Swap to `MODEL_PROVIDER=openai` + an `OPENAI_API_KEY` to use OpenAI instead — no code changes needed.)

If using Ollama, make sure the model and the embedding model are pulled:
```bash
ollama pull llama3.2:1b
ollama pull nomic-embed-text
```

## Running

```bash
# Run all tests
uv run pytest -v

# Run the full agent against the frozen eval set and generate the comparison report
uv run python run_eval.py
```

## Project history

Built incrementally, one GitHub-tagged stage at a time — see the
[releases](../../tags) for the full progression from a bare RAG prototype
(v0.1.0) to a fully evaluated agent (v1.0.0), each with its own commits,
tests, and evidence.
