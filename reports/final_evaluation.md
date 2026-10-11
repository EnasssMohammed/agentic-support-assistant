# Final Evaluation: Baseline vs. Full Agent

## Summary

| Case | Baseline (Stage 1) | Full Agent (Stage 8) |
|---|---|---|
| n1 (router red light) | Generic advice, no grounding | Escalated — correct given diagnostic returned Hard Fault (see note on randomness below) |
| n2 (stated Hard Fault) | Suggested manual fixes (policy violation) | **Triggered the code-level policy check** (see Failure/Recovery Case below) |
| n3 (digital license refund) | Asked unnecessary questions | Escalated, correctly cited the non-refundable rule |
| n4 (account lockout) | Generic but reasonable | Escalated, but reasoning correctly reached the right policy action (password reset) despite confused rule-citation text |
| n5 (14-day return) | **Hallucinated "30 days"** | Grounded in the real 14-day policy, though reasoning was inconsistent |
| e1 (retry limit) | Did not escalate (policy violation) | Escalated correctly, citing the 3-turn retry rule |
| a1 (ambiguous "fix it") | Asked a clarifying question (correct) | Diagnostic-driven; outcome depends on the random diagnostic result |

## Key improvement: hallucination eliminated

The single clearest result: the baseline invented a 30-day return window that
does not exist anywhere in `technical_docs.txt`. Every agent run that touched
return policy correctly grounded its answer in the real 14-day rule. This is
the direct, measurable benefit of retrieval (Stage 3).

## Failure/Recovery Case (required evidence)

**Case n2** exposed a real failure: the local 1B-parameter model, despite an
explicit system-prompt rule ("do not request another diagnostic once a result
is present"), requested the diagnostic tool a second time in the same
conversation.

Instead of trusting the prompt alone, `src/agent_loop.py` enforces this as a
**code-level policy check**: a `diagnostic_already_run` flag that the LLM
cannot override. When the model violated the rule, the system did not loop
indefinitely or silently retry — it caught the violation and terminated in
`BUDGET_EXHAUSTED`, a defined safe state, rather than taking an unverified
action.

**This demonstrates the required pattern: a policy-check step that can
reject an intermediate model output and force safe termination, with a
documented instance of it actually firing.**

## Known limitations

1. **Model capacity.** The local `llama3.2:1b` model frequently produces
   internally inconsistent reasoning text (citing the wrong rule number while
   still reaching a defensible action). A larger model (`llama3:8b`,
   `gpt-4o-mini`) would likely reason more consistently, at the cost of
   latency (local) or requiring an API key (cloud).
2. **Diagnostic tool randomness.** `run_router_diagnostic()` returns a
   weighted-random result. This is appropriate for testing every branch
   of the agent's logic (Stage 4's goal), but it means a fixed "expected
   action" in `evals/cases.jsonl` for router-related cases isn't always
   the uniquely correct answer — the correct action depends on which
   diagnostic outcome actually occurred that run.
3. **Latency.** Full runs took 35s-320s per case locally. The <60s target
   in `docs/00-problem.md` would need a faster model (local or cloud) for
   production use.

## Conclusion

The agent measurably outperforms the baseline on the dimension that mattered
most in Stage 1's analysis: grounding answers in actual policy instead of
inventing them. It also demonstrates a working safety control (the policy
check) catching a genuine model failure. Remaining inconsistency is
attributable to the small model's reasoning capacity, not the architecture
— the same pipeline with a larger model is expected to show more consistent
reasoning while keeping the same grounding and safety guarantees.

## Addendum (2026-10-10): correction to the n2 analysis

The Failure/Recovery Case above attributes the n2 failure to the small model ignoring
an instruction. That was incomplete. The system prompt itself pushed the model to the
wrong action: its rule said to choose `run_diagnostic` whenever the customer describes a
device problem and no `[DIAGNOSTIC RESULT]` marker is present, but n2's message already
states the result ("Diagnostics came back as a Hard Fault"). The model quoted that rule
in its reasoning when it chose `run_diagnostic`.

The failure went unnoticed because `test_hard_fault_triggers_escalation` needs a live
model and is excluded from CI. It was found when the live tests were re-run after the
Dependabot updates; the same behaviour is visible in the 2026-10-07 evaluation run, so
it is not caused by the dependency updates.

Fix: Policy Rule #1 (a Hard Fault must be escalated immediately) is now enforced in code.
A Hard Fault stated by the customer, or returned by the diagnostic tool, escalates
without depending on the model's decision. The regression is covered by deterministic
tests that run in CI (`tests/test_agent_loop_unit.py`).

The earlier Stage 3 live test for the return window had no assertion, so its PASSED result
verified nothing; it now checks that the baseline's invented "30 days" does not appear.
