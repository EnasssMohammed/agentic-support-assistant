"""
Deterministic unit tests for the agent loop - no Ollama, no network.

A scripted fake model replays a fixed sequence of decisions, so every
terminal state (including the failure/recovery cases) is tested
reliably. These run in CI; the slower end-to-end tests that use a real
model are in test_agent_loop.py.
"""
import pytest

from src.agent_loop import MAX_MESSAGE_LENGTH, InvalidInputError, TerminalState, VeloAgent
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


def test_diagnostic_then_answer_resolves_in_two_turns():
    agent, model = make_agent(
        [make_decision(ActionType.RUN_DIAGNOSTIC), make_decision(ActionType.ANSWER)]
    )
    result = agent.run("My router has no internet.")
    assert result.terminal_state == TerminalState.RESOLVED
    assert result.turns_used == 2
    assert model.calls == 2


def test_escalation_creates_a_ticket(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # keep generated tickets out of the repo
    agent, _ = make_agent([make_decision(ActionType.ESCALATE, escalate=True)])
    result = agent.run("Diagnostics came back as a Hard Fault.")
    assert result.terminal_state == TerminalState.ESCALATED
    assert result.ticket is not None
    assert (tmp_path / "tickets" / f"{result.ticket.ticket_id}.json").exists()


def test_escalation_flag_wins_even_if_action_says_answer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent, _ = make_agent([make_decision(ActionType.ANSWER, escalate=True)])
    result = agent.run("Something that must go to a human.")
    assert result.terminal_state == TerminalState.ESCALATED


def test_second_diagnostic_request_is_blocked_by_policy_check():
    """The documented failure/recovery case: the model ignores the
    'diagnose at most once' rule and the code stops it, instead of looping."""
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
