# Knowledge base: known gaps

Scope: `data/technical_docs.txt`, the built-in manual that is the live knowledge base and the only one the evaluation
reports cover (`07-knowledge-studio.md`, "Evaluation after a change"). This file is documentation only: it is not read
by the agent, and the manual was deliberately left unchanged so that the evidence in `reports/` still describes the
knowledge base the agent answers from. Each gap says what it affects and how Velo behaves today.

## 1. Ambiguous or loosely worded rules

| # | Gap | Effect today |
|---|---|---|
| 1 | "Interaction turn" in Policy Rule #2 is not defined | The code defines it as three agent replies (`agent_loop`); the manual does not say so |
| 2 | The Error 500 entry ends with a restart and does not say what happens if that fails | Escalation then comes only from Rule #2, not from the entry itself |
| 3 | "Software Glitch" is described as recoverable by remote reboot, firmware update or cache reset | Velo has no tool for any of these; it can only guide the customer or escalate |
| 4 | Section 2 is titled "Critic policy" but no critic is described | The replan step is a code-level policy check, not a described critic |
| 5 | Rule #1 names an internal tool (`create_escalation_ticket`) inside a customer policy | Mixes policy with implementation; harmless to behaviour |
| 6 | Locked account: "trigger automated reset link" does not say who triggers it or how identity is checked | Velo has no such tool; it can only tell the customer what the policy says |
| 7 | Terms are borrowed from other domains ("Error 500", "Network Card or Motherboard" for a router) | Wording only |

## 2. Missing policy

| # | Missing | Risk |
|---|---|---|
| 1 | Warranty or cover for a hardware fault after the 14-day window | The agent has nothing to cite and could promise or refuse without support |
| 2 | What is refundable: devices versus services, opened devices, and who performs the refund | Vague answers; Velo can never perform a refund (no consequential tool) |
| 3 | Response time after escalation | The customer is told the team will follow up, with no time |
| 4 | Exceptions to waiting for three turns (wide outage, account security) | Urgent cases follow the normal path |
| 5 | A list of what is out of scope | Out-of-scope questions are handled only by the prompt |
| 6 | Arabic text: the manual is English only, the customers write Arabic | Retrieval depends on cross-language embeddings; `run_retrieval_check.py` measures it |

## 3. Conflicts with the sample policy files

The three files in `data/` other than the manual (`Account_And_Billing_Policy.txt`,
`Escalation_Rules_And_Limits.md`, `Network_Troubleshooting_Guide.md`) are not part of the live knowledge base unless
someone publishes them in the Studio. They disagree with the manual:

| Topic | Manual | Sample files |
|---|---|---|
| Red Internet LED | Error 500: restart the router, check the WAN cable | Unpaid bill (account policy); PPPoE authentication error (network guide) |
| "Rule #1" and "Rule #2" | Hard fault; three turns | Fibre cut; more than two reset attempts; a third rule about an open ticket within 24 hours |
| Password reset | Link by email | OTP to the registered mobile |
| Hardware replacement | Hard fault: escalate to staff at once | Replacement delivered within 48 hours |
| Tools implied | None beyond the diagnostic and the ticket | Port soft reset, TR-069 rewrite, replacement permit |

The Studio review flags the Rule #1 and Rule #2 overlaps. For the rest, the documents must be rewritten so that they
describe what the support team does, not what Velo does, before they are published (`07-knowledge-studio.md`).

## 4. Decision and next step

- Decision (2026-11-08): the supervised demo and the evaluation use the built-in manual alone. The sample files stay in
  the repository as material for the Studio and are covered by tests, but are not published.
- Next step: resolve the gaps above in a pull request (one entry per gap), add a pricing and warranty document through
  the Studio, then re-run `run_eval_v2.py --with-uploads --runs 5` so that the reports match the live knowledge base.
  Until then, a claim about Velo's answers applies to the built-in manual only.
