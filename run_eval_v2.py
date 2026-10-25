"""
Evaluation v2: repeated runs, pass@1 / pass@k / pass^k, adversarial suite, release gates.

    uv run python run_eval_v2.py --runs 3                 # real model (follows MODEL_PROVIDER)
    uv run python run_eval_v2.py --runs 3 --only adversarial
    uv run python run_eval_v2.py --dry-run                # verify the harness, no API/Ollama needed
    uv run python run_eval_v2.py --runs 5 --gate          # exit code 1 on NO-GO (use in CI)
    uv run python run_eval_v2.py --runs 5 --arm baseline  # comparison arm: one ungrounded model call
    uv run python run_eval_v2.py --runs 5 --arm rag       # comparison arm: retrieval only, no policy/tools

Every run uses a fresh conversation and a throw-away tickets/approvals folder, so evaluation
never pollutes your real tickets. The diagnostic result is forced per case (see the
"diagnostic" field), so the only source of variation is the model. The report is rewritten
after every case: a crash or Ctrl+C keeps everything finished so far.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from src.eval_metrics import (
    CaseOutcome,
    check_observation,
    evaluate_gates,
    is_infra_error,
    release_decision,
    summarize,
)
from src.retrieval_agent import PROMPT_VERSION

CASES_FILE = Path("evals/cases_v2.jsonl")
REPORTS_DIR = Path("reports")


# ------------------------------------------------------------------ cases

def load_cases(path: Path = CASES_FILE, only: str | None = None) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [c for c in cases if only in (None, c["family"], c["id"])]


def expand_turn(turn: str | dict) -> str:
    return turn["repeat"] * turn["times"] if isinstance(turn, dict) else turn


# --------------------------------------------------------------- one run

class _FailingModel:
    """Injected failure: the model provider is unreachable."""

    def generate_structured(self, messages, schema):
        from src.model_client import ModelClientError
        raise ModelClientError("injected model failure")

    def generate(self, messages):
        return self.generate_structured(messages, None)


def run_case_once(make_agent, case: dict, workdir: Path) -> dict:
    """Run one case in a fresh conversation. Returns the observation checked by the metrics module."""
    import src.agent_loop as agent_loop
    import src.approval as approval
    import src.escalation as escalation
    from src.agent_loop import InvalidInputError
    from src.conversation import Conversation

    tickets_dir, approvals_dir = workdir / "tickets", workdir / "approvals"
    diagnostics = {"calls": 0}
    real_diagnostic = agent_loop.run_router_diagnostic

    def counted_diagnostic(*args, **kwargs):
        diagnostics["calls"] += 1
        if case.get("inject") == "diagnostic_error":
            raise RuntimeError("injected diagnostic failure")
        return real_diagnostic(*args, **kwargs)

    saved = (escalation.TICKETS_DIR, approval.APPROVALS_DIR, agent_loop.run_router_diagnostic)
    escalation.TICKETS_DIR, approval.APPROVALS_DIR = tickets_dir, approvals_dir
    agent_loop.run_router_diagnostic = counted_diagnostic

    obs = {"replies": [], "final_state": None, "tickets": 0, "diagnostic_runs": 0,
           "error": None, "input_rejected": False, "elapsed": 0.0, "turn_times": [],
           "infra_error": False}
    internal_errors: list[str] = []
    started = time.perf_counter()
    try:
        agent = make_agent(case)
        if case.get("inject") == "model_error":
            agent.retrieval_agent.model = _FailingModel()
        conversation = Conversation()
        for turn in case["turns"]:
            turn_started = time.perf_counter()
            try:
                result = agent.reply(conversation, expand_turn(turn))
            except InvalidInputError:
                obs["input_rejected"] = True
                break
            obs["turn_times"].append(time.perf_counter() - turn_started)
            obs["replies"].append(result.reply_text)
            obs["final_state"] = result.terminal_state.value
            if result.error_message:
                internal_errors.append(result.error_message)
    except Exception as exc:  # an unhandled crash is itself a finding
        obs["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        escalation.TICKETS_DIR, approval.APPROVALS_DIR, agent_loop.run_router_diagnostic = saved

    obs["elapsed"] = time.perf_counter() - started
    obs["infra_error"] = any(is_infra_error(t) for t in [obs["error"] or "", *internal_errors])
    obs["diagnostic_runs"] = diagnostics["calls"]
    obs["tickets"] = len(list(tickets_dir.glob("*.json"))) if tickets_dir.exists() else 0
    return obs


# ------------------------------------------------------------------ report

def render_report(meta: dict, outcomes: list[CaseOutcome], excerpts: dict, k: int,
                  min_pass1: float, max_p95: float) -> tuple[str, dict]:
    summary = summarize(outcomes, k)
    gates = evaluate_gates(outcomes, summary, k, min_pass1, max_p95)
    decision, reasons = release_decision(gates)
    lost = sum(o.infra_errors for o in outcomes)
    if lost:
        decision = "INVALID RUN"
        reasons = [f"{lost} run(s) were lost to a network or provider outage; re-run when the connection is stable"]
    overall = summary["overall"]

    arm = meta.get("arm", "agent")
    lines = [f"# Velo evaluation v2 ({arm}): {meta['provider']} / {meta['model']}", ""]
    if arm != "agent":
        lines += [f"> **ABLATION ARM: `{arm}`.** Comparison evidence for the full agent. It has no escalation "
                  "or diagnostic tool and no code-level policy, so failing the ticket and diagnostic gates is "
                  "expected. It is never a release candidate.", ""]
    if lost:
        lines += [f"> **INVALID RUN.** {lost} run(s) failed with a connection error to the model or the "
                  "embedding service. The scores below mix outage with quality and must not be used.", ""]
    if meta["dry_run"]:
        lines += ["> **DRY RUN.** A scripted stand-in model was used. These numbers verify the harness only "
                  "and say nothing about quality.", ""]
    lines += [
        f"- Date: {meta['date']}",
        f"- Cases: {len(outcomes)} / {meta['total_cases']} run, {k} run(s) each",
        f"- Cases file: `{meta['cases_file']}`",
        "",
        f"## Release decision: **{'DRY RUN (not a release decision)' if meta['dry_run'] else decision}**",
        "",
        *(
            ["Budgets exceeded. Record in the release notes why this is acceptable:"]
            + [f"- {r}" for r in reasons]
            if decision == "CONDITIONAL GO"
            else ["Blocked by:"] + [f"- {r}" for r in reasons] if reasons else ["All gates pass."]
        ),
        "",
        "## Gates",
        "",
        "| Gate | Type | Result | Detail |",
        "|---|---|---|---|",
        *(f"| {g['name']} | {'blocking' if g['blocking'] else 'budget'} | "
          f"{'pass' if g['ok'] else '**FAIL**'} | {g['detail']} |" for g in gates),
        "",
        "## Scorecard",
        "",
        f"| Family | Cases | pass@1 | pass@{k} | pass^{k} |",
        "|---|---|---|---|---|",
        f"| **All** | {overall['cases']} | {overall['pass@1']:.1%} | {overall[f'pass@{k}']:.1%} "
        f"| {overall[f'pass^{k}']:.1%} |",
        *(f"| {name} | {b['cases']} | {b['pass@1']:.1%} | {b[f'pass@{k}']:.1%} | {b[f'pass^{k}']:.1%} |"
          for name, b in summary["families"].items()),
        "",
        f"Latency per reply: p50 {summary['latency_p50']:.1f}s, p95 {summary['latency_p95']:.1f}s.",
        "",
        f"Flaky cases (pass some runs, fail others): {', '.join(summary['flaky']) or 'none'}",
        f"Always failing: {', '.join(summary['always_failing']) or 'none'}",
        "",
        "## Failures",
        "",
    ]
    failed = [o for o in outcomes if o.c < o.n]
    if not failed:
        lines.append("None.")
    for o in failed:
        lines.append(f"### {o.case_id} ({o.family}): {o.c}/{o.n} runs passed")
        seen = set()
        for run in o.failures:
            for check, detail in run:
                if (check, detail) not in seen:
                    seen.add((check, detail))
                    lines.append(f"- `{check}`: {detail}")
        if excerpts.get(o.case_id):
            lines.append(f"- last reply: {excerpts[o.case_id]}")
        lines.append("")

    raw = {"meta": meta, "decision": decision, "reasons": reasons, "summary": summary, "gates": gates,
           "cases": [{"id": o.case_id, "family": o.family, "passes": o.passes, "states": o.states,
                      "failures": o.failures} for o in outcomes]}
    return "\n".join(lines), raw


def report_stem(provider: str, model: str, arm: str = "agent") -> str:
    prefix = "eval_v2_" if arm == "agent" else f"eval_v2_{arm}_"
    return prefix + re.sub(r"[^A-Za-z0-9._-]+", "-", f"{provider}_{model}").strip("-")


# --------------------------------------------------------------- dry run

def _dry_components():
    from src.intents import is_router_topic
    from src.schemas import ActionType, AgentDecision

    class DryRAG:
        def retrieve(self, query: str, k: int = 3) -> str:
            return "DRY RUN POLICY PASSAGE"

    class DryModel:
        def generate(self, messages):
            return "Please restart the router and try again."

        def generate_structured(self, messages, schema):
            latest = messages[-1]["content"].split("<latest_customer_message>")[-1]
            if "[DIAGNOSTIC RESULT]" not in latest and is_router_topic(latest):
                action, text = ActionType.RUN_DIAGNOSTIC, "Running a check."
            else:
                action, text = ActionType.ANSWER, "Please restart the router. Returns are accepted within 14 days."
            return AgentDecision(action=action, reasoning="dry run", requires_escalation=False,
                                 response_to_user=text)

    return DryModel(), DryRAG()


# ------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3, help="runs per case (k)")
    parser.add_argument("--cases", type=Path, default=CASES_FILE)
    parser.add_argument("--only", help="a family name or a case id")
    parser.add_argument("--dry-run", action="store_true", help="scripted model, no API needed")
    parser.add_argument("--arm", choices=("agent", "rag", "baseline"), default="agent",
                        help="system under test: the full agent, or an ablation arm to compare against")
    parser.add_argument("--min-pass1", type=float, default=0.80)
    parser.add_argument("--max-p95", type=float, default=30.0, help="seconds")
    parser.add_argument("--gate", action="store_true", help="exit 1 when the decision is NO-GO")
    parser.add_argument("--verbose", action="store_true", help="show agent logs on the console")
    args = parser.parse_args(argv)

    from src.agent_loop import VeloAgent
    from src.diagnostics import DiagnosticStatus

    if not args.verbose:
        # Keep the console readable: progress lines only. Full logs still go to logs/velo.log.
        for handler in logging.getLogger("velo").handlers:
            if type(handler) is logging.StreamHandler:
                handler.setLevel(logging.CRITICAL)

    if args.dry_run:
        model, rag = _dry_components()
        provider, model_name = "dry-run", "stub"
    else:
        from src.model_client import get_model_client
        from src.rag_engine import RAGEngine, resolve_provider
        from src.settings import load_settings

        settings = load_settings()
        provider = resolve_provider()
        model_name = getattr(settings, "model_name", "unknown")
        try:
            model, rag = get_model_client(), RAGEngine(provider=provider)
            rag.retrieve("connectivity check")          # preflight: embeddings reachable
            model.generate([{"role": "user", "content": "ping"}])   # preflight: model reachable
        except Exception as exc:
            print(f"Cannot reach the model or embedding provider: {type(exc).__name__}: {exc}\n"
                  "Check the internet connection, VPN or proxy, and OPENAI_API_KEY, then run again.")
            return 3

    def make_agent(case: dict):
        if args.arm != "agent":
            from src.arms import build_arm
            return build_arm(args.arm, model, rag)
        status = DiagnosticStatus(case.get("diagnostic", "software_glitch"))
        return VeloAgent(model=model, rag=rag, diagnostic_status=status)

    all_cases = load_cases(args.cases)
    cases = load_cases(args.cases, args.only)
    if not cases:
        print(f"No cases match {args.only!r}.")
        return 2

    meta = {"provider": provider, "model": model_name, "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cases_file": str(args.cases), "total_cases": len(all_cases), "runs": args.runs,
            "dry_run": args.dry_run, "arm": args.arm, "prompt_version": PROMPT_VERSION}
    stem = report_stem(provider, model_name, args.arm)
    REPORTS_DIR.mkdir(exist_ok=True)

    outcomes: list[CaseOutcome] = []
    excerpts: dict[str, str] = {}
    outage_streak = 0
    for case in cases:
        if outage_streak >= 3:
            print("\nStopping: 3 cases in a row could not reach the provider. Check the internet "
                  "connection, VPN or proxy, and OPENAI_API_KEY, then run again.")
            break
        outcome = CaseOutcome(case["id"], case["family"], bool(case.get("adversarial")))
        for _ in range(args.runs):
            with tempfile.TemporaryDirectory() as tmp:
                obs = run_case_once(make_agent, case, Path(tmp))
            fails = check_observation(case, obs)
            outcome.passes.append(not fails)
            outcome.failures.append(fails)
            outcome.elapsed.extend(obs["turn_times"] or [obs["elapsed"]])
            outcome.infra_errors += obs["infra_error"]
            outcome.states.append(obs["final_state"] or ("input_rejected" if obs["input_rejected"] else "error"))
            if fails and obs["replies"]:
                excerpts[case["id"]] = obs["replies"][-1].replace("\n", " ")[:160]
        outcomes.append(outcome)
        note = f"  ({outcome.infra_errors} lost to connection errors)" if outcome.infra_errors else ""
        print(f"{case['id']:>4} {case['family']:<13} {outcome.c}/{outcome.n} passed{note}")
        outage_streak = outage_streak + 1 if outcome.infra_errors == outcome.n else 0

        text, raw = render_report(meta, outcomes, excerpts, args.runs, args.min_pass1, args.max_p95)
        (REPORTS_DIR / f"{stem}.md").write_text(text, encoding="utf-8")
        (REPORTS_DIR / f"{stem}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    label = "DRY RUN (not a release decision)" if args.dry_run else raw["decision"]
    if raw["decision"] == "INVALID RUN":
        label = "INVALID RUN (connection errors; the scores are not meaningful)"
    print(f"\nDecision: {label}  (report: reports/{stem}.md)")
    for reason in raw["reasons"]:
        print(f"  - {reason}")

    overall = raw["summary"]["overall"]
    print(f"\nScorecard: pass@1 {overall['pass@1']:.1%} | pass@{args.runs} {overall[f'pass@{args.runs}']:.1%} "
          f"| pass^{args.runs} {overall[f'pass^{args.runs}']:.1%}")
    print("\nGates:")
    for gate in raw["gates"]:
        print(f"  [{'ok' if gate['ok'] else 'FAIL'}] {gate['name']}: {gate['detail']}")
    failing = [o for o in outcomes if o.c < o.n]
    if failing:
        print("\nFailing cases (paste this block when asking for help):")
        for o in failing:
            print(f"\n{o.case_id} ({o.family}) {o.c}/{o.n}")
            shown = set()
            for run in o.failures:
                for check, detail in run:
                    if (check, detail) not in shown:
                        shown.add((check, detail))
                        print(f"  - {check}: {detail}")
            if excerpts.get(o.case_id):
                print(f"  last reply: {excerpts[o.case_id]}")
    return 1 if args.gate and not args.dry_run and raw["decision"] not in ("GO", "CONDITIONAL GO") else 0


if __name__ == "__main__":
    sys.exit(main())
