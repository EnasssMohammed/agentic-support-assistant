# Code map: every file, its purpose and how the files relate

Arabic version: [04-code-map.md](04-code-map.md)

Curriculum reference: chapter 5 (structure and boundaries between layers) and section 14.3 (repository boundaries).

## The core idea

**The model proposes, the code decides.** The model reads the message and the policy and proposes a
decision (answer, diagnose, ask, escalate). The code checks the decision and carries it out, and it
rejects or changes the decision when it breaks a rule.

## The journey of one message

Example: the customer writes "I cannot log in to my account".

```
ui/pages.py ──► src/agent_loop.py (the brain)
                 ├─ conversation.py     stores the message, knows the current issue
                 ├─ intents.py          classifies the topic (account / router / billing)
                 ├─ retrieval_agent.py ─► rag_engine.py    fetches the policy for that topic
                 │                      └► model_client.py  asks the model, in a fixed shape (schemas.py)
                 ├─ rules in code       reject or change the model's decision
                 ├─ diagnostics.py      the only tool: the router check
                 ├─ escalation.py       writes the ticket file ─► approval.py (approval request)
                 └─ responses.py        writes the fixed replies in one consistent voice
```

`ui/pages.py` then shows the reply, and the ticket appears in the Team Inbox through `ui/tickets.py`.

## 1) The agent core: `src/`

| File | Purpose | Relations |
|---|---|---|
| `agent_loop.py` | The most important file. Runs the conversation: validates input, tracks the issue, and applies the rules: escalate after 3 attempts, Hard Fault immediately, diagnose before guiding, only one diagnostic | Calls every file below |
| `conversation.py` | The memory: messages, diagnostic result, ticket, and the current issue's topic and starting point | Used by `agent_loop` and `ui` |
| `schemas.py` | The shape of the model's decision, `AgentDecision` (action, reasoning, whether to escalate, reply). Forces JSON instead of free text | Used by `model_client` and `retrieval_agent` |
| `intents.py` | Deterministic keyword decisions: did the customer confirm the fix? Is the problem still there? What is the topic? Which evidence is missing? | Used by `agent_loop` and `rag_engine` |
| `responses.py` | The fixed Arabic replies (escalation, asking for details, resolved) and step formatting | Used by `agent_loop` |
| `retrieval_agent.py` | Builds the request to the model (policy + issue history + message) and holds the system prompt and its rules | Calls `rag_engine` and `model_client` |
| `rag_engine.py` | The knowledge base: splits `technical_docs.txt` entry by entry, embeds it, and searches by topic | Reads `data/`, stores in `chroma_langchain/` |
| `model_client.py` | The model boundary: one interface for OpenAI or Ollama, plus `ModelClientError` | Called by `retrieval_agent` |
| `settings.py` | Reads `.env` and validates it once (provider, model, key) | Used by `model_client` and `rag_engine` |
| `diagnostics.py` | The mock check (ok / software glitch / hardware fault) and reading the customer's claims | Called by `agent_loop` |
| `escalation.py` | Writes the ticket JSON: the issue, the evidence, what the customer was told, and the next step for staff | Writes to `tickets/` |
| `approval.py` | Human approval requests for protected actions. The request is created, but nothing waits on it yet | Writes to `approval_requests/` |
| `logging_config.py` | Event log to the screen and to `logs/velo.log` | Used by everything |
| `baseline.py` | The simple agent (one call, no tools). Kept only for the historical comparison | Stage 1 |

## 2) The interfaces

| File | Purpose |
|---|---|
| `app.py` | Entry point: the sidebar and navigation between pages |
| `ui/pages.py` | The pages: Home, Velo Agent (customer), Team Inbox (staff) |
| `ui/theme.py` | The design (CSS) and icons |
| `ui/tickets.py` | Reads the files in `tickets/` and keeps each ticket's status (new, in progress, closed) |
| `main.py` | Command-line interface for quick tries |
| `.streamlit/config.toml` | Streamlit colours (optional) |

The agent writes the ticket to `tickets/` and the team reads the same files, so there is no database between them.

## 3) Evaluation (chapter 11)

| File | Purpose |
|---|---|
| `run_eval_v2.py` | The current runner: repeats each case k times and writes the report and the release decision |
| `src/eval_metrics.py` | The calculations: pass@k, case checks, gates and the decision |
| `evals/cases_v2.jsonl` | 38 frozen cases in ten families, 8 of them adversarial |
| `run_retrieval_check.py` | Measures retrieval accuracy in Arabic and English (optional) |
| `run_eval.py` and `evals/cases.jsonl` | The old evaluation (7 cases), kept for the historical comparison |
| `reports/` | Reports of each run (release evidence) |

## 4) Data and configuration

| File | Purpose |
|---|---|
| `data/technical_docs.txt` | The only knowledge source. Editing it rebuilds the index automatically |
| `.env` and `.env.example` | Secrets and options: `MODEL_PROVIDER`, `MODEL_NAME`, `OPENAI_API_KEY`. The first is never pushed to Git |
| `pyproject.toml` and `uv.lock` | Dependencies with pinned versions |
| `chroma_langchain/`, `tickets/`, `approval_requests/`, `logs/` | Generated at run time, never pushed to Git |

## 5) Tests: what each file guards

| File | Guards |
|---|---|
| `test_agent_loop_unit.py` | The core loop with a scripted model |
| `test_conversation.py` | Memory, escalation after 3 replies, and the command-line interface |
| `test_issue_tracking.py` | Topics never mix, plus the "diagnose first" and escalation rules |
| `test_intents.py` | Topic and evidence classification in Arabic and English |
| `test_diagnostics.py`, `test_escalation.py`, `test_approval.py` | The tools, tickets and approvals |
| `test_rag_index_cache.py`, `test_rag_provider.py`, `test_rag_splitting.py` | The index, the provider and how the knowledge base is split |
| `test_eval_metrics.py`, `test_run_eval.py` | The evaluation calculations (new and old) |
| `test_settings.py` | Settings validation |

Tests marked `requires_llm` need a live model, so CI leaves them out.

## 6) Documentation and project files

| File | Purpose |
|---|---|
| `README.md` | The entry point |
| `CHANGELOG.md` | What changed in each release |
| `docs/` | One document per step: the problem, evaluation, issue tracking, and this map |
| `.github/workflows/ci.yml` | Runs the lint and the tests on every push |
| `.github/dependabot.yml` | Dependency updates |
| `update_old_tests.py` | Temporary: used once, safe to delete |

## Three rules that explain most of the code

1. **Dependencies point one way:** the interface, then `agent_loop`, then the tools and retrieval,
   then the model boundary. A lower file never imports a higher one, so each layer can be tested alone.
2. **Every control lives in code, not in the prompt:** a rule such as "diagnose first" used to live
   in the prompt only. The evaluation showed the model does not always follow it, so it moved into `agent_loop`.
3. **Everything that can fail has a safe path:** an outage of the model, the retrieval or the tool ends
   in an honest reply and, when needed, a ticket, never in a crash.

## Suggested reading order (about an hour)

1. `schemas.py` (two minutes): the shape of a decision.
2. `conversation.py`: what is remembered.
3. `agent_loop.py`: start with `reply`, then `_decide_loop`. This is the heart.
4. `retrieval_agent.py`: the system prompt and how the request is built.
5. `escalation.py`, then `ui/tickets.py`: how a ticket reaches the team.
6. `test_issue_tracking.py`: explains the intended behaviour with live examples, and is the best documentation of the rules.

## If you change something, what else to update

| Change | Also update |
|---|---|
| A new rule in `agent_loop` | A test in `test_issue_tracking.py` and a case in `cases_v2.jsonl` |
| A new entry in `technical_docs.txt` | `test_rag_splitting.py` (entry count and topic tag) |
| New topic words in `intents.py` | `test_intents.py` |
| New reply text in `responses.py` | The cases that check reply phrases in `cases_v2.jsonl` |
| A new release | `CHANGELOG.md` and a Git tag |
