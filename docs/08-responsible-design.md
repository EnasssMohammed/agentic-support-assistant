# Responsible design: trust, oversight, audit, framework and supply chain

Scope: Velo as described in `05-release-decision.md` (conditional GO for a supervised demo, NO-GO for production).
Facts quoted here come from the other documents; each section says where. Where something does not exist yet, this
document says so instead of describing it as done.

## 1. Over-trust and under-trust

Two people can trust Velo wrongly: the customer who reads its replies, and the staff member who reads its tickets.
Each can trust too much (over-trust) or too little (under-trust).

| Who | Over-trust looks like | What in the system limits it | Under-trust looks like | What in the system limits it |
|---|---|---|---|---|
| Customer | Believing a fluent reply is a promise: a refund, a closed case, a confirmed hardware fault | No tool can refund or change an account, so the agent cannot do it; what the customer is told about an escalation is a fixed text (`responses.escalation_notice`), not model prose; a customer's own claim of a hard fault is treated as unverified | Ignoring a correct answer and asking for a human every time | Every reply ends in a defined terminal state, and escalation to a person is always available (Policy Rule #2 escalates after 3 agent replies) |
| Staff | Acting on a ticket as if the diagnostic were real, or as if the agent's reasoning were reliable | The diagnostic is simulated and the documents say so; a ticket distinguishes a verified hard fault from a reported one ("NOT verified by the diagnostic tool"); the ticket cites the policy used | Re-reading the whole conversation and ignoring the ticket, which wastes the time the ticket is meant to save | The ticket carries the transcript, the diagnostic result, the policy cited, what the customer was told and a next step written for staff (`src/escalation.py`) |

Facts that justify calibrated, not full, trust (from `05-release-decision.md`, `06-threat-model.md` and
`reports/final_evaluation.md`):

- The frozen suite scores 100% for the final agent, but that suite guided the fixes, so it is a regression result, not an
  estimate of new-case performance. On the held-out suite written afterwards, the attack success rate was 7/85 = 8.2%
  (95% upper bound 16.0%), all in indirect injection through a poisoned knowledge-base entry.
- The local `llama3.2:1b` model gave inconsistent reasoning text even when its final action was right, so the
  `agent_reasoning` field in a ticket is a lead for staff, not evidence.
- The p95 reply latency (40.7 s) is above the 30 s budget; this is an accepted, non-blocking exceedance.

Design rule that follows: the customer is told only what code can guarantee, and staff are shown which facts were
measured and which were claimed.

## 2. Human oversight

Tiers, from `06-threat-model.md` section 5:

| Tier | Actions | Oversight |
|---|---|---|
| READ | `search_policy`, `run_router_diagnostic` | None needed: no side effects |
| WRITE (internal) | `create_escalation_ticket`, `create_approval_request` | A person reads every ticket; staff can close it |
| CONSEQUENTIAL | none exist | Not applicable today |

**If the human does nothing:** the ticket stays open and the customer has already been told the team will follow up.
No action is waiting for approval, so inaction cannot cause a consequential action. This holds only while no
consequential tool exists. The approval record (`src/approval.py`, statuses and reviewer fields) is created beside the
ticket but is not connected to any action. The first consequential tool (a refund, an account change) must be built
with an approval gate that expires into a safe refusal, and that gate does not exist yet.

Oversight of the knowledge base: every Studio upload is reviewed, versioned, audited and reversible, and an optional
`VELO_STUDIO_PIN` protects the page. The PIN is shared and the author name is typed, so this is a demo control, not
authentication (`06-threat-model.md`, T13).

## 3. Audit trail

What exists:

- Tickets (`tickets/*.json`) with timestamp, customer message, transcript, diagnostic result, policy cited, reasoning,
  what the customer was told and a suggested action.
- The Studio audit log and version history for every knowledge-base change.
- An event log (`logs/velo.log`) of decisions and terminal states. It records states and decisions, not message text.

What does not exist: one audit record per agent action that states **why** the action was taken in a stable
`explanation` field (action, inputs, the rule that fired, model or code decision, result). The reasons are in the log
lines and the ticket's `agent_reasoning`, but there is no structured, queryable trail. This is a known gap, listed with
the residual risks; closing it is a small change (append one JSON line per decision from `agent_loop`) and it should
exclude message text to respect T12.

## 4. Framework choice

Velo uses a plain Python loop (`src/agent_loop.py`), not an agent framework. LangChain is used only for retrieval
(embeddings and the Chroma store) and the model boundary; LangGraph was tried in an earlier plan and dropped.

Reasons:

1. **The workflow is known in advance** (retrieve, decide, diagnose if needed, decide again, resolve or escalate), which
   `00-problem.md` calls an agentic workflow, not an open-ended agent.
2. **The rules that matter live in code** (Policy Rules #1 and #2, one diagnostic, one ticket). A framework would not
   remove them and would add a layer between the model's proposal and the check that rejects it.
3. **Testability:** the loop takes any model client, so 305 offline tests run in CI against a scripted fake model.
4. **A single agent is enough:** there is one workflow, one tool-using role and no step that needs a second agent to
   check the first. The replan step is a code-level policy check, not a second model. Adding a second agent would need a
   one-sentence justification of what it can do that a rule in code cannot.

Cost of the choice: no built-in tracing or checkpointing, which is why the audit trail above is a gap.

## 5. Supply chain: packages and models

| Component | Choice | Why | Known risk |
|---|---|---|---|
| Dependency management | `uv` with `uv.lock` | Exact, reproducible versions | None specific |
| Updates | Dependabot (uv and GitHub Actions, weekly) and CI (`ruff`, `pytest`) | Updates arrive as reviewed pull requests that must pass CI | A dependency update can still change model behaviour; live tests run locally only |
| Retrieval | `chromadb`, `langchain`, `langchain-community`, `langchain-ollama`, `langchain-openai` | Local vector store, one retrieval code path for two providers | `langchain-community` is being sunset and the `Chroma` class in it is deprecated; migration to `langchain-chroma` is pending |
| Validation | `pydantic`, `pydantic-settings` | Structured model output and checked settings; a bad key or model name fails at startup | None specific |
| Interface | `streamlit` | Fast demo UI | No authentication |
| Model and embeddings, cloud | OpenAI (`gpt-5-nano-2025-08-07` for the recorded evaluation reports; `text-embedding-3-small`) | Fast enough for repeated evaluation runs | Customer text is sent to the provider (T11) |
| Model and embeddings, local | Ollama (`llama3.2:1b`, `nomic-embed-text`) | Free, private, works offline | Slow and inconsistent reasoning at 1B parameters |

The model name is recorded in each evaluation report, and reports with different model, prompt version or knowledge-base
hash are not compared (`compare_arms.py` refuses).
