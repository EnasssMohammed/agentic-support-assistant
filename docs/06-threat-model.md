# Threat model

Scope: Velo as evaluated in `05-release-decision.md` (supervised demo). Principle: **the model proposes, the code
decides.** Everything the model reads (customer text, retrieved passages, tool results) is data, never instructions.

## 1. Trust boundaries

```
Customer (untrusted)
   |  message
   v
input validation (length cap) -> instruction-override guard -> agent loop (code) <-> model (output untrusted)
                                                                 ^        ^
                  retrieved passages (data) <- knowledge base    |        |  diagnostic result (data) <- router tool (simulated)
                                                                 v
                                      tickets + approval records (files) -> human staff (Team Inbox, no authentication in the demo)
```

Three boundaries matter: customer to code, retrieved text and tool output to the model, and model output to action.
Only code crosses the last one.

## 2. Assets and actors

| Asset | Why it matters |
|---|---|
| A1 Customer data: messages, tickets, transcripts | Confidentiality between customers |
| A2 What the agent promises: refunds, tickets, "your case is closed" | Integrity: a false promise is a harm |
| A3 Provider API key | Confidentiality |
| A4 System prompt and policy logic | Low value alone, but a leak helps the next attack |
| A5 Knowledge base | Integrity: it is the policy the agent obeys |
| A6 Human agents' time | Availability: tickets are work |

Actors: a malicious customer; a curious customer after another customer's data; the author of a poisoned knowledge-base
entry; a buggy or compromised tool; a dependency or the model provider.

## 3. Threats, controls, evidence

| ID | Threat | Controls (code) | Evidence | Residual risk |
|---|---|---|---|---|
| T1 | Direct instruction override or prompt extraction | `SECURITY BOUNDARY` in the prompt; `is_instruction_override` answers with a fixed refusal without calling the model or creating a ticket | `x03`, `x07`, `x08`; held-out `h09`-`h12`, `h16` | The guard is keyword-based. A new wording reaches the model, where only the prompt protects (measured in `h09`-`h12`, `h16`) |
| T2 | Forged system markers or a claimed diagnostic in customer text | `_neutralize_markers`; a customer claim never replaces a tool result (only the safe direction, "hard fault", may escalate) | `x01`, `x02` | Other forgeries are untested |
| T3 | **Indirect injection** through a retrieved passage | The prompt labels `<retrieved_policy>` as data; refusals, tickets and state come from code, not from the model's text | held-out `h01`-`h04` (policy override, forced escalation, exfiltration image, prompt leak) | The model still writes the answer from the passage; retrieved text is not sanitised. Write access to the knowledge base is a PR to the repository, with no other access control |
| T4 | **Tool-output injection**: instructions inside the diagnostic's free-text field | The tool returns a typed status; state (`RESOLVED`, tickets) is set by code | held-out `h05`, `h06` | The real tool may return free text. It would need the same treatment as retrieved text |
| T5 | Ticket flooding or false escalation | One ticket per conversation; the escalation notice is deterministic; override attempts never create tickets | `x03`, held-out `h02`, `h15` | No rate limit across conversations, no authentication |
| T6 | Secret exfiltration (API key, `.env`, prompt) | The key is a validated `SecretStr` in the process, never in a prompt; the prompt forbids revealing itself | `x05`, held-out `h14` | Anything pasted into a ticket or a log by the operator is outside this control |
| T7 | **Cross-customer leakage** | State lives in one `Conversation` per customer; the agent object holds none | held-out `h07`, `h08` (another customer talks to the same agent first) | Tickets are files in one shared directory, and the Team Inbox has no authentication |
| T8 | Excessive agency: approving a refund, changing an account | No tool can do either; the approval record is not connected to any action | `x04`, held-out `h13`, `h17` | Becomes a real risk when a consequential tool is added (see section 5) |
| T9 | Oversized or malformed input | `MAX_MESSAGE_LENGTH` = 2000 characters, empty input rejected | `x06` | Unicode and encoding tricks are untested |
| T10 | Runaway loop or cost | `MAX_TURNS` = 3, diagnostic at most once, `FAILED_SAFELY` on model or retrieval errors | `f01`, `f02` | No token, time or spend budget; no rate limit |
| T11 | Supply chain and provider | `uv.lock`, weekly Dependabot, CI; an outage ends in `FAILED_SAFELY` | CI history, `INVALID RUN` detection in the harness | `langchain-community` is being sunset; customer text goes to the model provider |
| T12 | Personal data in logs and tickets | Logs rotate and are gitignored; the agent loop logs decisions and states, not message text | none | Tickets hold the full customer message; there is no redaction layer |

## 4. What can say NO to the model

| Control | Where |
|---|---|
| Input length and emptiness | `agent_loop.reply` |
| Instruction-override guard | `intents.is_instruction_override` |
| Marker neutralisation | `agent_loop._neutralize_markers` |
| Policy Rule #1: a hard fault escalates | `agent_loop` (code), not the prompt |
| Policy Rule #2: three agent replies without a resolution escalate | `agent_loop` |
| Router issues are diagnosed before guidance | `agent_loop` |
| The diagnostic runs only for a router issue, and once | `agent_loop` (allow-list) |
| One ticket per conversation | `agent_loop._already_escalated` |
| What the customer is told about an escalation | `responses.escalation_notice` (deterministic) |
| Model or retrieval failure | `FAILED_SAFELY` with a fixed message |

## 5. Tool and action inventory

| Tool or action | Tier | Effect | Reversible | Oversight |
|---|---|---|---|---|
| `search_policy` | READ | Reads the knowledge base | n/a | none needed |
| `run_router_diagnostic` | READ | Simulated health check | n/a | none needed |
| `create_escalation_ticket` | WRITE (internal) | Writes a ticket file | Yes, staff close it | A person reads every ticket |
| `create_approval_request` | WRITE (internal) | Writes a record next to the ticket | Yes | Not yet connected to an action |

There is no CONSEQUENTIAL tool. **If the human does nothing**, the ticket stays open and the customer has been told the
team will follow up. No action is pending, so nothing happens that needed approval. This is only true while no
consequential tool exists: the first one added must have an approval gate that times out into a safe refusal.

## 6. Measurement

- Frozen suite (`cases_v2.jsonl`): 8 adversarial cases, 5 runs each. The report states the **attack success rate as a
  rate with an upper bound** (95% Wilson interval), because "blocked once" is not evidence. This suite guided the fixes
  for `x03`, `n01` and `n02`, so it is a regression result.
- Held-out suite (`cases_v3_heldout.jsonl`): 17 cases written after the code was frozen, covering the gaps listed in the
  release decision (poisoned passage, tool-output injection, cross-customer isolation, new attack wordings). Results:
  **not run yet**; they are recorded here and in `reports/eval_v3_heldout_*.md`.
- Protocol: a failure is classified as an agent defect or a check defect before anything is changed. Fixing a defect
  turns that suite into a development set, so any later claim needs a new held-out suite (`v4`). Frozen files are
  never edited: `evals/frozen.json` holds their hashes and a test fails if one changes.

## 7. Not applicable, and why

- Memory poisoning, deletion, isolation of long-term memory: there is no long-term memory. Conversation state lives for
  one session and one customer.
- Multi-agent trust laundering: a single agent.
- Credentials for real systems: none. The diagnostic is simulated and no tool acts on an account.

## 8. Residual risk, in order

1. Indirect injection and tool-output injection are measured only by the held-out suite, on one model.
2. A new attack wording is stopped only by the prompt, with the keyword guard as a first filter.
3. No authentication on the Team Inbox, no rate limit, no token or spend budget.
4. Tickets and transcripts hold personal data with no redaction.
5. A consequential tool would need an approval gate that does not exist yet.
