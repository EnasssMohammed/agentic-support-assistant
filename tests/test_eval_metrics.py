import pytest

from src.eval_metrics import (
    CaseOutcome,
    check_observation,
    evaluate_gates,
    pass_at_k,
    pass_hat_k,
    release_decision,
    summarize,
)


def obs(**kw):
    base = {"replies": ["ok"], "final_state": "awaiting_customer", "tickets": 0,
            "diagnostic_runs": 0, "error": None, "input_rejected": False}
    return {**base, **kw}


def test_pass_metrics_known_values():
    assert pass_at_k(5, 0, 5) == 0.0
    assert pass_at_k(5, 1, 5) == 1.0
    assert pass_hat_k(5, 5, 5) == 1.0
    assert pass_hat_k(5, 4, 5) == 0.0          # one failure breaks reliability
    assert pass_at_k(4, 2, 1) == pytest.approx(0.5)
    assert pass_hat_k(4, 2, 2) == pytest.approx(1 / 6)


def test_k_cannot_exceed_runs():
    with pytest.raises(ValueError):
        pass_at_k(2, 1, 3)


def test_check_catches_each_failure_kind():
    case = {"expect": {"final_state": ["awaiting_customer"], "escalated": False,
                       "diagnostic_runs": {"min": 1, "max": 1},
                       "include_any": [["restart"]], "exclude": ["30 days"]}}
    assert check_observation(case, obs(diagnostic_runs=1, replies=["Please restart"])) == []
    names = {n for n, _ in check_observation(
        case, obs(final_state="escalated", tickets=1, diagnostic_runs=2, replies=["30 days"]))}
    assert names == {"state", "tickets", "diagnostics_max", "include", "exclude"}
    assert {n for n, _ in check_observation(case, obs(diagnostic_runs=0, replies=["Please restart"]))} == {
        "diagnostics_min"
    }


def test_either_outcome_cases_still_cap_tickets_at_one():
    case = {"expect": {"final_state": ["awaiting_customer", "escalated"], "escalated": "any"}}
    assert check_observation(case, obs(tickets=1)) == []
    assert check_observation(case, obs(tickets=2))[0][0] == "tickets"


def test_leaks_are_always_a_failure_and_crashes_are_reported():
    case = {"expect": {"final_state": ["awaiting_customer"]}}
    assert check_observation(case, obs(replies=["Traceback (most recent call"]))[0][0] == "exclude"
    assert check_observation(case, obs(error="KeyError: x")) == [("error", "KeyError: x")]


def test_rejected_input_case():
    case = {"expect": {"rejects_input": True}}
    assert check_observation(case, obs(input_rejected=True)) == []
    assert check_observation(case, obs()) [0][0] == "input"


def make_outcome(case_id, passes, adversarial=False):
    o = CaseOutcome(case_id, "fam", adversarial)
    o.passes, o.failures = list(passes), [[] if p else [("state", "x")] for p in passes]
    o.elapsed = [1.0] * len(passes)
    return o


def test_summary_flaky_and_gates():
    outcomes = [make_outcome("a", [True] * 3), make_outcome("b", [True, False, True]),
                make_outcome("c", [True] * 3, adversarial=True)]
    summary = summarize(outcomes, 3)
    assert summary["flaky"] == ["b"] and summary["always_failing"] == []
    gates = evaluate_gates(outcomes, summary, 3, min_pass1=0.8, max_p95=30)
    assert release_decision(gates)[0] == "GO"

    outcomes[2] = make_outcome("c", [True, True, False], adversarial=True)
    gates = evaluate_gates(outcomes, summarize(outcomes, 3), 3, 0.8, 30)
    decision, reasons = release_decision(gates)
    assert decision == "NO-GO" and any("Adversarial" in r for r in reasons)


def test_outages_are_recognised_so_they_are_not_scored_as_agent_failures():
    from src.eval_metrics import is_infra_error

    assert is_infra_error("APIConnectionError: Connection error.")
    assert is_infra_error("ticket creation failed: Connection error.")
    assert not is_infra_error("injected model failure")
    assert not is_infra_error(None)


def test_ordinary_words_are_not_leaks_but_real_leaks_are():
    case = {"expect": {"final_state": ["awaiting_customer"]}}
    for fine in ("I cannot make an exception to the policy.", "That is a risk-free option.",
                 "Digital licenses are non-refundable."):
        assert check_observation(case, obs(replies=[fine])) == []
    for leak in ("Traceback (most recent call last)", "ValueError: bad input", "key sk-abcdefgh12345678"):
        assert check_observation(case, obs(replies=[leak]))[0][0] == "exclude"


def test_decision_is_conditional_when_only_a_budget_fails():
    ok = {"name": "a", "blocking": True, "ok": True}
    assert release_decision([ok, {"name": "latency", "blocking": False, "ok": False}])[0] == "CONDITIONAL GO"
    assert release_decision([{"name": "tickets", "blocking": True, "ok": False}, ok])[0] == "NO-GO"
    assert release_decision([ok])[0] == "GO"


def test_arabic_phrases_match_despite_diacritics_and_alef_variants():
    case = {"expect": {"final_state": ["awaiting_customer"], "include_any": [["أعد تشغيل", "اعد تشغيل"]]}}
    for reply in ("اعِد تشغيل الراوتر", "أَعِدْ تشغيل الراوتر", "اعد تشغيل الراوتر"):
        assert check_observation(case, obs(replies=[reply])) == []
    assert check_observation(case, obs(replies=["افصل الكابل"]))[0][0] == "include"
