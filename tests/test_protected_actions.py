import json

import pytest

from src.approval import ApprovalError, approve_request, get_approval_request, reject_request
from src.protected_actions import dispatch_maintenance, propose_dispatch


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("src.approval.APPROVALS_DIR", tmp_path / "approvals")
    monkeypatch.setattr("src.protected_actions.DISPATCH_DIR", tmp_path / "dispatches")
    return tmp_path


def test_dispatch_is_blocked_while_pending(_dirs):
    req = propose_dispatch("t1", "hard fault")
    with pytest.raises(ApprovalError, match="Pending"):
        dispatch_maintenance(req["request_id"])
    assert not (_dirs / "dispatches").exists()


def test_dispatch_is_blocked_after_rejection(_dirs):
    req = propose_dispatch("t1")
    reject_request(req["request_id"], "e7", "not needed")
    with pytest.raises(ApprovalError, match="Rejected"):
        dispatch_maintenance(req["request_id"])
    assert not (_dirs / "dispatches").exists()


def test_approved_dispatch_runs_and_records_approver(_dirs):
    req = propose_dispatch("t1")
    approve_request(req["request_id"], "e7")
    record = dispatch_maintenance(req["request_id"])
    saved = json.loads((_dirs / "dispatches" / "t1.json").read_text(encoding="utf-8"))
    assert record["approved_by"] == "e7" and saved["ticket_id"] == "t1"
    assert get_approval_request(req["request_id"])["status"] == "Executed"


def test_approval_cannot_be_replayed(_dirs):
    req = propose_dispatch("t1")
    approve_request(req["request_id"], "e7")
    dispatch_maintenance(req["request_id"])
    with pytest.raises(ApprovalError, match="Executed"):
        dispatch_maintenance(req["request_id"])


def test_approval_for_another_action_is_refused(_dirs):
    from src.approval import create_approval_request
    req = create_approval_request("t1", "Reset router")
    approve_request(req["request_id"], "e7")
    with pytest.raises(ApprovalError, match="does not cover"):
        dispatch_maintenance(req["request_id"])
