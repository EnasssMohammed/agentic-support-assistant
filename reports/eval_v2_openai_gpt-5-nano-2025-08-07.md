# Velo evaluation v2 (agent): openai / gpt-5-nano-2025-08-07

- Date: 2026-10-25T23:19:45+00:00
- Cases: 38 / 38 run, 5 run(s) each
- Cases file: `evals\cases_v2.jsonl`

## Release decision: **CONDITIONAL GO**

Budgets exceeded. Record in the release notes why this is acceptable:
- p95 reply latency <= 30s (budget)

## Gates

| Gate | Type | Result | Detail |
|---|---|---|---|
| No unexpected or missing tickets | blocking | pass | 0 violation(s) |
| Diagnostic tool used at most once per conversation | blocking | pass | 0 violation(s) |
| Router issues are diagnosed before guidance | blocking | pass | 0 violation(s) |
| No unsupported or leaked content in replies | blocking | pass | 0 violation(s) |
| No unhandled errors | blocking | pass | 0 run(s) |
| Adversarial suite passes every run (pass^5 = 100%) | blocking | pass | 9 adversarial case(s) |
| pass@1 >= 80% | budget | pass | 100.0% |
| p95 reply latency <= 30s | budget | **FAIL** | 40.7s |

## Scorecard

| Family | Cases | pass@1 | pass@5 | pass^5 |
|---|---|---|---|---|
| **All** | 38 | 100.0% | 100.0% | 100.0% |
| account | 3 | 100.0% | 100.0% | 100.0% |
| adversarial | 8 | 100.0% | 100.0% | 100.0% |
| ambiguous | 2 | 100.0% | 100.0% | 100.0% |
| connectivity | 6 | 100.0% | 100.0% | 100.0% |
| escalation | 6 | 100.0% | 100.0% | 100.0% |
| multiturn | 2 | 100.0% | 100.0% | 100.0% |
| no_evidence | 2 | 100.0% | 100.0% | 100.0% |
| refund | 4 | 100.0% | 100.0% | 100.0% |
| resolution | 3 | 100.0% | 100.0% | 100.0% |
| tool_failure | 2 | 100.0% | 100.0% | 100.0% |

Latency per reply: p50 14.0s, p95 40.7s.

Flaky cases (pass some runs, fail others): none
Always failing: none

## Failures

None.