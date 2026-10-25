"""
The ablation arms must be honest comparison systems: no tools, no tickets, no hidden policy.
Runs on scripted models and the dry-run harness, so it needs no Ollama/OpenAI and runs in CI.
"""
import json
from pathlib import Path

import pytest

import compare_arms
import run_eval_v2
from src.agent_loop import TerminalState
from src.arms import BaselineArm, RagOnlyArm, build_arm
from src.conversation import Conversation
from src.model_client import ModelClient, ModelClientError
from src.schemas import ActionType, AgentDecision

CASES = Path(__file__).resolve().parent.parent / "evals" / "cases_v2.jsonl"


class FakeRAG:
    def retrieve(self, query: str, k: int = 3) -> str:
        return "FAKE POLICY PASSAGE"


class Model(ModelClient):
    model_name = "scripted"

    def __init__(self, decision: AgentDecision | None = None, fail: bool = False):
        self._decision, self._fail = decision, fail

    def generate(self, messages):
        if self._fail:
            raise ModelClientError("down")
        return "just restart it"

    def generate_structured(self, messages, schema):
        if self._fail:
            raise ModelClientError("down")
        return self._decision


def decision(action, escalate=False):
    return AgentDecision(action=action, reasoning="r", requires_escalation=escalate, response_to_user="ok")


def test_baseline_answers_every_message_and_never_escalates():
    arm = BaselineArm(Model())
    result = arm.reply(Conversation(), "My router is on fire, Hard Fault")
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert result.ticket is None
    assert result.reply_text == "just restart it"


def test_baseline_fails_safely_when_the_model_is_down():
    result = BaselineArm(Model(fail=True)).reply(Conversation(), "hello")
    assert result.terminal_state == TerminalState.FAILED_SAFELY
    assert result.error_message == "down"


def test_rag_arm_accepts_an_escalation_proposal_but_has_no_ticket_tool():
    arm = RagOnlyArm(Model(decision(ActionType.ESCALATE, True)), FakeRAG())
    conversation = Conversation()
    result = arm.reply(conversation, "I need a human")
    assert result.terminal_state == TerminalState.ESCALATED
    assert result.ticket is None
    assert conversation.agent_replies == 1


def test_rag_arm_does_not_enforce_policy():
    """A model that asks for a diagnostic simply gets its words back: nothing runs, nothing is blocked."""
    arm = RagOnlyArm(Model(decision(ActionType.RUN_DIAGNOSTIC)), FakeRAG())
    result = arm.reply(Conversation(), "internet is down")
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER


def test_rag_arm_keeps_state_consistent_when_the_model_fails():
    conversation = Conversation()
    result = RagOnlyArm(Model(fail=True), FakeRAG()).reply(conversation, "hello")
    assert result.terminal_state == TerminalState.FAILED_SAFELY
    assert conversation.messages == []


def test_build_arm_rejects_unknown_names():
    with pytest.raises(ValueError):
        build_arm("agent", Model(), FakeRAG())


# ---------------------------------------------------- the runner and the comparison


def _dry(tmp_path, monkeypatch, arm):
    monkeypatch.chdir(tmp_path)
    code = run_eval_v2.main(["--dry-run", "--runs", "2", "--arm", arm, "--cases", str(CASES), "--only", "refund"])
    assert code == 0
    return tmp_path / "reports"


@pytest.mark.parametrize(("arm", "stem"), [
    ("baseline", "eval_v2_baseline_dry-run_stub"),
    ("rag", "eval_v2_rag_dry-run_stub"),
    ("agent", "eval_v2_dry-run_stub"),
])
def test_dry_run_writes_a_report_named_after_the_arm(tmp_path, monkeypatch, arm, stem):
    reports = _dry(tmp_path, monkeypatch, arm)
    data = json.loads((reports / f"{stem}.json").read_text(encoding="utf-8"))
    assert data["meta"]["arm"] == arm
    assert (data["decision"] == "N/A (ablation arm)") == (arm != "agent")
    text = (reports / f"{stem}.md").read_text(encoding="utf-8")
    assert (f"ABLATION ARM: `{arm}`" in text) == (arm != "agent")


def test_comparison_refuses_dry_runs(tmp_path, monkeypatch):
    reports = _dry(tmp_path, monkeypatch, "baseline")
    loaded = {"a": compare_arms.load_report(reports / "eval_v2_baseline_dry-run_stub.json")}
    loaded["b"] = loaded["a"]
    with pytest.raises(compare_arms.ComparisonError, match="dry run"):
        compare_arms.render(loaded)


def _fake_report(arm, p1):
    k = 3
    fam = {"pass@1": p1, "pass@3": 1.0, "pass^3": p1, "cases": 2}
    return {
        "meta": {"provider": "openai", "model": "m", "cases_file": "c.jsonl", "runs": k, "total_cases": 38,
                 "dry_run": False, "arm": arm},
        "decision": "NO-GO",
        "summary": {"overall": {"cases": 38, "pass@1": p1, "pass@3": 1.0, "pass^3": p1},
                    "families": {"adversarial": fam, "refund": fam},
                    "flaky": [], "always_failing": [], "latency_p50": 1.0, "latency_p95": 2.0},
        "gates": [{"name": "g", "blocking": True, "ok": p1 > 0.5, "detail": ""}],
    }


def test_comparison_table_lists_every_arm_and_family():
    text = compare_arms.render({"baseline": _fake_report("baseline", 0.3), "agent": _fake_report("agent", 0.9)})
    assert "| pass@1 | 30.0% | 90.0% |" in text
    assert "| adversarial |" in text and "| refund |" in text
    assert "0/1" in text and "1/1" in text


def test_comparison_refuses_different_models():
    other = _fake_report("agent", 0.9)
    other["meta"]["model"] = "other"
    with pytest.raises(compare_arms.ComparisonError, match="model"):
        compare_arms.render({"baseline": _fake_report("baseline", 0.3), "agent": other})


def test_injected_model_failure_is_handled_by_every_arm(tmp_path, monkeypatch):
    """Regression: the injected failure used to crash arms that call generate() instead of generate_structured()."""
    monkeypatch.chdir(tmp_path)
    for arm in ("baseline", "rag", "agent"):
        run_eval_v2.main(["--dry-run", "--runs", "1", "--arm", arm, "--cases", str(CASES), "--only", "f02"])
    for stem in ("eval_v2_baseline", "eval_v2_rag", "eval_v2"):
        data = json.loads((tmp_path / "reports" / f"{stem}_dry-run_stub.json").read_text(encoding="utf-8"))
        gate = next(g for g in data["gates"] if g["name"] == "No unhandled errors")
        assert gate["ok"], stem


def test_comparison_never_shows_a_release_label_for_an_ablation_arm():
    """Regression: a baseline run on a small subset printed CONDITIONAL GO."""
    baseline = _fake_report("baseline", 0.3)
    baseline["decision"] = "CONDITIONAL GO"
    text = compare_arms.render({"baseline": baseline, "agent": _fake_report("agent", 0.9)})
    assert "| Decision | n/a (ablation) | NO-GO |" in text


def test_comparison_refuses_different_prompt_versions_but_tolerates_old_reports():
    old = _fake_report("baseline", 0.3)                       # written before prompt_version existed
    new_a, new_b = _fake_report("rag", 0.5), _fake_report("agent", 0.9)
    new_a["meta"]["prompt_version"], new_b["meta"]["prompt_version"] = "2", "2"
    assert "rag" in compare_arms.render({"baseline": old, "rag": new_a, "agent": new_b})
    new_b["meta"]["prompt_version"] = "3"
    with pytest.raises(compare_arms.ComparisonError, match="prompt versions"):
        compare_arms.render({"rag": new_a, "agent": new_b})
