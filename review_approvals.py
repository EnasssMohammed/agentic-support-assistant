"""Reviewer console for the approval gate.

  uv run python review_approvals.py request <ticket_id>
  uv run python review_approvals.py list [--status Pending]
  uv run python review_approvals.py show <request_id>
  uv run python review_approvals.py approve <request_id> --employee E7
  uv run python review_approvals.py reject  <request_id> --employee E7 --reason "..."
  uv run python review_approvals.py execute <request_id>
"""

import argparse
import json
import sys
from pathlib import Path

from src import approval
from src.escalation import TICKETS_DIR
from src.protected_actions import dispatch_maintenance, propose_dispatch


def _print(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("request"); s.add_argument("ticket_id")
    s = sub.add_parser("list"); s.add_argument("--status")
    s = sub.add_parser("show"); s.add_argument("request_id")
    s = sub.add_parser("approve"); s.add_argument("request_id"); s.add_argument("--employee", required=True)
    s = sub.add_parser("reject"); s.add_argument("request_id"); s.add_argument("--employee", required=True); s.add_argument("--reason", required=True)
    s = sub.add_parser("execute"); s.add_argument("request_id")
    a = p.parse_args(argv)

    try:
        if a.cmd == "request":
            path = Path(TICKETS_DIR) / f"{a.ticket_id}.json"
            if not path.is_file():
                print(f"Ticket not found: {path}", file=sys.stderr)
                return 1
            ticket = json.loads(path.read_text(encoding="utf-8"))
            _print(propose_dispatch(a.ticket_id, ticket.get("suggested_human_action", "")))
        elif a.cmd == "list":
            _print(approval.list_approval_requests(a.status))
        elif a.cmd == "show":
            _print(approval.get_approval_request(a.request_id))
        elif a.cmd == "approve":
            _print(approval.approve_request(a.request_id, a.employee))
        elif a.cmd == "reject":
            _print(approval.reject_request(a.request_id, a.employee, a.reason))
        elif a.cmd == "execute":
            _print(dispatch_maintenance(a.request_id))
    except (approval.ApprovalError, FileNotFoundError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
