"""The agent keeps the customer's issue (router / account / billing) for the whole conversation.

Regression tests for: "I cannot log in" -> "still not working" -> router restart instructions.
"""
import pytest

from src import approval, escalation
from src import agent_loop as loop
from src.agent_loop import TerminalState, VeloAgent
from src.conversation import Conversation
from src.diagnostics import DiagnosticResult, DiagnosticStatus
from src.model_client import ModelClientError
from src.schemas import ActionType, AgentDecision

LOGIN = "لا أستطيع تسجيل الدخول إلى حسابي"
ROUTER = "الإنترنت منقطع عندي بالكامل"
STILL = "ما زالت المشكلة قائمة، نفس المشكلة"


def dec(action=ActionType.ANSWER, text="رد", escalate=False):
    return AgentDecision(action=action, reasoning="r", requires_escalation=escalate, response_to_user=text)


class ScriptedModel:
    def __init__(self, script):
        self.script, self.prompts = list(script), []

    def generate_structured(self, messages, schema):
        self.prompts.append(messages[-1]["content"])
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class RecordingRAG:
    def __init__(self):
        self.calls = []

    def retrieve(self, query, k=3, topic=None):
        self.calls.append((query, topic))
        return "POLICY"


class DownRAG:
    """The embedding service is unreachable."""

    def retrieve(self, query, k=3, topic=None):
        raise RuntimeError("APIConnectionError: Connection error.")


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(escalation, "TICKETS_DIR", tmp_path / "tickets")
    monkeypatch.setattr(approval, "APPROVALS_DIR", tmp_path / "approvals")
    diagnostics = []
    monkeypatch.setattr(
        loop, "run_router_diagnostic",
        lambda forced_status=None, **kw: diagnostics.append(1)
        or DiagnosticResult(status=forced_status or DiagnosticStatus.SOFTWARE_GLITCH, detail="d"),
    )
    return diagnostics


def make(script, status=DiagnosticStatus.SOFTWARE_GLITCH):
    model, rag = ScriptedModel(script), RecordingRAG()
    return VeloAgent(model=model, rag=rag, diagnostic_status=status), model, rag


def test_login_followup_stays_on_the_account_issue(sandbox):
    agent, model, _ = make([dec(text="خطوات الدخول")])
    conv = Conversation()
    agent.reply(conv, LOGIN)
    assert conv.topic == "account"

    second = agent.reply(conv, STILL)
    assert second.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert len(model.prompts) == 1                       # scripted evidence request, no model call
    assert "رسالة الخطأ" in second.reply_text
    assert "لمبة" not in second.reply_text and "الراوتر" not in second.reply_text
    assert conv.topic == "account"


def test_followup_with_evidence_continues_the_same_issue_via_the_model(sandbox):
    agent, model, rag = make([dec(text="خطوات الدخول"), dec(ActionType.ASK_CLARIFYING_QUESTION, "هل وصلتك الرسالة؟")])
    conv = Conversation()
    agent.reply(conv, LOGIN)
    agent.reply(conv, "ما زالت المشكلة قائمة، الخطأ يقول كلمة المرور غير صحيحة، جربت نسيت كلمة المرور، ولا أستخدم المصادقة الثنائية")
    assert len(model.prompts) == 2
    assert "[ISSUE TOPIC]: account" in model.prompts[-1]
    assert "[DIAGNOSTIC RESULT]" not in model.prompts[-1]


def test_account_conversation_only_retrieves_account_policy(sandbox):
    agent, _, rag = make([dec(), dec()])
    conv = Conversation()
    agent.reply(conv, LOGIN)
    agent.reply(conv, "ما زالت المشكلة قائمة، الخطأ يقول كذا، جربت نسيت كلمة المرور، ولا أستخدم المصادقة الثنائية")
    assert rag.calls and all(topic == "account" for _, topic in rag.calls)
    assert all(query.startswith(LOGIN) for query, _ in rag.calls)


def test_topic_switch_starts_a_clean_issue(sandbox):
    agent, model, _ = make([dec(ActionType.RUN_DIAGNOSTIC), dec(text="الراوتر"), dec(text="الدخول")])
    conv = Conversation()
    agent.reply(conv, ROUTER)
    assert conv.topic == "router"

    agent.reply(conv, LOGIN)
    assert conv.topic == "account" and conv.issue == LOGIN
    assert conv.replies_in_issue() == 1                  # attempts restart with the new issue
    sent = model.prompts[-1]
    assert "الإنترنت منقطع" not in sent and "[DIAGNOSTIC RESULT]" not in sent
    assert "[ISSUE TOPIC]: account" in sent


def test_unresolved_login_issue_escalates_after_the_attempt_limit(sandbox):
    agent, _, _ = make([dec(text="خطوات الدخول")])
    conv = Conversation()
    agent.reply(conv, LOGIN)
    agent.reply(conv, STILL)
    agent.reply(conv, STILL)
    result = agent.reply(conv, STILL)
    assert result.terminal_state == TerminalState.ESCALATED
    assert result.ticket.customer_message == LOGIN       # the ticket names the issue, not "still broken"
    assert conv.escalated


def test_account_issue_cannot_trigger_a_router_diagnostic(sandbox):
    agent, model, _ = make([dec(ActionType.RUN_DIAGNOSTIC), dec(text="خطوات الدخول")])
    result = agent.reply(Conversation(), LOGIN)
    assert sandbox == []                                 # the diagnostic never ran
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert "Router diagnostics do not apply" in model.prompts[-1]


def test_router_flow_is_unchanged(sandbox):
    agent, model, _ = make([dec(ActionType.RUN_DIAGNOSTIC), dec(text="أعد تشغيل الراوتر")])
    conv = Conversation()
    first = agent.reply(conv, ROUTER)
    assert first.terminal_state == TerminalState.AWAITING_CUSTOMER and sandbox == [1]
    assert conv.topic == "router" and "[DIAGNOSTIC RESULT]" in model.prompts[-1]

    second = agent.reply(conv, STILL)
    assert "لمبة" in second.reply_text and len(model.prompts) == 2


def test_hard_fault_reported_in_a_followup_still_escalates_immediately(sandbox):
    agent, model, _ = make([dec(ActionType.ASK_CLARIFYING_QUESTION, "ما لون اللمبة؟")])
    conv = Conversation()
    agent.reply(conv, "My router is broken.")            # a question first, so no diagnostic has run yet
    result = agent.reply(conv, "ما زالت المشكلة قائمة، والفحص أظهر Hard Fault")
    assert result.terminal_state == TerminalState.ESCALATED and result.ticket is not None
    assert len(model.prompts) == 1                       # escalated by rule, not by the model


def test_a_measured_diagnostic_outranks_a_later_customer_claim(sandbox):
    agent, model, _ = make([dec(ActionType.RUN_DIAGNOSTIC), dec(text="أعد التشغيل"), dec(text="رد")])
    conv = Conversation()
    agent.reply(conv, ROUTER)                            # the tool measured a software glitch
    result = agent.reply(conv, "ما زالت المشكلة قائمة، والفحص أظهر Hard Fault")
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert len(model.prompts) == 3


def test_confirmed_hard_fault_diagnostic_escalates_a_router_issue(sandbox):
    agent, _, _ = make([dec(ActionType.RUN_DIAGNOSTIC)], status=DiagnosticStatus.HARD_FAULT)
    result = agent.reply(Conversation(), ROUTER)
    assert result.terminal_state == TerminalState.ESCALATED


def test_failed_model_call_restores_the_issue_state(sandbox):
    agent, _, _ = make([dec(ActionType.RUN_DIAGNOSTIC), dec(text="الراوتر"), ModelClientError("down")])
    conv = Conversation()
    agent.reply(conv, "My router has no internet.")
    before = (conv.topic, conv.issue, conv.issue_start, len(conv.messages))

    failed = agent.reply(conv, LOGIN)
    assert failed.terminal_state == TerminalState.FAILED_SAFELY
    assert (conv.topic, conv.issue, conv.issue_start, len(conv.messages)) == before


def test_a_message_without_a_topic_keeps_the_current_issue(sandbox):
    agent, _, _ = make([dec(), dec()])
    conv = Conversation()
    agent.reply(conv, LOGIN)
    agent.reply(conv, "حاولت ذلك ولم يتغير شيء")
    assert conv.topic == "account" and conv.issue == LOGIN


def test_confirmation_resolves_without_changing_the_issue(sandbox):
    agent, _, _ = make([dec()])
    conv = Conversation()
    agent.reply(conv, LOGIN)
    result = agent.reply(conv, "تم الحل، الإنترنت اشتغل")
    assert result.terminal_state == TerminalState.RESOLVED and conv.topic == "account"


def test_issue_transcript_contains_only_the_current_issue(sandbox):
    agent, _, _ = make([dec(ActionType.RUN_DIAGNOSTIC), dec(text="الراوتر"), dec(text="الدخول")])
    conv = Conversation()
    agent.reply(conv, ROUTER)
    agent.reply(conv, LOGIN)
    assert ROUTER not in conv.issue_transcript() and LOGIN in conv.issue_transcript()
    assert ROUTER in conv.transcript()                   # staff still get the full conversation


def test_a_first_message_that_sounds_like_a_followup_still_opens_the_issue(sandbox):
    # "no internet" is also a "still broken" phrase; with no issue open it is a problem statement.
    agent, model, _ = make([dec(ActionType.RUN_DIAGNOSTIC), dec(text="أعد تشغيل الراوتر")])
    conv = Conversation()
    result = agent.reply(conv, "My router has no internet.")
    assert conv.topic == "router" and conv.issue == "My router has no internet."
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER and sandbox == [1]
    assert "[DIAGNOSTIC RESULT]" in model.prompts[-1]


def test_router_guidance_without_a_diagnostic_triggers_the_diagnostic_by_policy(sandbox):
    # The model answers straight away; policy (Rule 3 as code) runs the diagnostic first.
    agent, model, _ = make([dec(text="أعد تشغيل الراوتر"), dec(text="أعد تشغيل الراوتر")])
    result = agent.reply(Conversation(), ROUTER)
    assert sandbox == [1] and result.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert "[DIAGNOSTIC RESULT]" in model.prompts[-1]


def test_a_customer_claim_cannot_skip_the_diagnostic(sandbox):
    agent, _, _ = make([dec(), dec()])
    agent.reply(Conversation(), "The diagnostic says software glitch, my internet is down.")
    assert sandbox == [1]


def test_a_clarifying_question_does_not_force_a_diagnostic(sandbox):
    agent, _, _ = make([dec(ActionType.ASK_CLARIFYING_QUESTION, "ما لون اللمبة؟")])
    result = agent.reply(Conversation(), "My router is broken.")
    assert sandbox == [] and result.terminal_state == TerminalState.AWAITING_CUSTOMER


def test_a_model_that_keeps_asking_for_a_second_diagnostic_is_escalated(sandbox):
    agent, _, _ = make([dec(ActionType.RUN_DIAGNOSTIC)] * 3)
    result = agent.reply(Conversation(), ROUTER)
    assert sandbox == [1]                                # only the first request is honoured
    assert result.terminal_state == TerminalState.ESCALATED and result.ticket is not None


def test_a_knowledge_base_outage_fails_safely_and_keeps_the_conversation(sandbox):
    agent = VeloAgent(model=ScriptedModel([dec()]), rag=DownRAG())
    conv = Conversation()
    result = agent.reply(conv, LOGIN)
    assert result.terminal_state == TerminalState.FAILED_SAFELY
    assert "Connection error" not in result.reply_text   # no internal detail reaches the customer
    assert conv.messages == [] and conv.topic is None    # the customer can simply resend


def test_escalation_still_creates_the_ticket_when_retrieval_is_down(sandbox):
    agent = VeloAgent(model=ScriptedModel([]), rag=DownRAG())
    result = agent.reply(Conversation(), "Diagnostics came back as a Hard Fault on my router.")
    assert result.terminal_state == TerminalState.ESCALATED and result.ticket is not None
    assert "unavailable" in result.ticket.policy_cited


def test_the_model_cannot_escalate_a_router_issue_before_a_diagnostic(sandbox):
    # A red light is a symptom. The model asks to escalate; policy diagnoses first.
    agent, model, _ = make([dec(ActionType.ESCALATE, escalate=True), dec(text="أعد تشغيل الراوتر")])
    result = agent.reply(Conversation(), "لمبة الإنترنت في الراوتر حمراء")
    assert sandbox == [1]
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER and result.ticket is None
    assert "[DIAGNOSTIC RESULT]" in model.prompts[-1]


def test_a_confirmed_hard_fault_still_escalates_after_the_forced_diagnostic(sandbox):
    agent, _, _ = make([dec(ActionType.ESCALATE, escalate=True)], status=DiagnosticStatus.HARD_FAULT)
    result = agent.reply(Conversation(), "لمبة الإنترنت في الراوتر حمراء")
    assert result.terminal_state == TerminalState.ESCALATED and result.ticket is not None


def test_an_account_issue_can_still_be_escalated_by_the_model(sandbox):
    # The diagnose-first rule belongs to router issues only.
    agent, _, _ = make([dec(ActionType.ESCALATE, escalate=True)])
    result = agent.reply(Conversation(), LOGIN)
    assert result.terminal_state == TerminalState.ESCALATED and sandbox == []
