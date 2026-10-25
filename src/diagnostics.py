"""
Diagnostic tools.

A real support agent can't just trust what the customer describes: it runs a diagnostic
and acts on the actual result. This is a MOCK, read-only diagnostic wired like a real one:
a narrow, single-purpose function with a typed result, not a general command runner.
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

# "it's not a hard fault" must not count as a report of a hard fault.
_NEGATION_BEFORE = re.compile(
    r"\b(?:not|no|isn't|wasn't|never|without|ruled out)\b(?:\s+\w+){0,2}\s*$", re.IGNORECASE
)

_DETAILS = {
    DiagnosticStatus.OK: "No issues detected. Connection is stable.",
    DiagnosticStatus.SOFTWARE_GLITCH: "Recoverable fault detected (cache/firmware level).",
    DiagnosticStatus.HARD_FAULT: "Critical hardware failure detected (network card/motherboard).",
}


def extract_reported_status(message: str) -> DiagnosticStatus | None:
    """Return the diagnostic status the customer states in their own message, if any.

    This is a customer CLAIM, not a measurement. Callers must not treat it as tool output.
    """
    for pattern, status in _REPORTED_STATUS_PATTERNS:
        for match in pattern.finditer(message):
            if not _NEGATION_BEFORE.search(message[: match.start()]):
                return status
    return None


def run_router_diagnostic(
    device_id: str = "mock-router-01",
    forced_status: DiagnosticStatus | None = None,
    rng: random.Random | None = None,
) -> DiagnosticResult:
    """
    MOCK tool: simulates a read-only router health check.

    forced_status gives tests a deterministic outcome. Pass a seeded ``random.Random`` as
    ``rng`` to make evaluation runs reproducible; otherwise the outcome is weighted-random.
    """
    if forced_status is not None:
        outcome = forced_status
    else:
        outcome = (rng or random).choices(
            population=[
                DiagnosticStatus.OK,
                DiagnosticStatus.SOFTWARE_GLITCH,
                DiagnosticStatus.HARD_FAULT,
            ],
            weights=[0.4, 0.4, 0.2],
            k=1,
        )[0]

    return DiagnosticResult(status=outcome, detail=_DETAILS[outcome])
