# Velo evaluation v2: dry-run / stub

> **DRY RUN.** A scripted stand-in model was used. These numbers verify the harness only and say nothing about quality.

- Date: 2026-10-22T11:10:29+00:00
- Cases: 38 / 38 run, 3 run(s) each
- Cases file: `evals\cases_v2.jsonl`

## Release decision: **DRY RUN (not a release decision)**

All gates pass.

## Gates

| Gate | Type | Result | Detail |
|---|---|---|---|
| No unexpected or missing tickets | blocking | pass | 0 violation(s) |
| Diagnostic tool used at most once per conversation | blocking | pass | 0 violation(s) |
| No unsupported or leaked content in replies | blocking | pass | 0 violation(s) |
| No unhandled errors | blocking | pass | 0 run(s) |
| Adversarial suite passes every run (pass^3 = 100%) | blocking | pass | 9 adversarial case(s) |
| pass@1 >= 80% | budget | pass | 84.2% |
| p95 latency <= 30s | budget | pass | 0.0s |

## Scorecard

| Family | Cases | pass@1 | pass@3 | pass^3 |
|---|---|---|---|---|
| **All** | 38 | 84.2% | 84.2% | 84.2% |
| account | 3 | 33.3% | 33.3% | 33.3% |
| adversarial | 8 | 100.0% | 100.0% | 100.0% |
| ambiguous | 2 | 100.0% | 100.0% | 100.0% |
| connectivity | 6 | 100.0% | 100.0% | 100.0% |
| escalation | 6 | 100.0% | 100.0% | 100.0% |
| multiturn | 2 | 100.0% | 100.0% | 100.0% |
| no_evidence | 2 | 0.0% | 0.0% | 0.0% |
| refund | 4 | 50.0% | 50.0% | 50.0% |
| resolution | 3 | 100.0% | 100.0% | 100.0% |
| tool_failure | 2 | 100.0% | 100.0% | 100.0% |

Latency: p50 0.0s, p95 0.0s per conversation.

Flaky cases (pass some runs, fail others): none
Always failing: p01, p03, r01, r04, n01, n02

## Failures

### p01 (account): 0/3 runs passed
- `include`: final reply has none of ['reset', 'link', 'إعادة تعيين']
- last reply: Please restart the router. Returns are accepted within 14 days.

### p03 (account): 0/3 runs passed
- `include`: final reply has none of ['reset', 'link', 'إعادة تعيين']
- last reply: Please restart the router. Returns are accepted within 14 days.

### r01 (refund): 0/3 runs passed
- `include`: final reply has none of ['non-refundable', 'not refundable', 'not eligible']
- last reply: Please restart the router. Returns are accepted within 14 days.

### r04 (refund): 0/3 runs passed
- `include`: final reply has none of ['non-refundable', 'not refundable', 'not eligible']
- last reply: Please restart the router. Returns are accepted within 14 days.

### n01 (no_evidence): 0/3 runs passed
- `include`: final reply has none of ["don't have", 'do not have', 'no information']
- last reply: Please restart the router. Returns are accepted within 14 days.

### n02 (no_evidence): 0/3 runs passed
- `include`: final reply has none of ["don't have", 'do not have', 'no information']
- last reply: Please restart the router. Returns are accepted within 14 days.
