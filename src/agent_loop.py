"""
Bounded agent loop with conversation state.

This is what turns Velo from "one call that answers" into an agent: it can decide it needs
more evidence (a diagnostic), act on that decision, observe the result, and decide again,
within a hard turn budget so it can never loop forever.

It also remembers the conversation. `reply()` handles one customer message inside a
`Conversation`, so the agent sees earlier messages and Policy Rule #2 can be applied;
`run()` is the single-message shortcut (a brand-new conversation).
"""
from enum import Enum

from src.conversation import Conversation, Role
from src.diagnostics import (
    DiagnosticResult,
    DiagnosticStatus,
    extract_reported_status,
    run_router_diagnostic,
)
from src.escalation import EscalationTicket, create_escalation_ticket
from src.logging_config import get_logger
from src.model_client import ModelClient, ModelClientError
from src.rag_engine import RAGEngine
from src.retrieval_agent import RetrievalAgent
from src.schemas import ActionType, AgentDecision

logger = get_logger("agent_loop")

MAX_TURNS = 3  # model decisions allowed for ONE customer message
MAX_MESSAGE_LENGTH = 2000
UNRESOLVED_TURN_LIMIT = 3  # Policy Rule #2: agent replies allowed before an automatic escalation


class TerminalState(str, Enum):
    RESOLVED = "resolved"
    AWAITING_CUSTOMER = "awaiting_customer"  # the agent asked a question and needs the answer
    ESCALATED = "escalated"
    BUDGET_EXHAUSTED = "budget_exhausted"
    FAILED_SAFELY = "failed_safely"  # model/provider error - no unsafe action was taken


class AgentRunResult:
    def __init__(
        self,
        terminal_state: TerminalState,
        final_decision: AgentDecision | None,
        turns_used: int,
        ticket: EscalationTicket | None = None,
        error_message: str | None = None,
    ):
        self.terminal_state = terminal_state
        self.final_decision = final_decision
        self.turns_used = turns_used
        self.ticket = ticket
        self.error_message = error_message

    def __repr__(self):
        ticket_id = self.ticket.ticket_id if self.ticket else None
        return f"AgentRunResult(state={self.terminal_state}, turns={self.turns_used}, ticket={ticket_id})"


class InvalidInputError(ValueError):
    """Raised for input that should never reach the model at all."""


class VeloAgent:
    def __init__(self, model: ModelClient, rag: RAGEngine):
        self.retrieval_agent = RetrievalAgent(model=model, rag=rag)

    def run(self, user_message: str) -> AgentRunResult:
        """Handle a single message in a brand-new conversation."""
        return self.reply(Conversation(), user_message)

    def reply(self, conversation: Conversation, user_message: str) -> AgentRunResult:
        """Handle the next customer message of `conversation` and record the exchange in it.

        Policy checks are enforced here in code, not only in the prompt, because small local
        models do not always follow them:
        - Rule #1: a Hard Fault is escalated immediately.
        - Rule #2: a customer still writing after 3 agent replies is escalated automatically.
        - The diagnostic tool runs at most once per conversation.

        If the model provider fails, nothing is guessed: the attempt is logged, the
        conversation is left exactly as it was (so the customer can resend), and the result
        is FAILED_SAFELY.
        """
        self._validate_input(user_message)

        if conversation.escalated:
            return self._already_escalated(conversation, user_message)

        history = conversation.transcript()
        agent_replies_so_far = conversation.agent_replies
        conversation.add(Role.CUSTOMER, user_message)

        if agent_replies_so_far >= UNRESOLVED_TURN_LIMIT:
            logger.info(f"Not resolved after {agent_replies_so_far} agent replies - escalating (Rule #2)")
            result = self._escalate(
                conversation, user_message, user_message, self._unresolved_decision(), turn=0
            )
        else:
            result = self._decide_loop(conversation, user_message, history)

        if result.terminal_state == TerminalState.FAILED_SAFELY:
            conversation.drop_last()
            return result
        if result.final_decision is not None:
            conversation.add(Role.AGENT, result.final_decision.response_to_user)
        if result.ticket is not None:
            conversation.ticket = result.ticket
        return result

    def _decide_loop(
        self, conversation: Conversation, user_message: str, history: str
    ) -> AgentRunResult:
        context = user_message

        # A diagnostic outcome stated by the customer counts as a diagnostic result, so the
        # tool is not run to "confirm" it.
        if conversation.diagnostic is None:
            reported_status = extract_reported_status(user_message)
            if reported_status is not None:
                logger.info(f"Customer reported diagnostic status: {reported_status.value}")
                conversation.diagnostic = DiagnosticResult(
                    status=reported_status, detail="reported by the customer"
                )
                if reported_status == DiagnosticStatus.HARD_FAULT:
                    return self._escalate(
                        conversation, user_message, context, self._hard_fault_decision(), turn=0
                    )
        if conversation.diagnostic is not None:
            context = self._with_diagnostic(user_message, conversation.diagnostic)

        for turn in range(1, MAX_TURNS + 1):
            logger.info(f"Turn {turn}/{MAX_TURNS} - deciding...")
            try:
                decision = self.retrieval_agent.decide(context, history=history)
            except ModelClientError as e:
                logger.error(f"Model call failed on turn {turn}: {e}")
                return AgentRunResult(TerminalState.FAILED_SAFELY, None, turn, error_message=str(e))

            logger.info(f"Turn {turn} decision: action={decision.action}, escalate={decision.requires_escalation}")

            if decision.requires_escalation or decision.action == ActionType.ESCALATE:
                return self._escalate(conversation, user_message, context, decision, turn)

            if decision.action == ActionType.RUN_DIAGNOSTIC and conversation.diagnostic is None:
                result = run_router_diagnostic()
                logger.info(f"Diagnostic run: status={result.status.value}")
                conversation.diagnostic = result
                context = self._with_diagnostic(user_message, result)
                if result.status == DiagnosticStatus.HARD_FAULT:
                    # Policy Rule #1 is mandatory, so it is enforced here, not left to the model.
                    return self._escalate(
                        conversation, user_message, context, self._hard_fault_decision(), turn
                    )
                continue

            if decision.action == ActionType.RUN_DIAGNOSTIC:
                logger.warning(
                    "Model requested a second diagnostic call - policy violation. "
                    "Terminating safely instead of looping."
                )
                return AgentRunResult(TerminalState.BUDGET_EXHAUSTED, decision, turn)

            if decision.action == ActionType.ASK_CLARIFYING_QUESTION:
                return AgentRunResult(TerminalState.AWAITING_CUSTOMER, decision, turn)
            return AgentRunResult(TerminalState.RESOLVED, decision, turn)

        logger.warning(f"Turn budget ({MAX_TURNS}) exhausted without resolution.")
        return AgentRunResult(TerminalState.BUDGET_EXHAUSTED, decision, MAX_TURNS)

    def _escalate(
        self,
        conversation: Conversation,
        user_message: str,
        context: str,
        decision: AgentDecision,
        turn: int,
    ) -> AgentRunResult:
        """Write the escalation ticket; finish ESCALATED, or FAILED_SAFELY if it can't be written."""
        try:
            retrieved_policy = self.retrieval_agent.rag.retrieve(context)
            ticket = create_escalation_ticket(
                customer_message=user_message,
                decision=decision,
                retrieved_policy=retrieved_policy,
                conversation_transcript=(
                    conversation.transcript() if conversation.customer_turns > 1 else None
                ),
                diagnostic=conversation.diagnostic,
            )
            logger.info(f"Escalated. Ticket created: {ticket.ticket_id}")
        except Exception as e:
            # Even if ticket creation fails, we must not pretend it worked.
            logger.error(f"Escalation decided but ticket creation failed: {e}")
            return AgentRunResult(TerminalState.FAILED_SAFELY, decision, turn, error_message=str(e))
        return AgentRunResult(TerminalState.ESCALATED, decision, turn, ticket=ticket)

    @staticmethod
    def _already_escalated(conversation: Conversation, user_message: str) -> AgentRunResult:
        ticket = conversation.ticket
        decision = AgentDecision(
            action=ActionType.ESCALATE,
            reasoning="The conversation is already escalated; no new ticket is created.",
            requires_escalation=True,
            response_to_user=(
                f"Your case is already with our support team (ticket {ticket.ticket_id}). "
                "They will follow up with you."
            ),
        )
        conversation.add(Role.CUSTOMER, user_message)
        conversation.add(Role.AGENT, decision.response_to_user)
        return AgentRunResult(TerminalState.ESCALATED, decision, 0, ticket=ticket)

    @staticmethod
    def _with_diagnostic(user_message: str, diagnostic: DiagnosticResult) -> str:
        return (
            f"{user_message}\n\n"
            f"[DIAGNOSTIC RESULT]: status={diagnostic.status.value}, detail={diagnostic.detail}"
        )

    @staticmethod
    def _hard_fault_decision() -> AgentDecision:
        return AgentDecision(
            action=ActionType.ESCALATE,
            reasoning=(
                "Policy Rule #1: a Hard Fault diagnostic result is non-recoverable via user "
                "steps and must be escalated to the human team immediately. Enforced in code, "
                "not left to the model."
            ),
            requires_escalation=True,
            response_to_user=(
                "This needs a technician. I've escalated your case to our support team with "
                "the details, so you won't need to repeat them."
            ),
        )

    @staticmethod
    def _unresolved_decision() -> AgentDecision:
        return AgentDecision(
            action=ActionType.ESCALATE,
            reasoning=(
                f"Policy Rule #2: the issue was not resolved within {UNRESOLVED_TURN_LIMIT} "
                "interaction turns, so the conversation is escalated automatically. Enforced "
                "in code, not left to the model."
            ),
            requires_escalation=True,
            response_to_user=(
                f"I haven't been able to resolve this in {UNRESOLVED_TURN_LIMIT} attempts, so "
                "I've escalated your case to our support team with the whole conversation. "
                "You won't need to repeat yourself."
            ),
        )

    @staticmethod
    def _validate_input(user_message: str) -> None:
        if not user_message or not user_message.strip():
            raise InvalidInputError("Customer message cannot be empty.")
        if len(user_message) > MAX_MESSAGE_LENGTH:
            raise InvalidInputError(
                f"Customer message too long ({len(user_message)} chars, "
                f"max {MAX_MESSAGE_LENGTH})."
            )
