# Velo — Agentic Technical Support Assistant

[![CI](https://github.com/EnasssMohammed/agentic-support-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/EnasssMohammed/agentic-support-assistant/actions/workflows/ci.yml)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)

A domain-agnostic, policy-grounded AI support agent, built as an applied
implementation of the Fin.ai agentic pattern: knowledge retrieval, safe
diagnostics, a bounded resolution workflow, and escalation to a human with
a full context package when the agent can't resolve the issue itself.

Implements the Level 2 requirements: knowledge retrieval, diagnostic tools, multi-turn conversation
state, and escalation with a context package. The evaluation compares the agent with a non-agentic
baseline on single-message cases (see [`reports/final_evaluation.md`](reports/final_evaluation.md));
multi-turn behaviour is covered by deterministic unit tests, not by the evaluation set.

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

### Failure handling

Every reply ends in a defined terminal state: `RESOLVED`, `AWAITING_CUSTOMER` (the agent asked a question), `ESCALATED`, `BUDGET_EXHAUSTED`, or `FAILED_SAFELY`. Provider errors and malformed model output are caught (`ModelClientError`), logged, and returned as `FAILED_SAFELY` instead of crashing; the conversation is left exactly as it was, so the customer can resend.

### Conversation state and policy checks

`VeloAgent.reply(conversation, message)` handles one customer message inside a `Conversation` (a Pydantic model holding the messages, the diagnostic result and the ticket), so the agent sees the earlier turns. These policies are enforced in code, not only in the prompt, because small local models do not always follow them:

* **Rule #1:** a Hard Fault, stated by the customer or returned by the diagnostic tool, is escalated immediately.
* **Rule #2:** a customer still writing after 3 agent replies is escalated automatically, and the ticket carries the whole conversation.
* The diagnostic tool runs at most once per conversation, and a conversation that is already escalated never gets a second ticket.

Escalation tickets contain the customer message, the conversation transcript, the diagnostic result, the policy cited, and the agent's reasoning.

## Tech Stack

* **Language:** Python 3.12+
* **Package manager:** `uv`
* **Vector DB:** ChromaDB (local)
* **Embeddings:** Ollama (`nomic-embed-text`) or OpenAI (`text-embedding-3-small`)
* **LLM:** Ollama (local, e.g. `llama3.2:1b`) or OpenAI — switchable via `.env`, no code change
* **Frameworks:** LangChain (retrieval), Pydantic (structured output/schemas)
* **Quality:** pytest, ruff, GitHub Actions CI, structured logging (`logs/velo.log`)

## Directory Structure

```text
velo/
├── .github/workflows/ci.yml   # Lint + deterministic unit tests on every push/PR
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
│   ├── agent_loop.py          # Bounded decide → diagnose → decide loop, per conversation
│   ├── conversation.py        # Conversation state (messages, diagnostic, ticket)
│   ├── logging_config.py      # Console + file logging
│   └── baseline.py            # Non-agentic baseline (for comparison only)
├── tests/                     # Unit tests (fake model, run in CI) + LLM tests (local only)
├── tickets/                   # Generated escalation tickets (gitignored)
├── .env.example               # Required environment variables
├── LICENSE                    # MIT
└── run_eval.py                # Runs the full agent against evals/cases.jsonl
```

## Setup

```bash
uv sync
```

Copy `.env.example` to `.env` and adjust it:
```
MODEL_PROVIDER=ollama
MODEL_NAME=llama3.2:1b
```
(Swap to `MODEL_PROVIDER=openai` + an `OPENAI_API_KEY` to use OpenAI instead — no code changes needed.)
Settings are validated at startup (`src/settings.py`), so a missing key, or a model name that does not match the
provider, fails immediately with a clear message.

If using Ollama, make sure the model and the embedding model are pulled:
```bash
ollama pull llama3.2:1b
ollama pull nomic-embed-text
```

## Running

```bash
# Fast, deterministic tests (no model needed - this is what CI runs)
uv run pytest -m "not requires_llm" -v

# Everything, including end-to-end tests that call a live Ollama/OpenAI model (slow)
uv run pytest -v

# Lint
uv run ruff check .

# Run the full agent against the frozen eval set and generate the comparison report
uv run python run_eval.py
# -> writes reports/agent_results_<provider>_<model>.md, with an escalation-match summary
```

## Project history

Built incrementally, one GitHub-tagged stage at a time — see the
[releases](../../tags) for the full progression from a bare RAG prototype
(v0.1.0) to a fully evaluated agent (v1.0.0), each with its own commits,
tests, and evidence.
