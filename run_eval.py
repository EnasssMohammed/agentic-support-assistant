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


def render_summary(runs: list[CaseRun]) -> str:
    rows = []
    scored = matched = failed = 0
    for run in runs:
        state = run.result.terminal_state
        match = escalation_matches(run.case["requires_escalation"], state)
        if match is None:
            failed += 1
            mark = "n/a (failed safely)"
        else:
            scored += 1
            matched += match
            mark = "yes" if match else "NO"
        rows.append(
            f"| {run.case['id']} | {run.case['requires_escalation']} | {state.value} "
            f"| {mark} | {run.result.turns_used} | {run.elapsed:.1f} |"
        )

    median = statistics.median(r.elapsed for r in runs) if runs else 0.0
    return "\n".join(
        [
            "## Summary",
            "",
            "| Case | Escalation expected | Terminal state | Match | Turns | Time (s) |",
            "|---|---|---|---|---|---|",
            *rows,
            "",
            f"**Escalation match: {matched}/{scored} scored** ({failed} failed safely, not scored). "
            f"Median time per case: {median:.1f}s.",
            "",
            "This only checks whether the escalate / don't-escalate decision was right. It does "
            "not judge the wording or content of the answer, so read each case below. n1 and a1 "
            "can legitimately go either way: the mock diagnostic is random (about 20% Hard "
            "Fault), and a Hard Fault must be escalated.",
            "",
        ]
    )


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
    agent = VeloAgent(model=model, rag=rag)

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
        print(f"[{i}/{len(cases)}] Running case {case['id']}...")
        start = time.time()
        result = agent.run(case["question"])
        elapsed = time.time() - start
        print(f"  -> {result.terminal_state.value} in {elapsed:.1f}s ({result.turns_used} turn(s))")
        runs.append(CaseRun(case, result, elapsed))
        write_report(path, header, runs)

    print(f"\nDone. Report written to {path}")
    return path


if __name__ == "__main__":
    main()
