# Baseline Failure Analysis

The non-agentic baseline (single LLM call, no retrieval, no tools) was run against
7 frozen eval cases in `evals/cases.jsonl`. Full raw output is in
`baseline_results.md`.

## Critical failures

- **n2 (Hard Fault escalation):** Per policy, a Hard Fault diagnostic result must
  be escalated immediately. The baseline instead offered generic self-troubleshooting
  steps and suggested contacting the ISP — it has no awareness of the escalation
  policy because it has no access to `technical_docs.txt`.

- **n5 (return window):** The baseline stated a 30-day return window. This number
  does not appear anywhere in `technical_docs.txt` — it is a hallucinated policy,
  not a grounded one.

- **n3 (digital license refund):** Instead of applying the deny-refund policy for
  digital licenses, the baseline asked clarifying questions it didn't need to ask,
  because it doesn't know the policy exists.

- **e1 (retry-limit escalation):** Policy requires escalation once the retry limit
  is hit. The baseline instead offered to keep trying, directly contradicting the
  policy.

## Conclusion

Every failure traces back to one root cause: the baseline has no access to the
knowledge base, so it fills gaps with plausible-sounding but ungrounded or
incorrect text. This is the evidence that justifies building a retrieval-grounded,
policy-aware agent (Stage 3+) instead of a single LLM call. The fix is verified in
`reports/agent_results.md` and summarized in `reports/final_evaluation.md`.
