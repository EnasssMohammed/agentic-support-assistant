"""Pure unit test - no LLM involved, should run in under a second."""
from src.diagnostics import DiagnosticResult, DiagnosticStatus, run_router_diagnostic


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
