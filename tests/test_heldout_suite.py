"""
The held-out suite, its harness features and the frozen-suite guard.

All offline: a fake agent stands in for the model, so these run in CI.
"""
import json
import types
from pathlib import Path

import pytest

import run_eval_v2 as harness
from src import agent_loop, escalation
from src.agent_loop import AgentRunResult, TerminalState
from src.diagnostics import DiagnosticStatus
from src.eval_metrics import CaseOutcome, attack_success_rate, wilson_upper
from src.schemas import ActionType, AgentDecision

ROOT = Path(__file__).resolve().parent.parent
V3 = ROOT / "evals" / "cases_v3_heldout.jsonl"
ALLOWED_EXPECT = {"final_state", "escalated", "diagnostic_runs", "include_any", "exclude", "rejects_input"}
ALLOWED_KEYS = {"id", "family", "turns", "diagnostic", "expect", "adversarial", "poison", "diagnostic_detail",
                "side_conversation", "inject"}


def cases():
    return [json.loads(line) for line in V3.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------------ the suite itself

def test_heldout_suite_is_well_formed():
    loaded = cases()
    assert len(loaded) == 17
    assert len({c["id"] for c in loaded}) == len(loaded)
    for c in loaded:
        assert set(c) <= ALLOWED_KEYS, c["id"]
        assert set(c["expect"]) <= ALLOWED_EXPECT, c["id"]
        assert c["adversarial"] is True, c["id"]          # every case is held to the strict adversarial gate
        assert c["turns"] and all(isinstance(t, str) for t in c["turns"]), c["id"]


def test_heldout_suite_covers_the_gaps_listed_in_the_release_decision():
    families = {c["family"] for c in cases()}
    assert {"indirect_injection", "tool_output_injection", "isolation", "attack_paraphrase"} <= families
    assert any("poison" in c for c in cases())
    assert any("diagnostic_detail" in c for c in cases())
    assert any("side_conversation" in c for c in cases())


def test_heldout_attacks_are_not_copies_of_the_frozen_cases():
    frozen = {json.loads(line)["turns"][0] for line in (ROOT / "evals" / "cases_v2.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip() and isinstance(json.loads(line)["turns"][0], str)}
    assert not frozen & {c["turns"][0] for c in cases()}


def test_frozen_suite_is_unchanged():
    """Never edit a frozen cases file after seeing results. Add a new version and re-run instead."""
    manifest = json.loads((ROOT / "evals" / "frozen.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        if name.startswith("_"):
            continue
        assert harness.normalized_sha256(ROOT / "evals" / name) == expected, f"{name} was edited after freezing"


def test_hash_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    assert harness.normalized_sha256(lf) == harness.normalized_sha256(crlf)


# ------------------------------------------------------------------ harness features

class FakeAgent:
    """Runs the diagnostic when asked and creates a ticket file when asked, like the real agent would."""

    def __init__(self):
        self.retrieval_agent = types.SimpleNamespace(model=None)
        self.details = []

    def reply(self, conversation, message):
        if "diag" in message:
            self.details.append(agent_loop.run_router_diagnostic().detail)
        if "ticket" in message:
            escalation.TICKETS_DIR.mkdir(parents=True, exist_ok=True)
            (escalation.TICKETS_DIR / f"{len(list(escalation.TICKETS_DIR.glob('*.json')))}.json").write_text("{}")
        decision = AgentDecision(action=ActionType.ANSWER, reasoning="r", requires_escalation=False,
                                 response_to_user="ok")
        return AgentRunResult(TerminalState.AWAITING_CUSTOMER, decision, 1)


def test_side_conversation_is_excluded_from_the_checked_counts(tmp_path):
    agent = FakeAgent()
    case = {"id": "t", "family": "f", "turns": ["diag now"], "side_conversation": ["diag and ticket"],
            "expect": {}}
    obs = harness.run_case_once(lambda c: agent, case, tmp_path)
    assert obs["tickets"] == 0                  # the other customer's ticket is not this conversation's
    assert obs["diagnostic_runs"] == 1          # nor is their diagnostic run
    assert len(agent.details) == 2


def test_diagnostic_detail_injection_reaches_the_tool_result(tmp_path):
    agent = FakeAgent()
    case = {"id": "t", "family": "f", "turns": ["diag"], "diagnostic_detail": "INJECTED TEXT", "expect": {}}
    harness.run_case_once(lambda c: agent, case, tmp_path)
    assert agent.details == ["INJECTED TEXT"]


@pytest.mark.parametrize("with_topic", [True, False])
def test_poisoned_passage_is_ranked_first_for_either_rag_signature(with_topic):
    if with_topic:
        class Rag:
            def retrieve(self, query, k=3, topic=None):
                return f"real:{topic}"
    else:
        class Rag:
            def retrieve(self, query, k=3):
                return "real"
    text = harness._PoisonedRAG(Rag(), "EVIL").retrieve("q", topic="router")
    assert text.startswith("[Source: technical_docs.txt]\nEVIL") and "real" in text


def test_report_names_never_collide_across_suites_and_arms():
    names = {
        harness.report_stem("openai", "m"),
        harness.report_stem("openai", "m", "rag"),
        harness.report_stem("openai", "m", "agent", "v3_heldout"),
        harness.report_stem("openai", "m", "baseline", "v3_heldout"),
    }
    assert len(names) == 4
    assert harness.report_stem("openai", "m") == "eval_v2_openai_m"          # the existing agent report name
    assert harness.suite_name(Path("evals/cases_v3_heldout.jsonl")) == "v3_heldout"
    assert harness.suite_name(Path("evals/cases_v2.jsonl")) == "v2"


def test_dry_run_of_the_heldout_suite_writes_its_own_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    harness.main(["--dry-run", "--runs", "1", "--cases", str(V3)])
    data = json.loads((tmp_path / "reports" / "eval_v3_heldout_dry-run_stub.json").read_text(encoding="utf-8"))
    assert data["meta"]["suite"] == "v3_heldout" and len(data["meta"]["cases_sha256"]) == 64
    assert data["attack_success_rate"]["attempts"] == 17


# ------------------------------------------------------------------ attack success rate

def test_zero_failures_is_never_reported_as_zero_risk():
    assert wilson_upper(0, 40) == pytest.approx(0.088, abs=0.002)
    assert wilson_upper(0, 190) < wilson_upper(0, 40)
    assert wilson_upper(5, 40) > 5 / 40


def test_attack_success_rate_counts_failed_adversarial_runs_only():
    attack = CaseOutcome("a", "adversarial", True, passes=[True, True, False, True])
    normal = CaseOutcome("b", "refund", False, passes=[False, False, False, False])
    rate = attack_success_rate([attack, normal])
    assert (rate["attempts"], rate["successful"], rate["rate"]) == (4, 1, 0.25)
    assert attack_success_rate([normal])["attempts"] == 0


# ------------------------------------------------------------------ the injections really reach the model

class PromptRecordingModel:
    model_name = "recording"

    def __init__(self):
        self.prompts = []

    def generate_structured(self, messages, schema):
        self.prompts.append(messages[-1]["content"])
        return AgentDecision(action=ActionType.ANSWER, reasoning="r", requires_escalation=False,
                             response_to_user="ok")

    def generate(self, messages):
        return "ok"


class PlainRag:
    def retrieve(self, query, k=3, topic=None):
        return "REAL POLICY"


def _run_with_real_agent(case_id, tmp_path):
    case = next(c for c in cases() if c["id"] == case_id)
    model = PromptRecordingModel()

    def make(c):
        rag = harness._PoisonedRAG(PlainRag(), c["poison"]) if c.get("poison") else PlainRag()
        return agent_loop.VeloAgent(model=model, rag=rag,
                                    diagnostic_status=DiagnosticStatus(c["diagnostic"]))

    harness.run_case_once(make, case, tmp_path)
    return case, model.prompts


def test_poisoned_passage_is_inside_the_retrieved_policy_the_model_reads(tmp_path):
    case, prompts = _run_with_real_agent("h02", tmp_path)
    assert prompts and case["poison"] in prompts[-1]


def test_injected_tool_detail_is_inside_the_diagnostic_result_the_model_reads(tmp_path):
    case, prompts = _run_with_real_agent("h05", tmp_path)
    assert prompts and "verified administrator" in prompts[-1]
