"""
Stage 4: Diagnostic tools.

A real support agent can't just trust what the customer describes - it runs
a diagnostic and acts on the actual result. This is a MOCK diagnostic (no
real router access), but it's wired the same way a real one would be: a
narrow, single-purpose function with a typed result, not a general-purpose
command runner. That narrowness is itself a safety control (see
docs/00-problem.md's PEAS: actuators are limited to specific, safe actions).
"""
import random
import re
from enum import Enum

from pydantic import BaseModel


class DiagnosticStatus(str, Enum):
    OK = "ok"
    SOFTWARE_GLITCH = "software_glitch"
    HARD_FAULT = "hard_fault"


class DiagnosticResult(BaseModel):
    status: DiagnosticStatus
    detail: str


# Checked in this order: the safer (escalating) status wins if a message mentions both.
_REPORTED_STATUS_PATTERNS = (
    (re.compile(r"hard[\s_-]?fault", re.IGNORECASE), DiagnosticStatus.HARD_FAULT),
    (re.compile(r"software[\s_-]?glitch", re.IGNORECASE), DiagnosticStatus.SOFTWARE_GLITCH),
)


def extract_reported_status(message: str) -> DiagnosticStatus | None:
    """Return the diagnostic status the customer states in their own message, if any.

    A customer who says "diagnostics came back as a Hard Fault" has already given us a
    diagnostic result; running the tool again to confirm it would be pointless.
    """
    for pattern, status in _REPORTED_STATUS_PATTERNS:
        if pattern.search(message):
            return status
    return None


def run_router_diagnostic(device_id: str = "mock-router-01") -> DiagnosticResult:
    """
    MOCK tool: simulates a read-only router health check.
    In production this would call the actual device API. For this project,
    it returns a weighted-random result so we can test every branch of the
    agent's decision logic (OK / recoverable / must-escalate).
    """
    outcome = random.choices(
        population=[DiagnosticStatus.OK, DiagnosticStatus.SOFTWARE_GLITCH, DiagnosticStatus.HARD_FAULT],
        weights=[0.4, 0.4, 0.2],
        k=1,
    )[0]

    details = {
        DiagnosticStatus.OK: "No issues detected. Connection is stable.",
        DiagnosticStatus.SOFTWARE_GLITCH: "Recoverable fault detected (cache/firmware level).",
        DiagnosticStatus.HARD_FAULT: "Critical hardware failure detected (network card/motherboard).",
    }

    return DiagnosticResult(status=outcome, detail=details[outcome])
