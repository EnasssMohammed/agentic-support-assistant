"""Greetings and "who are you?" get a fixed reply; an unrecognised issue never becomes a ticket on its own."""

import pytest

from src import approval, escalation
from src.agent_loop import TerminalState, VeloAgent
from src.conversation import Conversation
from src.diagnostics import DiagnosticStatus
from src.intents import is_greeting, is_identity_question
from src.schemas import ActionType, AgentDecision


class _Rag:
    def retrieve(self, query, k=3, topic=None):
        return "policy"


class _Model:
    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def generate_structured(self, messages, schema):
        self.calls += 1
        return self.decisions.pop(0) if len(self.decisions) > 1 else self.decisions[0]


def _decision(action, text="..."):
    return AgentDecision(action=action, reasoning="r", requires_escalation=False, response_to_user=text)


@pytest.fixture(autouse=True)
def _tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation, "TICKETS_DIR", tmp_path / "tickets")
    monkeypatch.setattr(approval, "APPROVALS_DIR", tmp_path / "approvals")


@pytest.mark.parametrize("text", [
    "مرحبا", "مرحباً!", "أهلاً وسهلاً", "السلام عليكم ورحمة الله وبركاته", "صباح الخير",
    "مرحبا كيف حالك", "Hello", "hi there", "Good morning", "how are you",
])
def test_greetings_are_recognised(text):
    assert is_greeting(text)


@pytest.mark.parametrize("text", [
    "مرحبا الراوتر معطل", "hello my router is down", "الانترنت مقطوع", "كيف أعيد ضبط الراوتر",
    "hi, I was charged twice", "good", "help", "نسيت كلمة السر", "ما اشتغل",
])
def test_a_greeting_followed_by_a_problem_is_not_small_talk(text):
    assert not is_greeting(text)


@pytest.mark.parametrize("text", [
    "من انت", "من أنت؟", "مين انت", "ما اسمك", "هل انت روبوت", "ماذا تفعل", "who are you?", "What can you do",
])
def test_identity_questions_are_recognised(text):
    assert is_identity_question(text)


@pytest.mark.parametrize("text", [
    "من انت لتقول لي ذلك والراوتر معطل", "ماذا تفعل لو الراوتر معطل", "what are the router lights",
])
def test_identity_pattern_needs_the_whole_message(text):
    assert not is_identity_question(text)


def test_greeting_does_not_call_the_model_or_change_the_conversation():
    model = _Model(_decision(ActionType.RUN_DIAGNOSTIC))
    agent = VeloAgent(model=model, rag=_Rag())
    conv = Conversation()
    result = agent.reply(conv, "مرحبا")
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert result.ticket is None
    assert "Velo" in result.reply_text
    assert model.calls == 0
    assert (conv.messages, conv.topic, conv.issue) == ([], None, None)


def test_greeting_in_an_open_issue_does_not_reuse_the_old_diagnostic():
    model = _Model(
        _decision(ActionType.RUN_DIAGNOSTIC),
        _decision(ActionType.ANSWER, "أعد تشغيل الراوتر"),
    )
    agent = VeloAgent(model=model, rag=_Rag(), diagnostic_status=DiagnosticStatus.SOFTWARE_GLITCH)
    conv = Conversation()
    agent.reply(conv, "الانترنت مقطوع عندي")
    calls, size, replies = model.calls, len(conv.messages), conv.replies_in_issue()

    agent.reply(conv, "مرحبا")
    agent.reply(conv, "من انت")

    assert model.calls == calls                      # the model never saw either message
    assert len(conv.messages) == size                # nothing was stored
    assert conv.replies_in_issue() == replies        # and no attempt was counted
    assert conv.topic == "router"


def test_identity_reply_is_in_the_customer_language():
    agent = VeloAgent(model=_Model(_decision(ActionType.ANSWER)), rag=_Rag())
    arabic = agent.reply(Conversation(), "من انت").reply_text
    english = agent.reply(Conversation(), "who are you").reply_text
    assert "مساعد" in arabic and "assistant" in english


def test_unrecognised_issue_asks_for_details_instead_of_opening_a_ticket():
    # The model keeps asking for a diagnostic the policy rejects (no router issue was recognised).
    model = _Model(_decision(ActionType.RUN_DIAGNOSTIC, "أجري فحصاً"))
    agent = VeloAgent(model=model, rag=_Rag())
    conv = Conversation()
    result = agent.reply(conv, "عندي شي غريب يصير")
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert result.ticket is None
    assert conv.escalated is False
