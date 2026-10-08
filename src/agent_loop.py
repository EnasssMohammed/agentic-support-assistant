"""
Stage 5: Bounded agent loop.

This is what turns Velo from "one call that answers" into an agent: it can
decide it needs more evidence (a diagnostic), act on that decision, observe
the result, and decide again - within a hard turn budget so it can never
loop forever (see docs/00-problem.md's success contract: <= 8 turns).
"""
from enum import Enum

from src.diagnostics import run_router_diagnostic
from src.escalation import EscalationTicket, create_escalation_ticket
from src.logging_config import get_logger
from src.model_client import ModelClient, ModelClientError
from src.rag_engine import RAGEngine
from src.retrieval_agent import RetrievalAgent
from src.schemas import ActionType, AgentDecision

logger = get_logger("agent_loop")

MAX_TURNS = 3
MAX_MESSAGE_LENGTH = 2000


class TerminalState(str, Enum):
    RESOLVED = "resolved"
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
        """Runs the bounded decide -> (diagnose) -> decide loop.

        Policy check (code-level, not just prompt-level): the diagnostic
        tool may run at most ONCE per conversation. Small local models
        sometimes ignore the "don't ask again" instruction in the prompt,
        so this is enforced here instead of trusted to the model.

        Error handling: if the model provider fails or returns something
        unusable, the loop does NOT crash or silently guess - it logs the
        failure and returns FAILED_SAFELY so the caller can retry or hand
        off to a human, same as any other terminal state.
        """
        self._validate_input(user_message)

        context = user_message
        diagnostic_already_run = False

        for turn in range(1, MAX_TURNS + 1):
            logger.info(f"Turn {turn}/{MAX_TURNS} - deciding...")
            try:
                decision = self.retrieval_agent.decide(context)
            except ModelClientError as e:
                logger.error(f"Model call failed on turn {turn}: {e}")
                return AgentRunResult(
                    TerminalState.FAILED_SAFELY, None, turn, error_message=str(e)
                )

            logger.info(f"Turn {turn} decision: action={decision.action}, escalate={decision.requires_escalation}")

            if decision.requires_escalation or decision.action == ActionType.ESCALATE:
                try:
                    retrieved_policy = self.retrieval_agent.rag.retrieve(context)
                    ticket = create_escalation_ticket(
                        customer_message=user_message,
                        decision=decision,
                        retrieved_policy=retrieved_policy,
                    )
                    logger.info(f"Escalated. Ticket created: {ticket.ticket_id}")
                except Exception as e:
                    # Even if ticket creation fails, we must not pretend it worked.
                    logger.error(f"Escalation decided but ticket creation failed: {e}")
                    return AgentRunResult(
                        TerminalState.FAILED_SAFELY, decision, turn, error_message=str(e)
                    )
                return AgentRunResult(TerminalState.ESCALATED, decision, turn, ticket=ticket)

            if decision.action == ActionType.RUN_DIAGNOSTIC and not diagnostic_already_run:
                diagnostic_already_run = True
                result = run_router_diagnostic()
                logger.info(f"Diagnostic run: status={result.status.value}")
                context = (
                    f"{user_message}\n\n"
                    f"[DIAGNOSTIC RESULT]: status={result.status.value}, detail={result.detail}"
                )
                continue

            if decision.action == ActionType.RUN_DIAGNOSTIC and diagnostic_already_run:
                logger.warning(
                    "Model requested a second diagnostic call - policy violation. "
                    "Terminating safely instead of looping."
                )
                return AgentRunResult(TerminalState.BUDGET_EXHAUSTED, decision, turn)

            return AgentRunResult(TerminalState.RESOLVED, decision, turn)

        logger.warning(f"Turn budget ({MAX_TURNS}) exhausted without resolution.")
        return AgentRunResult(TerminalState.BUDGET_EXHAUSTED, decision, MAX_TURNS)

    @staticmethod
    def _validate_input(user_message: str) -> None:
        if not user_message or not user_message.strip():
            raise InvalidInputError("Customer message cannot be empty.")
        if len(user_message) > MAX_MESSAGE_LENGTH:
            raise InvalidInputError(
                f"Customer message too long ({len(user_message)} chars, "
                f"max {MAX_MESSAGE_LENGTH})."
            )
