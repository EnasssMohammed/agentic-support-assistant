"""
Stage 5: Bounded agent loop.

This is what turns Velo from "one call that answers" into an agent: it can
decide it needs more evidence (a diagnostic), act on that decision, observe
the result, and decide again - within a hard turn budget so it can never
loop forever (see docs/00-problem.md's success contract: <= 8 turns).
"""
from enum import Enum
from src.model_client import ModelClient
from src.rag_engine import RAGEngine
from src.retrieval_agent import RetrievalAgent
from src.diagnostics import run_router_diagnostic
from src.schemas import ActionType, AgentDecision

MAX_TURNS = 3


class TerminalState(str, Enum):
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    BUDGET_EXHAUSTED = "budget_exhausted"


class AgentRunResult:
    def __init__(self, terminal_state: TerminalState, final_decision: AgentDecision, turns_used: int):
        self.terminal_state = terminal_state
        self.final_decision = final_decision
        self.turns_used = turns_used

    def __repr__(self):
        return f"AgentRunResult(state={self.terminal_state}, turns={self.turns_used})"


class VeloAgent:
    def __init__(self, model: ModelClient, rag: RAGEngine):
        self.retrieval_agent = RetrievalAgent(model=model, rag=rag)

    def run(self, user_message: str) -> AgentRunResult:
        """Runs the bounded decide -> (diagnose) -> decide loop."""
        context = user_message

        for turn in range(1, MAX_TURNS + 1):
            decision = self.retrieval_agent.decide(context)

            if decision.requires_escalation or decision.action == ActionType.ESCALATE:
                return AgentRunResult(TerminalState.ESCALATED, decision, turn)

            if decision.action == ActionType.RUN_DIAGNOSTIC:
                result = run_router_diagnostic()
                # Feed the diagnostic result back in as new evidence for the next decision.
                context = (
                    f"{user_message}\n\n"
                    f"[DIAGNOSTIC RESULT]: status={result.status.value}, detail={result.detail}"
                )
                continue  # decide again with the new evidence

            # ANSWER or ASK_CLARIFYING_QUESTION both end the loop as resolved.
            return AgentRunResult(TerminalState.RESOLVED, decision, turn)

        # Loop exhausted its budget without reaching a clean resolution.
        return AgentRunResult(TerminalState.BUDGET_EXHAUSTED, decision, MAX_TURNS)
