"""
Runs the frozen eval set through the non-agentic baseline and writes
reports/baseline_results.md. This is not a pass/fail test — it's evidence
collection. Read the report yourself and note where the baseline:
  - invents information not in technical_docs.txt (hallucination)
  - fails to escalate a Hard Fault per Policy Rule #1
  - gives inconsistent answers across runs

Uses whatever provider is set in .env (MODEL_PROVIDER=ollama by default).
"""
import json
import os
from pathlib import Path

from src.baseline import BaselineAgent
from src.model_client import get_model_client


def test_baseline_against_eval_set():
    cases = [json.loads(line) for line in open("evals/cases.jsonl", encoding="utf-8")]
    agent = BaselineAgent(model=get_model_client())

    Path("reports").mkdir(exist_ok=True)
    with open("reports/baseline_results.md", "w", encoding="utf-8") as report:
        report.write("# Baseline Results (non-agentic, single LLM call)\n\n")
        for case in cases:
            answer = agent.answer(case["question"])
            report.write(f"## {case['id']}\n")
            report.write(f"**Q:** {case['question']}\n\n")
            report.write(f"**Expected:** {case['expected_action']} "
                         f"(escalation required: {case['requires_escalation']})\n\n")
            report.write(f"**Baseline answered:** {answer}\n\n---\n\n")

    assert os.path.exists("reports/baseline_results.md")
