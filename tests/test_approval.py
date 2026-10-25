
import pytest

from src.approval import (
    ApprovalError,
    approve_request,
    create_approval_request,
    get_approval_request,
    reject_request,
    require_approval,
)


def test_pending_request_blocks_protected_action(tmp_path, monkeypatch):
    monkeypatch.setattr("src.approval.APPROVALS_DIR", tmp_path)
    request = create_approval_request("ticket-123", "Reset router")

    with pytest.raises(ApprovalError, match="Pending"):
        require_approval(request["request_id"])


def test_approved_request_allows_protected_action(tmp_path, monkeypatch):
    monkeypatch.setattr("src.approval.APPROVALS_DIR", tmp_path)
    request = create_approval_request("ticket-123", "Reset router")

    approve_request(request["request_id"], "employee-7")
    saved = require_approval(request["request_id"])

    assert saved["status"] == "Approved"
    assert saved["employee_id"] == "employee-7"
    assert saved["decided_at"] is not None


def test_rejected_request_blocks_protected_action(tmp_path, monkeypatch):
    monkeypatch.setattr("src.approval.APPROVALS_DIR", tmp_path)
    request = create_approval_request("ticket-123", "Reset router")

    reject_request(request["request_id"], "employee-7", "Customer confirmation needed")

    saved = get_approval_request(request["request_id"])
    assert saved["status"] == "Rejected"
    assert saved["rejection_reason"] == "Customer confirmation needed"

    with pytest.raises(ApprovalError, match="Rejected"):
        require_approval(request["request_id"])


def test_cannot_approve_request_twice(tmp_path, monkeypatch):
    monkeypatch.setattr("src.approval.APPROVALS_DIR", tmp_path)
    request = create_approval_request("ticket-123", "Reset router")
    approve_request(request["request_id"], "employee-7")

    with pytest.raises(ApprovalError, match="pending"):
        approve_request(request["request_id"], "employee-8")
