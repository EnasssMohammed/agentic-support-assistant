"""
Deterministic unit tests for the agent loop - no Ollama, no network.

A scripted fake model replays a fixed sequence of decisions, and the random
mock diagnostic is replaced with fixed results, so every terminal state
(including the failure/recovery cases) is tested reliably. These run in CI;
the slower end-to-end tests that use a real model are in test_agent_loop.py.
"""
import pytest

from src.agent_loop import MAX_MESSAGE_LENGTH, InvalidInputError, TerminalState, VeloAgent
from src.diagnostics import DiagnosticResult, DiagnosticStatus
from src.model_client import ModelClient, ModelClientError
from src.schemas import ActionType, AgentDecision


class FakeRAG:
    def retrieve(self, query: str, k: int = 3) -> str:
        return "FAKE POLICY PASSAGE"


class ScriptedModel(ModelClient):
    """Returns (or raises) the next item from a fixed script on each call."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def generate(self, messages):
        raise NotImplementedError

    def generate_structured(self, messages, schema):
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_decision(action: ActionType, escalate: bool = False) -> AgentDecision:
    return AgentDecision(
        action=action,
        reasoning="scripted test decision",
        requires_escalation=escalate,
        response_to_user="ok",
    )


def make_agent(script) -> tuple[VeloAgent, ScriptedModel]:
    model = ScriptedModel(script)
    return VeloAgent(model=model, rag=FakeRAG()), model


def fix_diagnostic(monkeypatch, status: DiagnosticStatus) -> None:
    """Replace the random mock diagnostic with a fixed result."""
    monkeypatch.setattr(
        "src.agent_loop.run_router_diagnostic",
        lambda: DiagnosticResult(status=status, detail="fixed for test"),
    )


def forbid_diagnostic(monkeypatch) -> None:
    def _fail():
        raise AssertionError("the diagnostic tool must not run in this scenario")

    monkeypatch.setattr("src.agent_loop.run_router_diagnostic", _fail)


@pytest.fixture(autouse=True)
def isolated_tickets(tmp_path, monkeypatch):
    """Keep generated escalation tickets out of the repo."""
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("bad_message", ["", "   ", "x" * (MAX_MESSAGE_LENGTH + 1)])
def test_invalid_input_is_rejected_before_calling_the_model(bad_message):
    agent, model = make_agent([])
    with pytest.raises(InvalidInputError):
        agent.run(bad_message)
    assert model.calls == 0


def test_direct_answer_resolves_in_one_turn():
    agent, _ = make_agent([make_decision(ActionType.ANSWER)])
    result = agent.run("How do I reset my password?")
    assert result.terminal_state == TerminalState.RESOLVED
    assert result.turns_used == 1


def test_diagnostic_then_answer_resolves_in_two_turns(monkeypatch):
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK)
    agent, model = make_agent(
        [make_decision(ActionType.RUN_DIAGNOSTIC), make_decision(ActionType.ANSWER)]
    )
    result = agent.run("My router has no internet.")
    assert result.terminal_state == TerminalState.RESOLVED
    assert result.turns_used == 2
    assert model.calls == 2


def test_escalation_creates_a_ticket(tmp_path):
    agent, _ = make_agent([make_decision(ActionType.ESCALATE, escalate=True)])
    result = agent.run("Something that must go to a human.")
    assert result.terminal_state == TerminalState.ESCALATED
    assert result.ticket is not None
    assert (tmp_path / "tickets" / f"{result.ticket.ticket_id}.json").exists()


def test_escalation_flag_wins_even_if_action_says_answer():
    agent, _ = make_agent([make_decision(ActionType.ANSWER, escalate=True)])
    result = agent.run("Something that must go to a human.")
    assert result.terminal_state == TerminalState.ESCALATED


def test_second_diagnostic_request_is_blocked_by_policy_check(monkeypatch):
    """The documented failure/recovery case: the model ignores the
    'diagnose at most once' rule and the code stops it, instead of looping."""
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK)
    agent, model = make_agent(
        [make_decision(ActionType.RUN_DIAGNOSTIC), make_decision(ActionType.RUN_DIAGNOSTIC)]
    )
    result = agent.run("My router has no internet.")
    assert result.terminal_state == TerminalState.BUDGET_EXHAUSTED
    assert model.calls == 2  # it did not keep looping


def test_model_failure_fails_safely_instead_of_crashing():
    agent, _ = make_agent([ModelClientError("provider unreachable")])
    result = agent.run("My router has no internet.")
    assert result.terminal_state == TerminalState.FAILED_SAFELY
    assert result.final_decision is None
    assert "provider unreachable" in result.error_message


# --- Policy Rule #1: a Hard Fault must be escalated, enforced in code -------------------


def test_customer_reported_hard_fault_escalates_without_calling_the_model(monkeypatch):
    """Regression: the model used to answer 'run_diagnostic' to a message that already
    reported a Hard Fault. The rule is mandatory, so it no longer depends on the model."""
    forbid_diagnostic(monkeypatch)
    agent, model = make_agent([])  # an empty script: any model call would raise
    result = agent.run("Diagnostics came back as a Hard Fault on my router.")
    assert result.terminal_state == TerminalState.ESCALATED
    assert result.ticket is not None
    assert model.calls == 0
    assert result.turns_used == 0


def test_measured_hard_fault_escalates_without_a_second_model_call(monkeypatch):
    fix_diagnostic(monkeypatch, DiagnosticStatus.HARD_FAULT)
    agent, model = make_agent([make_decision(ActionType.RUN_DIAGNOSTIC)])
    result = agent.run("My router has no internet.")
    assert result.terminal_state == TerminalState.ESCALATED
    assert result.ticket is not None
    assert model.calls == 1  # the escalation did not wait for another model decision


def test_customer_reported_software_glitch_does_not_rerun_the_diagnostic(monkeypatch):
    forbid_diagnostic(monkeypatch)
    agent, model = make_agent([make_decision(ActionType.ANSWER)])
    result = agent.run("The diagnostic says software glitch on my router.")
    assert result.terminal_state == TerminalState.RESOLVED
    assert model.calls == 1
