"""
The evaluation script must score runs, keep per-model reports, and survive a failed case.

Uses a scripted fake model and a fake retriever, so it needs no Ollama/OpenAI and runs in CI.
"""
import json
from pathlib import Path

import pytest

from run_eval import escalation_matches, main, report_path
from src.agent_loop import TerminalState
from src.model_client import ModelClient, ModelClientError
from src.schemas import ActionType, AgentDecision


class FakeRAG:
    def retrieve(self, query: str, k: int = 3) -> str:
        return "FAKE POLICY PASSAGE"


class ScriptedModel(ModelClient):
    model_name = "scripted"

    def __init__(self, script):
        self._script = list(script)

    def generate(self, messages):
        raise NotImplementedError

    def generate_structured(self, messages, schema):
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def decision(action: ActionType, escalate: bool = False) -> AgentDecision:
    return AgentDecision(
        action=action,
        reasoning="scripted reasoning",
        requires_escalation=escalate,
        response_to_user="ok",
    )


@pytest.mark.parametrize(
    ("expected", "state", "result"),
    [
        (True, TerminalState.ESCALATED, True),
        (False, TerminalState.ESCALATED, False),
        (False, TerminalState.RESOLVED, True),
        (True, TerminalState.RESOLVED, False),
        (False, TerminalState.BUDGET_EXHAUSTED, True),
        (True, TerminalState.FAILED_SAFELY, None),
        (False, TerminalState.FAILED_SAFELY, None),  # no decision was reached: not scored
    ],
)
def test_escalation_matches(expected, state, result):
    assert escalation_matches(expected, state) is result


def test_report_path_is_named_after_provider_and_model():
    assert report_path("openai", "gpt-4o-mini") == Path("reports/agent_results_openai_gpt-4o-mini.md")
    assert report_path("ollama", "llama3.2:1b") == Path("reports/agent_results_ollama_llama3.2-1b.md")


def test_run_writes_a_summary_and_survives_a_failed_case(tmp_path, monkeypatch):
    """Regression: a case that failed safely has no decision, and the script used to crash on it."""
    monkeypatch.chdir(tmp_path)  # keep generated tickets out of the repo
    cases_file = tmp_path / "cases.jsonl"
    cases = [
        {"id": "c1", "question": "How do I reset my password?", "expected_action": "x",
         "requires_escalation": False},
        {"id": "c2", "question": "My router has no internet.", "expected_action": "x",
         "requires_escalation": False},
        {"id": "c3", "question": "This must go to a human.", "expected_action": "x",
         "requires_escalation": True},
    ]
    cases_file.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")
    model = ScriptedModel(
        [
            decision(ActionType.ANSWER),
            ModelClientError("provider unreachable"),
            decision(ActionType.ESCALATE, escalate=True),
        ]
    )

    path = main(
        model=model, rag=FakeRAG(), cases_file=cases_file,
        reports_dir=tmp_path / "reports", provider="ollama",
    )

    assert path.name == "agent_results_ollama_scripted.md"
    report = path.read_text(encoding="utf-8")
    assert "Model: scripted" in report
    assert "Escalation match: 2/2 scored" in report
    assert "1 failed safely" in report
    assert "provider unreachable" in report  # the failure is reported, not hidden
    assert report.count("## c") == 3  # all three cases are in the report
