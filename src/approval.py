
"""Persistent human approval requests for protected actions."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVALS_DIR = Path("approval_requests")


class ApprovalError(RuntimeError):
    """Raised when an approval request cannot authorize an action."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_path(request_id: str) -> Path:
    # Prevent path traversal through a caller-supplied request ID.
    if not request_id or Path(request_id).name != request_id:
        raise ValueError("Invalid request ID.")
    return APPROVALS_DIR / f"{request_id}.json"


def create_approval_request(
    ticket_id: str,
    proposed_action: str,
    evidence: str = "",
) -> dict[str, Any]:
    """Create a pending approval request linked to an escalation ticket."""
    if not ticket_id.strip():
        raise ValueError("ticket_id is required.")
    if not proposed_action.strip():
        raise ValueError("proposed_action is required.")

    request = {
        "request_id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "proposed_action": proposed_action,
        "evidence": evidence,
        "status": "Pending",
        "created_at": _now(),
        "employee_id": None,
        "decided_at": None,
        "rejection_reason": None,
    }

    APPROVALS_DIR.mkdir(parents=True, exist_ok=True)
    _request_path(request["request_id"]).write_text(
        json.dumps(request, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return request


def get_approval_request(request_id: str) -> dict[str, Any]:
    """Load an approval request from disk."""
    path = _request_path(request_id)
    if not path.is_file():
        raise FileNotFoundError(f"Approval request not found: {request_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(request: dict[str, Any]) -> dict[str, Any]:
    _request_path(request["request_id"]).write_text(
        json.dumps(request, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return request


def approve_request(request_id: str, employee_id: str) -> dict[str, Any]:
    """Approve a pending request and record who made the decision."""
    if not employee_id.strip():
        raise ValueError("employee_id is required.")

    request = get_approval_request(request_id)
    if request["status"] != "Pending":
        raise ApprovalError("Only pending requests can be approved.")

    request["status"] = "Approved"
    request["employee_id"] = employee_id
    request["decided_at"] = _now()
    return _save(request)


def reject_request(
    request_id: str,
    employee_id: str,
    reason: str,
) -> dict[str, Any]:
    """Reject a pending request and record the reason."""
    if not employee_id.strip():
        raise ValueError("employee_id is required.")
    if not reason.strip():
        raise ValueError("A rejection reason is required.")

    request = get_approval_request(request_id)
    if request["status"] != "Pending":
        raise ApprovalError("Only pending requests can be rejected.")

    request["status"] = "Rejected"
    request["employee_id"] = employee_id
    request["decided_at"] = _now()
    request["rejection_reason"] = reason
    return _save(request)


def require_approval(request_id: str) -> dict[str, Any]:
    """Return the approved request or block the protected action."""
    request = get_approval_request(request_id)
    if request["status"] != "Approved":
        raise ApprovalError(
            f"Protected action blocked: approval status is {request['status']}."
        )
    return request
