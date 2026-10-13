# Changelog

All notable changes to Velo are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `run_eval.py` writes one report per provider and model (`reports/agent_results_<provider>_<model>.md`)
  and starts it with a summary table scoring the escalate / don't-escalate decision against the eval set.

### Fixed
- `run_eval.py` crashed on a case that failed safely (no decision to print) and overwrote the previous
  model's results on every run. It now reports the failure and keeps results per model.

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
