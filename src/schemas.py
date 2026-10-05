"""
Defines the structured shape of every agent decision.

Instead of letting the model return free text, we force it to return JSON
matching this schema. This is what lets the agent loop (Stage 5) make a
real decision in code instead of guessing from a paragraph.
"""
from enum import Enum
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    ANSWER = "answer"                  # enough evidence to resolve directly
    RUN_DIAGNOSTIC = "run_diagnostic"  # need to run a diagnostic tool first
    ASK_CLARIFYING_QUESTION = "ask_clarifying_question"
    ESCALATE = "escalate"              # policy requires human handoff


class AgentDecision(BaseModel):
    action: ActionType
    reasoning: str = Field(description="Why this action was chosen, citing the policy or evidence used")
    requires_escalation: bool
    response_to_user: str = Field(description="What to say to the customer right now")
