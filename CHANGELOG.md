# Changelog

All notable changes to Velo are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed
- A Hard Fault stated by the customer (or returned by the diagnostic tool) now escalates in
  code (Policy Rule #1) instead of depending on the model; previously the model could answer
  `run_diagnostic` to a message that already reported the result. Customer-reported
  diagnostic outcomes are recognised and the tool is not re-run to confirm them.
- Live-model return-window test now asserts the baseline's hallucinated "30 days" is absent.

### Changed
- `RAGEngine` now follows the `MODEL_PROVIDER` setting in `.env` (via `resolve_provider`),
  so the LLM and the embeddings switch together; previously embeddings were hardcoded to Ollama (#2).

### Added
- Unit tests for provider resolution.
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

[Unreleased]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/EnasssMohammed/agentic-support-assistant/compare/v0.6.0...v1.0.0
