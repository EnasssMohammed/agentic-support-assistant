# Release decision: Velo evaluation candidate

Date: 2026-10-25. Model: `gpt-5-nano-2025-08-07` (OpenAI). Prompt version: 2. Suite: `evals/cases_v2.jsonl`, 38 frozen cases, k = 5.

## Decision

**CONDITIONAL GO for a supervised demo. NO-GO for production use.**

## Evidence

| Measure | baseline | rag | agent (final) |
|---|---|---|---|
| pass@1 | 41.1% | 50.0% | 100.0% |
| pass^5 (every one of 5 runs passes) | 34.2% | 39.5% | 100.0% |
| p95 reply latency | 14.7 s | 25.3 s | 40.7 s |

- Every blocking gate passes for the agent: no unexpected or missing tickets, diagnostic at most once, router issues
  diagnosed before guidance, no unsupported or leaked content, no unhandled errors, adversarial suite 100% in every run.
- The only failing gate is the p95 latency budget (30 s). It is not blocking.
- 177 offline unit tests pass in CI (`uv run pytest -m "not requires_llm"`).
- `baseline` and `rag` are comparison arms, never release candidates. See `02-evaluation-v2.md` for the per-family
  table and for the three defects found and fixed on the way (`x03`, `n01`, `n02`).

## Allowed

- Answering Arabic and English support questions from the knowledge base, in a supervised demo.
- Running the (simulated) router diagnostic for router and connectivity issues, at most once per conversation.
- Handing a case to a human with a ticket that carries the diagnostic, the policy cited and the transcript.
- Refusing instruction-override and prompt-extraction attempts without calling the model.

## Not allowed

- Any consequential action: refunds, account changes, credentials. Velo has no tool for them, and the approval record
  that accompanies each ticket is not yet connected to any action.
- Production traffic, several customers at once, or real customer data.
- Treating the diagnostic result as real: the tool is simulated.

## Accepted exceedance

p95 reply latency is 40.7 s against the 30 s evaluation budget. The success contract (`00-problem.md`) targets under
60 s, which this meets. Accepted for a demo; to be revisited before any live use.

## Remaining risks (known, not yet measured)

The threat model (`06-threat-model.md`) lists each threat with its controls, evidence and residual risk.

- A poisoned knowledge-base passage (indirect prompt injection) and instructions hidden in a tool result are not tested.
- Isolation between two customers' conversations is assumed, not tested.
- Topic detection is keyword-based (`src/intents.py`); paraphrases outside the keyword lists fall back to the model.
- The 100% was reached on the suite that guided the fixes. It is a regression result, not an unbiased estimate.
- One model, one provider, k = 5. A different model needs a new run of all three arms.
- No structured trace: logs exist, but there is no run id, and prompt, model and index versions are only recorded in
  evaluation reports.
- No kill switch, no rate limit, no token or cost budget.

## Monitoring and rollback (demo)

- Monitoring: application logs and the tickets created. A person reads every ticket.
- Rollback: revert to the previous commit; CI runs the tests on every pull request. There is no automated rollback.

## Owner and next review

- Owner: Enas Mohammed
- Next review: [2026-11-15]. Re-run all three arms whenever the model, the prompt version, the knowledge base or the
  cases change, and review this file with the new numbers.
