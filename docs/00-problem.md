# Velo — Problem Definition

## Problem Statement
Velo is a general-purpose technical-support agent. Given a customer's issue about
any supported product or service, it retrieves the relevant documentation from a
governed knowledge base, runs safe read-only diagnostics, attempts a bounded
resolution workflow, and — when it cannot resolve the issue — escalates to a human
agent with a pre-filled ticket containing full context. It never invents information
and never takes irreversible actions without authority.

## Why This Needs an Agent
A single LLM call cannot: retrieve the right policy, run a diagnostic, check whether
the result requires escalation per policy, and decide the next step based on that
result. This requires a loop that observes tool output and decides again. This is
demonstrated empirically in `reports/baseline_results.md` and
`reports/analysis.md`: a single-call baseline invents policy details that don't
exist (a hallucinated 30-day return window vs. the real 14-day policy) and fails
mandatory escalations (suggesting manual fixes for a Hard Fault instead of
escalating immediately).

## Success Contract

| Dimension     | Target                                                        |
|---------------|-----------------------------------------------------------------|
| Task success  | Issue resolved with evidence traceable to `technical_docs.txt`  |
| Tool correctness | Correct diagnostic/tool called with correct arguments         |
| Safety        | No account/record writes; only ticket creation is a "write"     |
| Termination   | Every run ends in a defined terminal state                      |
| Cost          | ≤ 3 turns, ≤ 1 diagnostic call per conversation                 |
| Latency       | Target < 60s per run (not yet met locally — see `reports/final_evaluation.md`) |
| Human oversight | Escalation tickets (`tickets/*.json`) are reviewable before any follow-up action |

Terminal states (implemented in `src/agent_loop.py`): `RESOLVED`, `ESCALATED`,
`BUDGET_EXHAUSTED`.

## PEAS
- **Performance:** correct answers grounded in the knowledge base; correct escalation
  decisions per the policies in `technical_docs.txt`.
- **Environment:** customers, the knowledge base, a mock diagnostic tool, human
  support agents who receive escalated tickets.
- **Actuators:** search the knowledge base, run a diagnostic, create an escalation
  ticket. (Asking a clarifying question is implemented as a response type, not a
  separate actuator.)
- **Sensors:** the user's message, retrieved passages, diagnostic tool output,
  conversation state so far.

## Agency Level
Velo is an **agentic workflow**, not an open-ended agent. The high-level sequence
(retrieve → decide → diagnose if needed → decide again → resolve/escalate) is known
in advance. Autonomy is bounded to: whether a diagnostic is needed, whether retrieved
evidence is sufficient, and whether to escalate. This is justified because the domain
has clear, enumerable policies (see `technical_docs.txt`) rather than open-ended
judgement calls.

A code-level policy check (not just a prompt instruction) in `src/agent_loop.py`
enforces that the diagnostic tool runs at most once per conversation — this was
added after evaluation showed the model does not always follow that rule reliably
on its own (see `reports/final_evaluation.md`, "Failure/Recovery Case").
