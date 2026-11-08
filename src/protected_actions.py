"""The consequential action behind the human approval gate.

Dispatching a maintenance visit costs money and commits staff, so the agent can only
*propose* it. It runs only after a human approved the request, and each approval
works once. The dispatch itself is simulated: it writes a record to DISPATCH_DIR.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import approval

DISPATCH_DIR = Path(os.getenv("VELO_DISPATCH_DIR", "dispatches"))
PROPOSED_ACTION = "Dispatch maintenance visit"


def propose_dispatch(ticket_id: str, evidence: str = "") -> dict[str, Any]:
    """Agent side: ask for approval. Nothing is dispatched here."""
    return approval.create_approval_request(ticket_id, PROPOSED_ACTION, evidence)


def dispatch_maintenance(request_id: str) -> dict[str, Any]:
    """Run the protected action. Raises ApprovalError unless a human approved it."""
    request = approval.require_approval(request_id)
    if request["proposed_action"] != PROPOSED_ACTION:
        raise approval.ApprovalError("This approval does not cover a maintenance dispatch.")

    approval.mark_executed(request_id)  # consume first: a failure cannot be replayed

    record = {
        "ticket_id": request["ticket_id"],
        "approval_request_id": request_id,
        "approved_by": request["employee_id"],
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "note": "Simulated dispatch (no external system is called).",
    }
    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    (DISPATCH_DIR / f"{request['ticket_id']}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    return record
