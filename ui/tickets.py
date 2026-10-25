"""Read escalation tickets written by the agent and track their workflow status.

Tickets are the JSON files created by src/escalation.py, so the team inbox sees every
escalation from every session. Status lives in a sidecar file and never edits a ticket.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

STATUS_LABELS = {"new": "New", "in_progress": "In progress", "closed": "Closed"}


def _dir() -> Path:
    return Path(os.getenv("VELO_TICKETS_DIR", "tickets"))


def _read_status() -> dict[str, str]:
    path = _dir() / "_status.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_tickets() -> list[dict]:
    """All tickets, newest first, each with a `status` key."""
    directory = _dir()
    if not directory.is_dir():
        return []
    statuses = _read_status()
    tickets: list[dict] = []
    for path in directory.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            ticket = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if "ticket_id" not in ticket:
            continue
        ticket["status"] = statuses.get(ticket["ticket_id"], "new")
        tickets.append(ticket)
    tickets.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return tickets


def set_status(ticket_id: str, status: str) -> None:
    if status not in STATUS_LABELS:
        raise ValueError(f"Unknown status: {status}")
    directory = _dir()
    directory.mkdir(parents=True, exist_ok=True)
    statuses = _read_status()
    statuses[ticket_id] = status
    path = directory / "_status.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(statuses, indent=2), encoding="utf-8")
    tmp.replace(path)


def format_time(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%b %d, %H:%M")
    except (TypeError, ValueError):
        return "—"
