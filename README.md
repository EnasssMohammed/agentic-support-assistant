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
├── .github/
│   ├── workflows/ci.yml       # Lint + deterministic unit tests on every push/PR
│   └── dependabot.yml         # Weekly dependency updates (uv + GitHub Actions)
├── app.py                     # Streamlit platform: Home, Velo Agent, Team Inbox, Knowledge Management Studio
├── main.py                    # Multi-turn command-line interface
├── data/                      # Knowledge base sources (policies, troubleshooting); technical_docs.txt is the core file
├── docs/
│   ├── 00-problem.md          # Problem statement, PEAS, success contract
│   ├── 02-evaluation-v2.md    # Evaluation v2: arms, k runs, release gates
│   ├── 03-issue-tracking.md   # Issue tracking
│   ├── 04-code-map.md / .en.md  # Every file and how they relate (Arabic / English)
│   ├── 05-release-decision.md # Release decision
│   ├── 06-threat-model.md     # Threat model, tool inventory, residual risk
│   ├── 07-knowledge-studio.md # Knowledge Management Studio
│   ├── 08-responsible-design.md # Over/under-trust, human oversight, framework and supply-chain choices
│   └── 09-knowledge-base-gaps.md # Known gaps in the manual and conflicts with the sample policy files
├── evals/
│   ├── cases.jsonl            # Legacy stage-1 cases (6)
│   ├── cases_v2.jsonl         # Frozen evaluation suite (38 cases); hashes in frozen.json
│   └── cases_v3_heldout.jsonl # Held-out adversarial suite (17 cases)
├── knowledge/                 # Studio state: published documents, history, audit log (gitignored)
├── reports/                   # Baseline, agent and v2 evaluation reports (final_evaluation.md is the summary)
├── src/
│   ├── agent_loop.py          # Bounded decide → diagnose → decide loop, per conversation; policy rules in code
│   ├── conversation.py        # Conversation state (messages, diagnostic, ticket, topic)
│   ├── intents.py             # Deterministic intent / topic / override detection
│   ├── responses.py           # Fixed customer-facing replies
│   ├── topic_classifier.py    # Model-based topic fallback for unknown keywords
│   ├── retrieval_agent.py     # Grounds decisions in retrieved policy; system prompt
│   ├── rag_engine.py          # Dual-provider RAG engine; chunks by entry or by heading, over several files
│   ├── model_client.py        # Provider-agnostic model boundary (Ollama/OpenAI)
│   ├── schemas.py             # AgentDecision structured output schema
│   ├── settings.py            # Validated environment settings
│   ├── diagnostics.py         # Mock router diagnostic tool
│   ├── escalation.py          # Escalation ticket (context package) tool
│   ├── approval.py            # Human approval records (not yet connected to an action)
│   ├── knowledge.py           # Studio backend: review, publish, rollback, audit
│   ├── arms.py                # Evaluation arms: baseline, retrieval-only, full agent
│   ├── eval_metrics.py        # pass@k, case checks, gates, attack success rate
│   ├── logging_config.py      # Console + file logging
│   └── baseline.py            # Non-agentic baseline (for comparison only)
├── ui/                        # Streamlit pages: pages.py (home, customer, inbox), knowledge.py (Studio),
│                              # tickets.py, runtime.py (agent wiring), theme.py
├── tests/                     # Unit tests (fake model, run in CI) + LLM tests (local only)
├── tickets/                   # Generated escalation tickets (gitignored)
├── .env.example               # Required environment variables
├── LICENSE                    # MIT
├── CHANGELOG.md
├── run_eval_v2.py             # Evaluation v2 runner; compare_arms.py compares the arms
├── run_retrieval_check.py     # Retrieval accuracy check (optional)
└── run_eval.py                # Legacy stage-1 evaluation
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

## The Velo platform and the Knowledge Management Studio

```bash
uv run streamlit run app.py
```

Home, Velo Agent (the customer view), Team Inbox (escalated tickets) and the **Knowledge Management Studio**, where staff
upload, write, review, publish, version and audit the policies the agent answers from. Publishing indexes the new
knowledge base first and undoes itself if that fails. Set `VELO_STUDIO_PIN` in `.env` to protect the page. See
[docs/07-knowledge-studio.md](docs/07-knowledge-studio.md) for the checks, the limits and how to re-run the evaluation
against the published documents (`run_eval_v2.py --with-uploads`).

## Project history

Built incrementally, one GitHub-tagged stage at a time — see the
[releases](../../tags) for the full progression from a bare RAG prototype
(v0.1.0) to a fully evaluated, security-reviewed agent, each with its own commits,
tests, and evidence.
