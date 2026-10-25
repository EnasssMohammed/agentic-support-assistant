"""
Escalation with a complete, staff-facing context package.

A ticket must let a human act without re-reading the whole conversation: what the
customer asked, what was measured, why we escalated, what we told the customer, and
what the human should do next. The suggested action is written for staff and is never
the customer-facing reply.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from src.diagnostics import DiagnosticResult, DiagnosticStatus
from src.schemas import AgentDecision

TICKETS_DIR = Path(os.getenv("VELO_TICKETS_DIR", "tickets"))

Priority = Literal["normal", "high"]


class EscalationTicket(BaseModel):
    ticket_id: str
    created_at: str
    customer_message: str
    conversation_transcript: str | None = None  # set when the conversation had several turns
    diagnostic_result: DiagnosticResult | None = None
    agent_reasoning: str
    policy_cited: str
    suggested_human_action: str                 # instruction for staff
    escalation_kind: str | None = None          # hard_fault | unresolved | model
    priority: Priority = "normal"
    customer_reply: str | None = None           # what the customer was told


def _is_verified_hard_fault(diagnostic: DiagnosticResult | None) -> bool:
    return (
        diagnostic is not None
        and diagnostic.status == DiagnosticStatus.HARD_FAULT
        and not diagnostic.detail.startswith("unverified")
    )


def suggest_human_action(kind: str | None, diagnostic: DiagnosticResult | None) -> str:
    """Write the next step for staff from what is known, not from the customer reply."""
    if _is_verified_hard_fault(diagnostic):
        return (
            f"Hardware fault confirmed by diagnostic ({diagnostic.detail}). "
            "Arrange maintenance or device replacement and contact the customer to schedule it."
        )
    if diagnostic is not None and diagnostic.status == DiagnosticStatus.HARD_FAULT:
        return (
            "Customer reports a hard fault; this was NOT verified by the diagnostic tool. "
            "Run a verified diagnostic before dispatching maintenance."
        )
    if kind == "tool_failure":
        return (
            "The diagnostic tool failed, so the device state is unknown. Run the diagnostic "
            "manually, then contact the customer."
        )
    if kind == "unresolved":
        return (
            "Issue was not resolved by guided troubleshooting. Review the transcript to see "
            "which steps were already tried, then contact the customer with a different approach."
        )
    return "Review the agent's reasoning and the customer's request, then contact the customer."


def create_escalation_ticket(
    customer_message: str,
    decision: AgentDecision,
    retrieved_policy: str,
    conversation_transcript: str | None = None,
    diagnostic: DiagnosticResult | None = None,
    escalation_kind: str | None = None,
    customer_reply: str | None = None,
) -> EscalationTicket:
    """Builds the context package and persists it as a reviewable ticket."""
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    ticket_id = uuid.uuid4().hex[:8]
    while (TICKETS_DIR / f"{ticket_id}.json").exists():
        ticket_id = uuid.uuid4().hex[:8]

    ticket = EscalationTicket(
        ticket_id=ticket_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        customer_message=customer_message,
        conversation_transcript=conversation_transcript,
        diagnostic_result=diagnostic,
        agent_reasoning=decision.reasoning,
        policy_cited=retrieved_policy,
        suggested_human_action=suggest_human_action(escalation_kind, diagnostic),
        escalation_kind=escalation_kind,
        priority="high" if _is_verified_hard_fault(diagnostic) else "normal",
        customer_reply=customer_reply or decision.response_to_user,
    )

    path = TICKETS_DIR / f"{ticket.ticket_id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(ticket.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic: readers never see a half-written ticket
    return ticket
