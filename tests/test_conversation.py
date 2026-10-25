"""
Conversation state: history reaches the model, and Policy Rule #2 is enforced in code.

Uses a scripted fake model and a fake retriever, so it needs no Ollama/OpenAI and runs in CI.
"""
import json

import pytest

from main import main as run_cli
from src.agent_loop import UNRESOLVED_TURN_LIMIT, TerminalState, VeloAgent
from src.conversation import Conversation, Role
from src.diagnostics import DiagnosticResult, DiagnosticStatus
from src.model_client import ModelClient, ModelClientError
from src.schemas import ActionType, AgentDecision


class FakeRAG:
    def retrieve(self, query: str, k: int = 3) -> str:
        return "FAKE POLICY PASSAGE"


class ScriptedModel(ModelClient):
    """Replays a fixed script and records every prompt it was sent."""

    model_name = "scripted"

    def __init__(self, script):
        self._script = list(script)
        self.prompts: list[str] = []

    @property
    def calls(self) -> int:
        return len(self.prompts)

    def generate(self, messages):
        raise NotImplementedError

    def generate_structured(self, messages, schema):
        self.prompts.append(messages[-1]["content"])
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def decision(action: ActionType, text: str = "agent reply", escalate: bool = False) -> AgentDecision:
    return AgentDecision(
        action=action, reasoning="scripted", requires_escalation=escalate, response_to_user=text
    )


def make_agent(script) -> tuple[VeloAgent, ScriptedModel]:
    model = ScriptedModel(script)
    return VeloAgent(model=model, rag=FakeRAG()), model


@pytest.fixture(autouse=True)
def isolated_tickets(tmp_path, monkeypatch):
    """Keep generated escalation tickets out of the repo."""
    monkeypatch.chdir(tmp_path)


def read_tickets(tmp_path):
    return [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "tickets").glob("*.json")]



def fix_diagnostic(monkeypatch, status: DiagnosticStatus, counter: list | None = None):
    def fake(*, forced_status=None):
        if counter is not None:
            counter.append(1)

        result_status = forced_status if forced_status is not None else status
        return DiagnosticResult(status=result_status, detail="fixed for test")

    monkeypatch.setattr("src.agent_loop.run_router_diagnostic", fake)



# --- the Conversation model ---------------------------------------------------------------


def test_conversation_counts_turns_and_builds_a_transcript():
    c = Conversation()
    c.add(Role.CUSTOMER, "my router is down")
    c.add(Role.AGENT, "have you restarted it?")
    c.add(Role.CUSTOMER, "yes, still down")
    assert (c.customer_turns, c.agent_replies) == (2, 1)
    assert c.transcript() == (
        "Customer: my router is down\nAgent: have you restarted it?\nCustomer: yes, still down"
    )


def test_conversation_survives_a_json_round_trip():
    c = Conversation()
    c.add(Role.CUSTOMER, "hello")
    c.diagnostic = DiagnosticResult(status=DiagnosticStatus.OK, detail="fine")
    assert Conversation.model_validate_json(c.model_dump_json()) == c


# --- history reaches the model -------------------------------------------------------------


def test_earlier_messages_are_sent_to_the_model_on_the_next_turn(monkeypatch):
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK, [])
    agent, model = make_agent(
        [
            decision(ActionType.ASK_CLARIFYING_QUESTION, "Which light is red?"),
            decision(ActionType.ANSWER, "Restart it."),  # a router issue is diagnosed before guidance,
            decision(ActionType.ANSWER, "Restart it."),  # so the model is asked once more with the result
        ]
    )
    conversation = Conversation()

    first = agent.reply(conversation, "My router is broken.")
    second = agent.reply(conversation, "The internet light.")

    assert first.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert second.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert "My router is broken." in model.prompts[1]
    assert "Which light is red?" in model.prompts[1]


def test_a_customer_still_writing_after_three_replies_is_escalated_in_code(tmp_path):
    agent, model = make_agent(
        [decision(ActionType.ASK_CLARIFYING_QUESTION, f"question {i}") for i in range(3)]
    )
    conversation = Conversation()
    for message in ("one", "two", "three"):
        assert agent.reply(conversation, message).terminal_state == TerminalState.AWAITING_CUSTOMER
    assert conversation.agent_replies == UNRESOLVED_TURN_LIMIT

    result = agent.reply(conversation, "still not fixed")

    assert result.terminal_state == TerminalState.ESCALATED
    assert model.calls == 3  # the fourth message did not wait for the model
    assert "Rule #2" in result.final_decision.reasoning
    (ticket,) = read_tickets(tmp_path)
    assert "Customer: one" in ticket["conversation_transcript"]  # the human gets the whole story
    assert "Agent: question 2" in ticket["conversation_transcript"]
    assert ticket["customer_message"] == "one"  # the ticket names the issue, not the last message


def test_a_conversation_resolved_in_time_is_not_escalated(tmp_path):
    agent, _ = make_agent(
        [decision(ActionType.ASK_CLARIFYING_QUESTION), decision(ActionType.ANSWER)]
    )
    conversation = Conversation()
    agent.reply(conversation, "one")
    result = agent.reply(conversation, "two")
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert not (tmp_path / "tickets").exists()


def test_after_escalation_later_messages_do_not_create_another_ticket(tmp_path):
    agent, model = make_agent([decision(ActionType.ESCALATE, "handing over", escalate=True)])
    conversation = Conversation()
    first = agent.reply(conversation, "this must go to a human")

    again = agent.reply(conversation, "hello? anyone?")

    assert again.terminal_state == TerminalState.ESCALATED
    assert again.ticket.ticket_id == first.ticket.ticket_id
    assert again.ticket.ticket_id in again.final_decision.response_to_user
    assert model.calls == 1
    assert len(read_tickets(tmp_path)) == 1


# --- the diagnostic tool, once per conversation ----------------------------------------------


def test_the_diagnostic_runs_at_most_once_per_conversation(monkeypatch):
    runs: list = []
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK, runs)
    agent, _ = make_agent(
        [
            decision(ActionType.RUN_DIAGNOSTIC),
            decision(ActionType.ASK_CLARIFYING_QUESTION, "Is the cable plugged in?"),
            decision(ActionType.RUN_DIAGNOSTIC),  # the model asks again on the next message
            decision(ActionType.ANSWER, "Please restart the router."),  # it re-plans after the rejection
        ]
    )
    conversation = Conversation()
    agent.reply(conversation, "No internet.")
    result = agent.reply(conversation, "Yes it is plugged in.")
    assert len(runs) == 1
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER


def test_the_escalation_ticket_carries_the_diagnostic_result(monkeypatch, tmp_path):
    fix_diagnostic(monkeypatch, DiagnosticStatus.HARD_FAULT)
    agent, _ = make_agent([decision(ActionType.RUN_DIAGNOSTIC)])
    result = agent.reply(Conversation(), "No internet.")

    assert result.terminal_state == TerminalState.ESCALATED
    (ticket,) = read_tickets(tmp_path)
    assert ticket["diagnostic_result"]["status"] == "hard_fault"
    assert ticket["conversation_transcript"] is None  # a single message needs no transcript


# --- failures leave the conversation untouched ------------------------------------------------


def test_a_failed_model_call_leaves_the_conversation_as_it_was():
    agent, _ = make_agent(
        [decision(ActionType.ASK_CLARIFYING_QUESTION), ModelClientError("unreachable"),
         decision(ActionType.ANSWER)]
    )
    conversation = Conversation()
    agent.reply(conversation, "one")
    before = conversation.model_copy(deep=True)

    failed = agent.reply(conversation, "two")

    assert failed.terminal_state == TerminalState.FAILED_SAFELY
    assert conversation == before  # no half-recorded turn, and the retry budget is not spent
    assert agent.reply(conversation, "two").terminal_state == TerminalState.AWAITING_CUSTOMER


# --- the CLI ---------------------------------------------------------------------------------


def test_the_cli_keeps_one_conversation_and_survives_a_failed_reply(capsys, monkeypatch):
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK, [])
    agent, model = make_agent(
        [
            ModelClientError("unreachable"),
            decision(ActionType.ASK_CLARIFYING_QUESTION, "Which light is red?"),
            decision(ActionType.ANSWER, "Restart it."),  # a router issue is diagnosed before guidance
            decision(ActionType.ANSWER, "Restart it."),  # so the model is asked once more with the result
        ]
    )
    inputs = iter(["", "my router is broken", "my router is broken", "the internet light", "/quit"])

    run_cli(agent=agent, input_fn=lambda prompt: next(inputs))

    output = capsys.readouterr().out
    assert "could not answer right now" in output  # the old script crashed here
    assert "Velo: Which light is red?" in output
    assert "Velo: Restart it." in output
    assert "my router is broken" in model.prompts[2]  # the second real turn saw the first
