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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    request = sub.add_parser("request")
    request.add_argument("ticket_id")

    listing = sub.add_parser("list")
    listing.add_argument("--status")

    show = sub.add_parser("show")
    show.add_argument("request_id")

    approve = sub.add_parser("approve")
    approve.add_argument("request_id")
    approve.add_argument("--employee", required=True)

    reject = sub.add_parser("reject")
    reject.add_argument("request_id")
    reject.add_argument("--employee", required=True)
    reject.add_argument("--reason", required=True)

    execute = sub.add_parser("execute")
    execute.add_argument("request_id")
    return parser


def _request_from_ticket(ticket_id: str) -> int:
    path = Path(TICKETS_DIR) / f"{ticket_id}.json"
    if not path.is_file():
        print(f"Ticket not found: {path}", file=sys.stderr)
        return 1
    ticket = json.loads(path.read_text(encoding="utf-8"))
    _print(propose_dispatch(ticket_id, ticket.get("suggested_human_action", "")))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "request":
            return _request_from_ticket(args.ticket_id)
        if args.cmd == "list":
            _print(approval.list_approval_requests(args.status))
        elif args.cmd == "show":
            _print(approval.get_approval_request(args.request_id))
        elif args.cmd == "approve":
            _print(approval.approve_request(args.request_id, args.employee))
        elif args.cmd == "reject":
            _print(approval.reject_request(args.request_id, args.employee, args.reason))
        elif args.cmd == "execute":
            _print(dispatch_maintenance(args.request_id))
    except (approval.ApprovalError, FileNotFoundError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
