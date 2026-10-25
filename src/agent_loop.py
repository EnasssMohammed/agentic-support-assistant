"""Velo agent controller: a bounded, policy-enforced support loop.

The model proposes; this module decides. Anything that must hold regardless of what
the model says (turn limits, escalation rules, trust in diagnostics) lives here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src import responses
from src.approval import create_approval_request
from src.conversation import Conversation, Role
from src.diagnostics import (
    DiagnosticResult,
    DiagnosticStatus,
    extract_reported_status,
    run_router_diagnostic,
)
from src.escalation import EscalationTicket, create_escalation_ticket
from src.intents import (
    classify_topic,
    customer_confirms_resolution,
    customer_reports_unresolved,
    extract_topic_evidence,
    is_vague_issue,
)
from src.logging_config import get_logger
from src.model_client import ModelClient, ModelClientError
from src.rag_engine import RAGEngine
from src.responses import EscalationKind
from src.retrieval_agent import RetrievalAgent
from src.schemas import ActionType, AgentDecision

logger = get_logger("agent_loop")

MAX_TURNS = 3                 # model decision cycles per customer message
MAX_MESSAGE_LENGTH = 2000
UNRESOLVED_TURN_LIMIT = 3     # Policy Rule #2: agent replies before forced escalation

_REPEAT_DIAGNOSTIC_FEEDBACK = (
    "[POLICY FEEDBACK]: A diagnostic has already been run for this conversation and "
    "cannot be repeated. Use the existing result and answer, ask one clarifying "
    "question, or escalate."
)


_SYSTEM_MARKER = re.compile(r"\[\s*(DIAGNOSTIC RESULT|POLICY FEEDBACK|ISSUE TOPIC)\s*\]", re.IGNORECASE)


def _neutralize_markers(text: str) -> str:
    """Customers must not be able to forge the markers the system appends itself."""
    return _SYSTEM_MARKER.sub(r"(\1)", text)


_WRONG_TOPIC_DIAGNOSTIC_FEEDBACK = (
    "[POLICY FEEDBACK]: Router diagnostics do not apply to this {topic} issue. Do not "
    "request a diagnostic. Answer from the {topic} policy, ask one clarifying question, "
    "or escalate."
)


class TerminalState(str, Enum):
    RESOLVED = "resolved"
    AWAITING_CUSTOMER = "awaiting_customer"
    ESCALATED = "escalated"
    BUDGET_EXHAUSTED = "budget_exhausted"   # kept for compatibility; loop now escalates instead
    FAILED_SAFELY = "failed_safely"


class InvalidInputError(ValueError):
    """Raised when invalid input must not reach the model."""


@dataclass
class AgentRunResult:
    terminal_state: TerminalState
    final_decision: AgentDecision | None
    turns_used: int
    ticket: EscalationTicket | None = None
    error_message: str | None = None          # internal detail, never shown to customers
    approval_request: dict | None = None
    customer_message: str | None = None       # overrides the decision text when set

    @property
    def reply_text(self) -> str:
        """The text that is safe to show to the customer."""
        if self.customer_message:
            return responses.tidy(self.customer_message)
        if self.final_decision is not None:
            return responses.tidy(self.final_decision.response_to_user)
        return responses.temporarily_unavailable()


class VeloAgent:
    def __init__(
        self,
        model: ModelClient,
        rag: RAGEngine,
        diagnostic_status: DiagnosticStatus | None = None,
    ):
        self.retrieval_agent = RetrievalAgent(model=model, rag=rag)
        self.diagnostic_status = diagnostic_status

    # ------------------------------------------------------------------ public

    def run(self, user_message: str) -> AgentRunResult:
        """Handle one message in a new conversation."""
        return self.reply(Conversation(), user_message)

    def reply(self, conversation: Conversation, user_message: str) -> AgentRunResult:
        """Handle a customer message and update the conversation state."""
        self._validate_input(user_message)

        if conversation.escalated:
            return self._already_escalated(conversation, user_message)

        snapshot = (conversation.topic, conversation.issue, conversation.issue_start)
        conversation.add(Role.CUSTOMER, user_message)
        self._track_issue(conversation, user_message)

        # Everything below is scoped to the CURRENT issue: its history, its attempts, its topic.
        history = conversation.issue_transcript(exclude_last=True)
        previous_replies = conversation.replies_in_issue()

        if customer_confirms_resolution(user_message):
            logger.info("Customer confirmed resolution.")
            return self._finish(conversation, self._resolved(), snapshot)

        if previous_replies >= UNRESOLVED_TURN_LIMIT:
            logger.info("Unresolved after %d replies; escalating.", previous_replies)
            result = self._escalate(
                conversation, user_message, user_message, EscalationKind.UNRESOLVED, turn=0
            )
            return self._finish(conversation, result, snapshot)

        # A reported Hard Fault must escalate immediately (Policy Rule #1), so it is never
        # swallowed by the "still not working" follow-up below.
        claims_hard_fault = extract_reported_status(user_message) == DiagnosticStatus.HARD_FAULT
        if previous_replies > 0 and customer_reports_unresolved(user_message) and not claims_hard_fault:
            follow_up = self._follow_up(conversation)
            if follow_up is not None:
                return self._finish(conversation, follow_up, snapshot)
            # Enough evidence collected: let the model and diagnostics take over.

        return self._finish(
            conversation, self._decide_loop(conversation, user_message, history), snapshot
        )

    # --------------------------------------------------------------- main loop

    def _decide_loop(
        self, conversation: Conversation, user_message: str, history: str
    ) -> AgentRunResult:
        user_message_for_model = _neutralize_markers(user_message)
        history = _neutralize_markers(history)
        topic = conversation.topic
        context = self._context(user_message_for_model, topic, conversation.diagnostic)

        if conversation.diagnostic is None:
            claim = extract_reported_status(user_message)
            if claim == DiagnosticStatus.HARD_FAULT:
                # Escalating is the safe direction, so an unverified claim may trigger it.
                conversation.diagnostic = DiagnosticResult(
                    status=claim, detail="unverified: reported by the customer"
                )
                return self._escalate(
                    conversation, user_message, context, EscalationKind.HARD_FAULT, turn=0
                )
            if claim is not None:
                # A customer cannot substitute their own claim for a real diagnostic.
                logger.info("Ignoring unverified customer claim: %s", claim.value)

        if conversation.diagnostic is None and is_vague_issue(user_message):
            decision = AgentDecision(
                action=ActionType.ASK_CLARIFYING_QUESTION,
                reasoning="Vague issue reported; asking for details before diagnostics.",
                requires_escalation=False,
                response_to_user=responses.ask_for_details(),
            )
            return AgentRunResult(TerminalState.AWAITING_CUSTOMER, decision, turns_used=0)

        for turn in range(1, MAX_TURNS + 1):
            logger.info("Turn %d/%d: deciding", turn, MAX_TURNS)
            try:
                decision = self.retrieval_agent.decide(context, history=history, topic=topic)
            except ModelClientError as exc:
                logger.error("Model call failed on turn %d: %s", turn, exc)
                return AgentRunResult(
                    TerminalState.FAILED_SAFELY,
                    None,
                    turn,
                    error_message=str(exc),
                    customer_message=responses.temporarily_unavailable(),
                )

            logger.info(
                "Turn %d decision: action=%s escalate=%s",
                turn, decision.action, decision.requires_escalation,
            )

            if (
                (decision.requires_escalation or decision.action == ActionType.ESCALATE)
                and topic == "router"
                and conversation.diagnostic is None
            ):
                # A red light is a symptom, not a Hard Fault. Only a confirmed Hard Fault may
                # escalate a router issue immediately, and that path never reaches this point.
                logger.info("Policy: a router issue is diagnosed before the model may escalate it.")
                decision = decision.model_copy(
                    update={"action": ActionType.RUN_DIAGNOSTIC, "requires_escalation": False}
                )

            if decision.requires_escalation or decision.action == ActionType.ESCALATE:
                return self._escalate(
                    conversation, user_message, context, EscalationKind.MODEL, turn, decision
                )

            if (
                decision.action == ActionType.ANSWER
                and topic == "router"
                and conversation.diagnostic is None
            ):
                # Rule 3 enforced in code: a router issue is diagnosed before any guidance.
                # Measured on a real model, the prompt alone was followed only some of the time.
                logger.info("Policy: diagnosing before answering a router issue.")
                decision = decision.model_copy(update={"action": ActionType.RUN_DIAGNOSTIC})

            if decision.action == ActionType.RUN_DIAGNOSTIC:
                if topic in ("account", "billing"):
                    # The router tool has nothing to say about this issue; reject and re-plan.
                    logger.warning("Diagnostic rejected for a %s issue; replanning.", topic)
                    context = f"{context}\n\n{_WRONG_TOPIC_DIAGNOSTIC_FEEDBACK.format(topic=topic)}"
                    continue
                if conversation.diagnostic is not None:
                    # Policy rejects the plan; feed the reason back and replan.
                    logger.warning("Repeated diagnostic rejected; replanning.")
                    context = f"{context}\n\n{_REPEAT_DIAGNOSTIC_FEEDBACK}"
                    continue

                try:
                    diagnostic = run_router_diagnostic(forced_status=self.diagnostic_status)
                except Exception:  # a failing tool must end in a handoff, never a crash
                    logger.exception("Diagnostic tool failed; escalating.")
                    return self._escalate(
                        conversation, user_message, context, EscalationKind.TOOL_FAILURE, turn
                    )
                logger.info("Diagnostic result: %s", diagnostic.status.value)
                conversation.diagnostic = diagnostic
                context = self._context(user_message_for_model, topic, diagnostic)

                if diagnostic.status == DiagnosticStatus.HARD_FAULT:
                    return self._escalate(
                        conversation, user_message, context, EscalationKind.HARD_FAULT, turn
                    )
                continue

            if decision.action in (ActionType.ASK_CLARIFYING_QUESTION, ActionType.ANSWER):
                return AgentRunResult(TerminalState.AWAITING_CUSTOMER, decision, turn)

            logger.warning("Unhandled action %s; replanning.", decision.action)

        logger.warning("Turn budget (%d) exhausted; escalating.", MAX_TURNS)
        return self._escalate(
            conversation, user_message, context, EscalationKind.UNRESOLVED, MAX_TURNS
        )

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _resolved() -> AgentRunResult:
        decision = AgentDecision(
            action=ActionType.ANSWER,
            reasoning="The customer explicitly confirmed that the issue is fixed.",
            requires_escalation=False,
            response_to_user=responses.resolved(),
        )
        return AgentRunResult(TerminalState.RESOLVED, decision, turns_used=0)

    @staticmethod
    def _follow_up(conversation: Conversation) -> AgentRunResult | None:
        """Ask only for evidence we still lack, for the CURRENT topic.

        Returns None when nothing is missing or the topic has no scripted follow-up; the
        model then continues the same issue with the history and the topic marker.
        """
        evidence = extract_topic_evidence(
            conversation.topic, _customer_text(conversation, conversation.issue_start)
        )
        missing = evidence.missing() if evidence is not None else ()
        if not missing:
            return None
        decision = AgentDecision(
            action=ActionType.ASK_CLARIFYING_QUESTION,
            reasoning="Issue persists; requesting missing evidence without repeating steps.",
            requires_escalation=False,
            response_to_user=responses.request_missing_details(missing),
        )
        return AgentRunResult(TerminalState.AWAITING_CUSTOMER, decision, turns_used=0)

    def _escalate(
        self,
        conversation: Conversation,
        user_message: str,
        context: str,
        kind: EscalationKind,
        turn: int,
        decision: AgentDecision | None = None,
    ) -> AgentRunResult:
        decision = decision or self._policy_decision(kind)
        customer_reply = responses.escalation_notice(
            kind, model_text=decision.response_to_user, attempts=UNRESOLVED_TURN_LIMIT
        )
        try:
            retrieved_policy = self.retrieval_agent.policy_for(context, conversation.topic)
        except Exception:
            # The handoff to a human matters more than the policy excerpt that enriches it.
            logger.warning("Policy lookup failed during escalation; creating the ticket without it.")
            retrieved_policy = "Policy lookup was unavailable when this ticket was created."
        try:
            ticket = create_escalation_ticket(
                customer_message=conversation.issue or user_message,
                decision=decision,
                retrieved_policy=retrieved_policy,
                conversation_transcript=(
                    conversation.transcript() if conversation.customer_turns > 1 else None
                ),
                diagnostic=conversation.diagnostic,
                escalation_kind=kind.value,
                customer_reply=customer_reply,
            )
            approval_request = create_approval_request(
                ticket_id=ticket.ticket_id,
                proposed_action=ticket.suggested_human_action,
                evidence=ticket.policy_cited,
            )
        except Exception as exc:  # escalation must fail loudly, never silently
            logger.exception("Escalation required, but ticket creation failed.")
            return AgentRunResult(
                TerminalState.FAILED_SAFELY,
                None,
                turn,
                error_message=f"ticket creation failed: {exc}",
                customer_message=responses.escalation_failed(),
            )

        logger.info("Escalated (%s). Ticket: %s", kind.value, ticket.ticket_id)
        notice = decision.model_copy(
            update={
                "response_to_user": responses.escalation_notice(
                    kind,
                    ticket.ticket_id,
                    model_text=decision.response_to_user,
                    attempts=UNRESOLVED_TURN_LIMIT,
                )
            }
        )
        return AgentRunResult(
            TerminalState.ESCALATED, notice, turn,
            ticket=ticket, approval_request=approval_request,
        )

    @staticmethod
    def _policy_decision(kind: EscalationKind) -> AgentDecision:
        if kind is EscalationKind.HARD_FAULT:
            rule = "Policy Rule #1: confirmed hard fault must be escalated immediately."
        elif kind is EscalationKind.TOOL_FAILURE:
            rule = "Diagnostic tool failed; the device state cannot be verified, so the case is escalated."
        else:
            rule = f"Policy Rule #2: not resolved within {UNRESOLVED_TURN_LIMIT} turns."
        return AgentDecision(
            action=ActionType.ESCALATE,
            reasoning=rule,
            requires_escalation=True,
            response_to_user=responses.escalation_notice(
                kind, attempts=UNRESOLVED_TURN_LIMIT
            ),
        )

    @staticmethod
    def _already_escalated(conversation: Conversation, user_message: str) -> AgentRunResult:
        ticket = conversation.ticket
        ticket_id = ticket.ticket_id if ticket is not None else "غير متاح"
        decision = AgentDecision(
            action=ActionType.ESCALATE,
            reasoning="The conversation is already escalated; no new ticket created.",
            requires_escalation=True,
            response_to_user=responses.already_escalated(ticket_id),
        )
        conversation.add(Role.CUSTOMER, user_message)
        conversation.add(Role.AGENT, decision.response_to_user)
        return AgentRunResult(TerminalState.ESCALATED, decision, 0, ticket=ticket)

    @staticmethod
    def _finish(
        conversation: Conversation, result: AgentRunResult, snapshot: tuple | None = None
    ) -> AgentRunResult:
        if result.terminal_state == TerminalState.FAILED_SAFELY:
            conversation.drop_last()   # the customer can resend; state stays consistent
            if snapshot is not None:
                conversation.topic, conversation.issue, conversation.issue_start = snapshot
            return result
        conversation.add(Role.AGENT, result.reply_text)
        if result.ticket is not None:
            conversation.ticket = result.ticket
        return result

    @staticmethod
    def _track_issue(conversation: Conversation, message: str) -> None:
        """Remember which issue this conversation is about.

        Once an issue is open, a follow-up ("still not working", "fixed") never changes it. A message that
        clearly names a different topic starts a new issue: its own history, its own
        attempt count. A message with no recognisable topic keeps the current one.
        """
        index = len(conversation.messages) - 1
        is_follow_up = customer_confirms_resolution(message) or customer_reports_unresolved(message)
        if is_follow_up and conversation.issue is not None:
            return  # "still broken" belongs to the issue already open
        # With no issue open yet, even "I have no internet" is a problem statement, not a follow-up.
        topic = classify_topic(message)
        if topic == "other":
            if conversation.topic is None and conversation.issue is None:
                conversation.issue, conversation.issue_start = message, index
            return
        if topic != conversation.topic:
            logger.info("Issue topic: %s -> %s", conversation.topic, topic)
            conversation.topic, conversation.issue, conversation.issue_start = topic, message, index

    @staticmethod
    def _diagnostic_line(diagnostic: DiagnosticResult) -> str:
        return f"[DIAGNOSTIC RESULT]: status={diagnostic.status.value}, detail={diagnostic.detail}"

    @classmethod
    def _with_diagnostic(cls, user_message: str, diagnostic: DiagnosticResult) -> str:
        return f"{user_message}\n\n{cls._diagnostic_line(diagnostic)}"

    @classmethod
    def _context(
        cls, message: str, topic: str | None, diagnostic: DiagnosticResult | None
    ) -> str:
        """The latest message plus the system lines the model may trust."""
        parts = [message]
        if topic:
            parts.append(f"[ISSUE TOPIC]: {topic}")
        if diagnostic is not None and topic == "router":
            # A router diagnostic must not leak into an account or billing conversation.
            parts.append(cls._diagnostic_line(diagnostic))
        return "\n\n".join(parts)

    @staticmethod
    def _validate_input(user_message: str) -> None:
        if not user_message or not user_message.strip():
            raise InvalidInputError("Customer message cannot be empty.")
        if len(user_message) > MAX_MESSAGE_LENGTH:
            raise InvalidInputError(
                f"Customer message too long ({len(user_message)} chars, max {MAX_MESSAGE_LENGTH})."
            )


def _customer_messages(conversation: Conversation, start: int = 0) -> list[str]:
    """Customer messages from `start` on (the Conversation API has no accessor for this)."""
    customer = getattr(Role.CUSTOMER, "value", Role.CUSTOMER)
    messages: list[str] = []
    for message in conversation.messages[start:]:
        role = getattr(message, "role", None)
        if getattr(role, "value", role) != customer:
            continue
        content = getattr(message, "content", None) or getattr(message, "text", "")
        if isinstance(content, str):
            messages.append(content)
    return messages


def _customer_text(conversation: Conversation, start: int = 0) -> str:
    return " ".join(_customer_messages(conversation, start))
