# Arm comparison: openai / gpt-5-nano-2025-08-07

- Cases: 38 frozen cases (`evals\cases_v2.jsonl`), 5 run(s) each
- Same cases, same model, same deterministic checks for every arm.

## Overall

| Measure | baseline | rag | agent |
|---|---|---|---|
| pass@1 | 41.1% | 50.0% | 100.0% |
| pass@5 (capability) | 50.0% | 52.6% | 100.0% |
| pass^5 (reliability) | 34.2% | 39.5% | 100.0% |
| Flaky cases | 6 | 5 | 0 |
| Always failing | 19 | 18 | 0 |
| Latency p95 per reply | 14.7s | 25.3s | 40.7s |
| Blocking gates passed | 2/6 | 2/6 | 6/6 |
| Decision | n/a (ablation) | n/a (ablation) | CONDITIONAL GO |

## pass^5 by family

| Measure | baseline | rag | agent |
|---|---|---|---|
| adversarial | 37.5% | 37.5% | 100.0% |
| escalation | 16.7% | 16.7% | 100.0% |
| no_evidence | 50.0% | 50.0% | 100.0% |
| connectivity | 16.7% | 0.0% | 100.0% |
| refund | 0.0% | 75.0% | 100.0% |
| tool_failure | 100.0% | 100.0% | 100.0% |
| account | 66.7% | 100.0% | 100.0% |
| ambiguous | 0.0% | 0.0% | 100.0% |
| multiturn | 100.0% | 100.0% | 100.0% |
| resolution | 33.3% | 0.0% | 100.0% |

## How to read this

- `baseline` has no retrieval, tools, state or policy. Its failures are the problem statement.
- `rag` adds grounded retrieval and history but no tools and no code-level policy. The gap between `baseline` and `rag` is what retrieval buys; the gap between `rag` and `agent` is what tools, state and enforced policy buy.
- Ablation arms cannot create tickets or run diagnostics, so they fail those checks by construction. Judge them on the families where that is not the whole story (no_evidence, refund, adversarial).
- A larger cost or latency with no gain would be a valid conclusion too: report it either way.
