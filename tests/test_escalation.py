"""Pure unit test - builds a fake AgentDecision manually, no LLM involved."""
import json
from pathlib import Path

from src.escalation import create_escalation_ticket, TICKETS_DIR
from src.schemas import AgentDecision, ActionType


def test_creates_ticket_file_with_full_context():
    fake_decision = AgentDecision(
        action=ActionType.ESCALATE,
        reasoning="Hard Fault diagnostic result requires immediate human escalation per Policy Rule #1.",
        requires_escalation=True,
        response_to_user="I've escalated this to our support team.",
    )

    ticket = create_escalation_ticket(
        customer_message="Diagnostics came back as a Hard Fault on my router.",
        decision=fake_decision,
        retrieved_policy="Hard Fault -> escalate immediately, non-recoverable via user steps.",
    )

    ticket_path = TICKETS_DIR / f"{ticket.ticket_id}.json"
    assert ticket_path.exists()

    saved = json.loads(ticket_path.read_text(encoding="utf-8"))
    assert saved["customer_message"] == "Diagnostics came back as a Hard Fault on my router."
    assert "Policy Rule #1" in saved["agent_reasoning"]
    assert saved["policy_cited"] != ""
