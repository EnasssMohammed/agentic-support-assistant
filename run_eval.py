"""
Stage 8: Resolution-quality evaluation.

Runs the FULL agent (retrieval + diagnostic tool + escalation) against the frozen eval set
that the Stage 1 baseline was run against. Run it directly (not via pytest) so progress is
printed after each case; the full set can take a while on a slow local model:

    uv run python run_eval.py

Each run writes its own report, named after the provider and model
(reports/agent_results_<provider>_<model>.md), so results from different models never
overwrite each other. The report is rewritten after every case, so a crash or Ctrl+C keeps
everything finished so far.
"""
import json
import re
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.agent_loop import AgentRunResult, TerminalState, VeloAgent
from src.conversation import Conversation, Role
from src.diagnostics import DiagnosticStatus
from src.model_client import ModelClient, get_model_client
from src.rag_engine import RAGEngine, resolve_provider

EVAL_FILE = Path("evals/cases.jsonl")
REPORTS_DIR = Path("reports")


@dataclass
class CaseRun:
    case: dict
    result: AgentRunResult
    elapsed: float


def report_path(provider: str, model_name: str, reports_dir: Path = REPORTS_DIR) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{provider}_{model_name}").strip("-")
    return reports_dir / f"agent_results_{safe}.md"


def escalation_matches(expected_escalation: bool, state: TerminalState) -> bool | None:
    """Whether the escalate / don't-escalate decision matched the case's expectation.

    Returns None when the run failed safely: no decision was reached, so it is not scored
    either way (counting it as "didn't escalate" would hand out false credit).
    """
    if state == TerminalState.FAILED_SAFELY:
        return None
    return (state == TerminalState.ESCALATED) == expected_escalation

def action_matches(case: dict, result: AgentRunResult) -> bool | None:
    """Heuristic check of whether the expected action appears in the result.

    Returns None when the run failed safely or when the action cannot
    be evaluated reliably from the available result.
    """
    if result.terminal_state == TerminalState.FAILED_SAFELY:
        return None

    action = case["expected_action"]
    state = result.terminal_state

    if result.final_decision is None:
        return None

    text = (
        result.final_decision.reasoning + " "
        + result.final_decision.response_to_user
    ).lower()

    if action == "escalate_immediately":
        return state == TerminalState.ESCALATED and "hard fault" in text

    if action == "escalate_after_retry_limit":
        return (
            state == TerminalState.ESCALATED
            and any(word in text for word in ("retry", "attempt", "3 interaction"))
        )

    if action == "guide_restart":
        # A Hard Fault should be escalated, not treated as routine troubleshooting.
        if state == TerminalState.ESCALATED and "hard fault" in text:
            return None
        return bool(re.search(r"\b(restart|reboot)\b", text))

    if action == "deny_refund_digital_license":
        return (
            "digital license" in text
            and any(
                phrase in text
                for phrase in ("non-refundable", "cannot be refunded",
                               "cannot issue a refund", "refund cannot")
            )
        )

    if action == "trigger_password_reset":
        return (
            "password reset" in text
            and any(word in text for word in ("link", "trigger", "reset flow"))
        )



    if action == "approve_return_within_window":
        approval_phrases = (
            "return is approved",
            "approved for return",
            "eligible for return",
            "eligible for a full refund",
            "you can return",
            "can proceed with a return",
            "return is allowed",
        )
        denial_phrases = (
            "not eligible for return",
            "not eligible for a refund",
            "cannot return",
            "cannot be returned",
            "refund is denied",
            "refund cannot be issued",
        )

        response = result.final_decision.response_to_user.lower()

        # Evaluate the customer-facing answer, not reasoning alone.
        if any(phrase in response for phrase in denial_phrases):
            return False

        return any(phrase in response for phrase in approval_phrases)



    if action == "ask_clarifying_question":
        return (
            state == TerminalState.AWAITING_CUSTOMER
            and any(
                phrase in text
                for phrase in (
                    "could you describe",
                    "please describe",
                    "can you clarify",
                    "could you clarify",
                    "what is not working",
                )
            )
        )

    # Unknown action labels are not scored.
    return None


def render_summary(runs: list[CaseRun]) -> str:
    rows = []
    scored = matched = failed = 0
    action_scored = action_matched = action_unscored = 0

    for run in runs:
        state = run.result.terminal_state

        # Existing escalation metric
        match = escalation_matches(
            run.case["requires_escalation"], state
        )
        if match is None:
            failed += 1
            escalation_mark = "n/a (failed safely)"
        else:
            scored += 1
            matched += int(match)
            escalation_mark = "yes" if match else "NO"

        # New expected-action metric
        action_match = action_matches(run.case, run.result)
        if action_match is None:
            action_unscored += 1
            action_mark = "n/a"
        else:
            action_scored += 1
            action_matched += int(action_match)
            action_mark = "yes" if action_match else "NO"

        rows.append(
            f"| {run.case['id']} | "
            f"{run.case['requires_escalation']} | "
            f"{state.value} | {escalation_mark} | "
            f"{run.case['expected_action']} | {action_mark} | "
            f"{run.result.turns_used} | {run.elapsed:.1f} |"
        )

    median = statistics.median(r.elapsed for r in runs) if runs else 0.0

    return "\n".join([
        "## Summary",
        "",
        "| Case | Escalation expected | Terminal state | "
        "Escalation match | Expected action | Action match | "
        "Turns | Time (s) |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        f"**Escalation match: {matched}/{scored} scored** "
        f"({failed} failed safely, not scored).",
        f"**Expected-action match: {action_matched}/{action_scored} scored** "
        f"({action_unscored} not scored).",
        f"Median time per case: {median:.1f}s.",
        "",
        "Expected-action matching uses keyword heuristics, not a full "
        "semantic evaluation. Review each case below, especially cases "
        "marked NO or n/a. The mock diagnostic is randomized, so a "
        "Hard Fault can legitimately cause escalation in some cases.",
        "",
    ])


def render_case(run: CaseRun) -> str:
    case, result = run.case, run.result
    lines = [
        f"## {case['id']}",
        f"**Q:** {case['question']}",
        "",
        f"**Expected:** {case['expected_action']} (escalation required: {case['requires_escalation']})",
        "",
        f"**Agent terminal state:** {result.terminal_state.value} "
        f"(turns used: {result.turns_used}, time: {run.elapsed:.1f}s)",
        "",
    ]
    if result.final_decision is None:
        lines += [f"**Failed safely:** {result.error_message}", ""]
    else:
        lines += [
            f"**Agent reasoning:** {result.final_decision.reasoning}",
            "",
            f"**Response to user:** {result.final_decision.response_to_user}",
            "",
        ]
    if result.ticket:
        lines += [f"**Ticket created:** `{result.ticket.ticket_id}`", ""]
    lines += ["---", ""]
    return "\n".join(lines)


def write_report(path: Path, header: str, runs: list[CaseRun]) -> None:
    body = "\n".join(render_case(run) for run in runs)
    path.write_text(f"{header}\n{render_summary(runs)}\n{body}", encoding="utf-8")


def main(
    model: ModelClient | None = None,
    rag: RAGEngine | None = None,
    cases_file: Path = EVAL_FILE,
    reports_dir: Path = REPORTS_DIR,
    provider: str | None = None,
) -> Path:
    cases = [json.loads(line) for line in open(cases_file, encoding="utf-8") if line.strip()]
    provider = resolve_provider(provider)
    model = model if model is not None else get_model_client()
    rag = rag if rag is not None else RAGEngine(provider=provider)


    path = report_path(provider, model.model_name, reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    header = (
        "# Full Agent Results (retrieval + diagnostics + escalation)\n\n"
        f"- Provider: {provider}\n"
        f"- Model: {model.model_name}\n"
        f"- Run started (UTC): {datetime.now(timezone.utc):%Y-%m-%d %H:%M}\n"
        f"- Cases: {len(cases)} from {cases_file.as_posix()}\n\n"
        "Compare against reports/baseline_results.md for the same cases.\n"
    )

    runs: list[CaseRun] = []
    for i, case in enumerate(cases, start=1):
        diagnostic_status = case.get("diagnostic_status")
        forced_status = (
            DiagnosticStatus[diagnostic_status.upper()]
            if diagnostic_status
            else None
        )

        agent = VeloAgent(
            model=model,
            rag=rag,
            diagnostic_status=forced_status,
        )

        print(f"[{i}/{len(cases)}] Running case {case['id']}...")
        start = time.time()

        prior_agent_replies = case.get("prior_agent_replies", 0)

        if prior_agent_replies:
            conversation = Conversation()

            for attempt in range(prior_agent_replies):
                conversation.add(
                    Role.CUSTOMER,
                    f"Previous attempt {attempt + 1}: "
                    "The issue is still unresolved.",
                )
                conversation.add(
                    Role.AGENT,
                    f"Previous response {attempt + 1}: "
                    "Troubleshooting was attempted, but the issue remains.",
                )

            result = agent.reply(conversation, case["question"])
        else:
            result = agent.run(case["question"])

        elapsed = time.time() - start
        print(
            f"  -> {result.terminal_state.value} "
            f"in {elapsed:.1f}s ({result.turns_used} turn(s))"
        )
        runs.append(CaseRun(case, result, elapsed))
        write_report(path, header, runs)


    print(f"\nDone. Report written to {path}")
    return path


if __name__ == "__main__":
    main()
