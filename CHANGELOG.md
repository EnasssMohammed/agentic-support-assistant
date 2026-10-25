# Changelog

All notable changes to Velo are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `is_instruction_override`: deterministic guard that refuses instruction-override and prompt-extraction attempts
  without calling the model or creating a ticket.
- `PROMPT_VERSION`, recorded in evaluation reports; `compare_arms.py` refuses to compare different versions.
- Comparison arms for evaluation v2 (`src/arms.py`, `run_eval_v2.py --arm baseline|rag|agent`) and `compare_arms.py`: the same 38
  frozen cases through a single-call baseline, a retrieval-only arm and the full agent, with a side-by-side table.
- Conversation state (`src/conversation.py`, Pydantic): `VeloAgent.reply(conversation, message)` keeps the messages, the
  diagnostic result and the ticket across customer messages; `run(message)` is still the single-message shortcut.
- Policy Rule #2 enforced in code: a customer still writing after 3 agent replies is escalated automatically
  (the knowledge base required this, but nothing implemented it).
- `AWAITING_CUSTOMER` terminal state for replies that ask a clarifying question; these were reported as `RESOLVED`.
- Escalation tickets now include the diagnostic result and, for multi-turn conversations, the transcript.
- `main.py` is a multi-turn CLI (`/new`, `/quit`).
- Validated settings (`src/settings.py`, Pydantic): `MODEL_PROVIDER`, `MODEL_NAME` and `OPENAI_API_KEY` are checked
  once, with clear errors, instead of being read with `os.getenv` in three places. A missing OpenAI key or a model
  name that does not match the provider now fails at startup instead of mid-run.
- `run_eval.py` writes one report per provider and model (`reports/agent_results_<provider>_<model>.md`)
  and starts it with a summary table scoring the escalate / don't-escalate decision against the eval set.
- `src/intents.py` and `src/responses.py`: deterministic intent detection and customer-facing replies moved out of
  the agent loop. Streamlit UI (`app.py`) with a customer chat and a team console.
- Escalation ticket v2: `escalation_kind`, `priority`, `customer_reply`; `suggested_human_action` is now written for staff.
- `RAGEngine.retrieve_passages()` returns passages with source and distance; optional relevance cutoff
  (`VELO_MAX_DISTANCE`). Retrieved text is labelled with its source.
- `run_router_diagnostic(rng=...)` for reproducible evaluation runs.
- Rotating log file (2 MB x 3).
- Evaluation v2 (`run_eval_v2.py`, `src/eval_metrics.py`, `evals/cases_v2.jsonl`): 38 frozen cases in 10 families,
  repeated runs, pass@1 / pass@k / pass^k, flaky-case list, adversarial suite, blocking release gates and a
  GO / NO-GO decision. `--dry-run` verifies the harness without a model; `--gate` exits 1 on NO-GO.
- Welcome message in the customer chat: Velo introduces itself as an AI assistant and says what it can do.

### Changed
- The customer notice for a model-initiated escalation is deterministic; the model's wording no longer reaches the customer.
- Prompt rule: requests for information are plain sentences, never numbered (numbering is for policy steps).
- Policy Rule 3 is enforced in code: a router issue is diagnosed before any guidance, even when the model answers
  directly or the customer claims a diagnostic result. A real evaluation showed the prompt alone was followed only
  some of the time.
- Release decision has four outcomes: GO, CONDITIONAL GO (only a budget exceeded), NO-GO, INVALID RUN.
- No-evidence cases accept either an admission or a clarifying question, and forbid invented step-by-step instructions.
- Evaluation gates: "diagnostic at most once" and "router issues are diagnosed before guidance" are separate gates;
  latency is measured per reply.
- The prompt says explicitly what to do when the policy has no answer (say so, never invent steps).
- The conversation now remembers its current issue (`topic`, `issue`, `issue_start`). History, retrieval,
  attempt counting, follow-up questions and the ticket are all scoped to that issue, so a login problem is never
  answered with router steps. Retrieval is filtered by topic; the router diagnostic is refused for account and
  billing issues. See `docs/03-issue-tracking.md`.
- The knowledge base is chunked per policy entry instead of fixed 300-character windows, so rules are never cut
  in half. The index rebuilds once automatically.
- Retrieval query includes the original issue, so short follow-ups find the right policy.
- Response-style rules and a data/instructions boundary added to the system prompt.
- A repeated diagnostic request is rejected and the model re-plans, instead of ending the run.

### Security
- A customer's claim of a diagnostic outcome is no longer treated as tool output; only a claimed Hard Fault can
  trigger escalation, and negated claims ("not a hard fault") are ignored.
- Customer text cannot forge the `[DIAGNOSTIC RESULT]` and `[POLICY FEEDBACK]` markers.

### Fixed
- The router diagnostic is an allow-list: it only runs for a router issue. An issue with no recognised topic could run it
  and receive router steps for an unrelated product (eval case `n01`).
- The injected model failure (`f02`) crashed systems that call `generate()`; it now supports both model calls.
- The model could escalate a router issue to a human before any diagnostic had run (a red LED is a symptom, not a
  Hard Fault). The diagnostic now runs first; a confirmed Hard Fault still escalates immediately.
- Evaluation phrase matching ignores Arabic diacritics and alef variants.
- Evaluation false positive: the plain word "exception" in a correct reply was treated as a leak. Leak detection now
  matches stack traces, error class names and API keys only.
- A knowledge-base outage (for example an unreachable embedding service) crashed the agent. It now fails safely
  like a model outage: the customer is asked to resend and no internal error text is shown.
- Escalation no longer depends on retrieval: the ticket is still created, without the policy excerpt, when the
  knowledge base cannot be searched.
- Evaluation: a run hit by network errors is reported as INVALID RUN instead of NO-GO; the run stops after three
  unreachable cases, and a preflight check runs before the first case.
- Topic drift: "still not working" after a login problem produced router instructions.
- A reported Hard Fault inside a "still not working" message was swallowed by the follow-up path.
- A failing diagnostic tool crashed the run; it now escalates with a ticket (`tool_failure`).
- `main.py` crashed when a reply failed safely (no decision to print).
- The diagnostic "at most once per conversation" rule only held within one message; it now holds across the conversation.
- `run_eval.py` crashed on a case that failed safely (no decision to print) and overwrote the previous
  model's results on every run. It now reports the failure and keeps results per model.
- Ticket `suggested_human_action` no longer contains the customer-facing reply.
- When ticket creation fails, the customer is told the case was not transferred.
- Internal error text is never shown to customers.
- Log duplicates when a framework configures the root logger.

## [1.2.0] - 2026-10-12

### Fixed
- `reports/baseline_results.md` is again the raw output of the Stage 1 baseline run, recovered from the
  original commit. The version restored in 1.0.1 was a condensed reconstruction written from a pasted
  copy of that output, not the captured file.
- Creating a second `RAGEngine` in the same process duplicated every chunk of the in-memory index
  (11 became 22), so top-k retrieval could return the same passage more than once.
- A Hard Fault stated by the customer (or returned by the diagnostic tool) now escalates in
  code (Policy Rule #1) instead of depending on the model; previously the model could answer
  `run_diagnostic` to a message that already reported the result. Customer-reported
  diagnostic outcomes are recognised and the tool is not re-run to confirm them.
- Live-model return-window test now asserts the baseline's hallucinated "30 days" is absent.

### Changed
- The knowledge-base index is built once and persisted under `chroma_langchain/<provider>/`, with a
  fingerprint of the source text, provider, embedding model and chunk settings. It is reused until any
  of those change, instead of re-embedding the whole document on every start (measured at about
  40 seconds locally with Ollama and `nomic-embed-text`).
- Dependency updates through Dependabot: `langchain` 1.4.3, `langchain-openai` 1.6.7, `ollama` 0.6.3,
  `python-dotenv` 1.2.4, and the `actions/checkout` v7 and `astral-sh/setup-uv` v7 GitHub Actions.
- `RAGEngine` now follows the `MODEL_PROVIDER` setting in `.env` (via `resolve_provider`),
  so the LLM and the embeddings switch together; previously embeddings were hardcoded to Ollama (#2).

### Added
- Unit tests for provider resolution, the index cache and Hard Fault enforcement.
- Dependabot configuration and this changelog.

## [1.1.0] - 2026-10-10

### Added
- `ModelClientError` and error handling around every model call; provider failures and
  malformed structured output no longer crash a run.
- `FAILED_SAFELY` terminal state and input validation (empty / over-long messages).
- Structured logging to the console and `logs/velo.log`.
- GitHub Actions CI (ruff lint + deterministic unit tests); tests that need a live model are
  marked `requires_llm` and excluded from CI.
- Deterministic agent-loop unit tests using a scripted fake model, including the
  "second diagnostic request is blocked" failure/recovery case.
- MIT `LICENSE` and `.env.example`.

### Changed
- `pyproject.toml` declares `pytest` and `ruff` as dev dependencies and drops unused
  `streamlit` and `langgraph`.
- README updated: CI badge, project structure, test commands, failure handling.

## [1.0.1] - 2026-10-07

### Fixed
- Restored `docs/00-problem.md`, `reports/baseline_results.md` and `reports/analysis.md`,
  which had been lost in an earlier sync issue.
- `main.py` is now a real CLI entry point instead of a stub.

## [1.0.0] - 2026-10-07

### Added
- Final evaluation of the full agent against the Stage 1 baseline (`reports/final_evaluation.md`).

### Fixed
- Diagnostic tool can run at most once per conversation, enforced in code rather than only
  in the prompt.
- RAG retrieval widened from `k=1` to `k=3` (wrong-paragraph retrieval).
- Diagnostic tool restricted to router/connectivity/hardware issues.

## [0.6.0] - 2026-10-06
### Added
- Escalation ticket tool: a JSON context package for the human agent.

## [0.5.0] - 2026-10-06
### Added
- Bounded agent loop (decide, diagnose, decide) with terminal states.

## [0.4.0] - 2026-10-06
### Added
- Mock router diagnostic tool.

## [0.3.0] - 2026-10-06
### Added
- Decisions grounded in retrieved policy (`RetrievalAgent`).

## [0.2.0] - 2026-10-06
### Added
- End-to-end test that the model returns a structured `AgentDecision`.

## [0.1.0] - 2026-10-05
### Added
- Non-agentic baseline, frozen eval set (`evals/cases.jsonl`), provider-agnostic model
  client (Ollama / OpenAI) with structured output, and the `AgentDecision` schema.
- Removed a duplicate `rag_enginge.py`.

[Unreleased]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v0.6.0...v1.0.0
