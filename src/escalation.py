"""
Stage 6: Escalation with context package.

When the agent decides to escalate, it must NOT just tell the customer
"someone will help you" and discard everything it learned. It must create
a ticket a human can act on immediately: what was asked, what evidence was
gathered (retrieved policy, diagnostic result), and why escalation was
required. This is the agent's only "write" action (see docs/00-problem.md's
success contract: "No writes except creating a ticket").
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from src.schemas import AgentDecision

TICKETS_DIR = Path("tickets")


class EscalationTicket(BaseModel):
    ticket_id: str
    created_at: str
    customer_message: str
    agent_reasoning: str
    policy_cited: str
    suggested_human_action: str


def create_escalation_ticket(
    customer_message: str,
    decision: AgentDecision,
    retrieved_policy: str,
) -> EscalationTicket:
    """Builds the context package and persists it as a reviewable ticket."""
    ticket = EscalationTicket(
        ticket_id=str(uuid.uuid4())[:8],
        created_at=datetime.now(timezone.utc).isoformat(),
        customer_message=customer_message,
        agent_reasoning=decision.reasoning,
        policy_cited=retrieved_policy,
        suggested_human_action=decision.response_to_user or "Review and contact the customer.",
    )

    TICKETS_DIR.mkdir(exist_ok=True)
    ticket_path = TICKETS_DIR / f"{ticket.ticket_id}.json"
    ticket_path.write_text(ticket.model_dump_json(indent=2), encoding="utf-8")

    return ticket
