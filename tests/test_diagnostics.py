"""Pure unit test - no LLM involved, should run in under a second."""
import pytest

from src.diagnostics import (
    DiagnosticResult,
    DiagnosticStatus,
    extract_reported_status,
    run_router_diagnostic,
)


def test_diagnostic_returns_valid_result():
    result = run_router_diagnostic()
    assert isinstance(result, DiagnosticResult)
    assert result.status in DiagnosticStatus
    assert len(result.detail) > 0


def test_diagnostic_distribution_covers_all_branches():
    # Run it enough times that all three outcomes should appear at least once.
    # This isn't a strict guarantee (it's random) but with 200 runs and the
    # lowest weight at 0.2, the odds of missing HARD_FAULT entirely are ~1e-19.
    seen = {run_router_diagnostic().status for _ in range(200)}
    assert seen == {DiagnosticStatus.OK, DiagnosticStatus.SOFTWARE_GLITCH, DiagnosticStatus.HARD_FAULT}


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Diagnostics came back as a Hard Fault on my router.", DiagnosticStatus.HARD_FAULT),
        ("status: hard_fault", DiagnosticStatus.HARD_FAULT),
        ("HARD-FAULT detected", DiagnosticStatus.HARD_FAULT),
        ("The diagnostic says software glitch.", DiagnosticStatus.SOFTWARE_GLITCH),
        ("software_glitch", DiagnosticStatus.SOFTWARE_GLITCH),
        ("Hard fault and also a software glitch", DiagnosticStatus.HARD_FAULT),  # safer one wins
        ("The router shows a red internet light.", None),
        ("I forgot my password.", None),
    ],
)
def test_extract_reported_status(message, expected):
    assert extract_reported_status(message) == expected
