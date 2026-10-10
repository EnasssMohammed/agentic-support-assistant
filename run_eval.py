"""
Stage 8: Resolution-quality evaluation.

Runs the FULL agent (retrieval + diagnostic tool + escalation) against the
same frozen eval set the baseline was run against in Stage 1, and writes
reports/agent_results.md. Run this directly (not via pytest) so you see
progress printed after each case, since the full set can take a while on
a slow local model:

    uv run python run_eval.py
"""
import json
import time
from pathlib import Path

from src.agent_loop import VeloAgent
from src.model_client import get_model_client
from src.rag_engine import RAGEngine

EVAL_FILE = Path("evals/cases.jsonl")
REPORT_FILE = Path("reports/agent_results.md")


def main():
    cases = [json.loads(line) for line in open(EVAL_FILE, encoding="utf-8")]
    agent = VeloAgent(model=get_model_client(), rag=RAGEngine())

    Path("reports").mkdir(exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as report:
        report.write("# Full Agent Results (retrieval + diagnostics + escalation)\n\n")
        report.write("Compare against reports/baseline_results.md for the same cases.\n\n")

        for i, case in enumerate(cases, start=1):
            print(f"[{i}/{len(cases)}] Running case {case['id']}...")
            start = time.time()

            result = agent.run(case["question"])

            elapsed = time.time() - start
            print(f"  -> {result.terminal_state.value} in {elapsed:.1f}s ({result.turns_used} turn(s))")

            report.write(f"## {case['id']}\n")
            report.write(f"**Q:** {case['question']}\n\n")
            report.write(f"**Expected:** {case['expected_action']} "
                         f"(escalation required: {case['requires_escalation']})\n\n")
            report.write(f"**Agent terminal state:** {result.terminal_state.value} "
                         f"(turns used: {result.turns_used}, time: {elapsed:.1f}s)\n\n")
            report.write(f"**Agent reasoning:** {result.final_decision.reasoning}\n\n")
            report.write(f"**Response to user:** {result.final_decision.response_to_user}\n\n")
            if result.ticket:
                report.write(f"**Ticket created:** `{result.ticket.ticket_id}`\n\n")
            report.write("---\n\n")

    print(f"\nDone. Report written to {REPORT_FILE}")


if __name__ == "__main__":
    main()
