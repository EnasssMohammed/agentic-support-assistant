"""
Ablation arms for evaluation v2: the same 38 frozen cases, run through weaker systems.

The guide asks for a measurable comparison, not a claim:

    baseline  one model call, no retrieval, no tools, no state, no policy        (src/baseline.py)
    rag       retrieval + the structured decision, with history, but NO code-level
              policy, NO diagnostic tool and NO ticket tool. The model proposes
              and nothing enforces.
    agent     the full VeloAgent (src/agent_loop.py)

Both arms expose the same ``reply(conversation, message)`` as VeloAgent and return an
``AgentRunResult``, so ``run_eval_v2.py`` scores them with the same deterministic checks.
They are comparison evidence only. They are never release candidates.
"""
from __future__ import annotations

from src import responses
from src.agent_loop import AgentRunResult, TerminalState
from src.baseline import BaselineAgent
from src.conversation import Conversation, Role
from src.model_client import ModelClient, ModelClientError
from src.rag_engine import RAGEngine
from src.retrieval_agent import RetrievalAgent
from src.schemas import ActionType, AgentDecision

ARMS = ("agent", "rag", "baseline")


class _ModelHolder:
    """Lets the runner inject a model failure the same way it does for VeloAgent."""

    def __init__(self, model: ModelClient):
        self.model = model


def _failed(turns: int, exc: Exception) -> AgentRunResult:
    return AgentRunResult(
        TerminalState.FAILED_SAFELY, None, turns,
        error_message=str(exc), customer_message=responses.temporarily_unavailable(),
    )


class BaselineArm:
    """Stage-1 baseline: every message is a fresh, ungrounded single call."""

    name = "baseline"

    def __init__(self, model: ModelClient):
        self.retrieval_agent = _ModelHolder(model)

    def reply(self, conversation: Conversation, user_message: str) -> AgentRunResult:
        try:
            text = BaselineAgent(self.retrieval_agent.model).answer(user_message)
        except ModelClientError as exc:
            return _failed(1, exc)
        decision = AgentDecision(
            action=ActionType.ANSWER, reasoning="baseline: single call",
            requires_escalation=False, response_to_user=text or "",
        )
        return AgentRunResult(TerminalState.AWAITING_CUSTOMER, decision, 1)


class RagOnlyArm:
    """Retrieval + structured decision + history. The model's proposal is accepted as is."""

    name = "rag"

    def __init__(self, model: ModelClient, rag: RAGEngine):
        self.retrieval_agent = RetrievalAgent(model=model, rag=rag)

    def reply(self, conversation: Conversation, user_message: str) -> AgentRunResult:
        history = conversation.transcript()
        conversation.add(Role.CUSTOMER, user_message)
        try:
            decision = self.retrieval_agent.decide(user_message, history=history)
        except ModelClientError as exc:
            conversation.drop_last()
            return _failed(1, exc)
        conversation.add(Role.AGENT, decision.response_to_user)
        wants_human = decision.requires_escalation or decision.action == ActionType.ESCALATE
        # No ticket tool exists in this arm: an escalation is only words.
        state = TerminalState.ESCALATED if wants_human else TerminalState.AWAITING_CUSTOMER
        return AgentRunResult(state, decision, 1)


def build_arm(name: str, model: ModelClient, rag: RAGEngine):
    if name == "baseline":
        return BaselineArm(model)
    if name == "rag":
        return RagOnlyArm(model, rag)
    raise ValueError(f"Unknown arm {name!r}; the full agent is built by run_eval_v2.py itself.")
