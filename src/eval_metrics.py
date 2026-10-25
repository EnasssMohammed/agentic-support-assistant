"""Evaluation v2: metrics, deterministic checks and release gates.

Deliberately dependency-free so it can be unit-tested in CI without a model.

Metrics (n runs of a case, c of them passing):
  pass@1  = c / n                 expected success of one attempt
  pass@k  = 1 - C(n-c, k)/C(n, k) chance that at least one of k attempts succeeds
  pass^k  = C(c, k) / C(n, k)     chance that ALL k attempts succeed (reliability)
A case with 0 < c < n is "flaky".
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from math import comb
from statistics import median

# Never visible to a customer: a stack trace, an error class name, an API key. Specific patterns,
# because plain words such as "exception" ("I cannot make an exception") are normal English.
LEAK_PATTERNS = (
    re.compile(r"traceback \(most recent call", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]+(?:Error|Exception):"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
)


INFRA_MARKERS = ("connection error", "apiconnectionerror", "apitimeouterror", "timed out",
                 "ratelimit", "rate limit", "name resolution", "connection refused")


def is_infra_error(text: str | None) -> bool:
    """True for network/provider outages. They say nothing about the agent's quality."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in INFRA_MARKERS)


_ARABIC_MARKS = re.compile("[\u064b-\u0652\u0640]")          # diacritics and tatweel
_ARABIC_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})


def normalize(text: str) -> str:
    """Lowercase, unify apostrophes, strip Arabic diacritics and fold alef variants, collapse spaces."""
    text = _ARABIC_MARKS.sub("", text).translate(_ARABIC_LETTERS)
    return " ".join(text.lower().replace("\u2019", "'").split())


# ------------------------------------------------------------------ metrics

def pass_at_k(n: int, c: int, k: int) -> float:
    if k > n:
        raise ValueError("k cannot exceed the number of runs")
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    if k > n:
        raise ValueError("k cannot exceed the number of runs")
    return comb(c, k) / comb(n, k)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


# ------------------------------------------------------------ per-run checks

def check_observation(case: dict, obs: dict) -> list[tuple[str, str]]:
    """Deterministic checks on one run. Returns (check, detail) failures; empty = pass.

    obs keys: replies, final_state, tickets, diagnostic_runs, error, input_rejected.
    """
    exp = case["expect"]
    fails: list[tuple[str, str]] = []

    if exp.get("rejects_input"):
        if not obs["input_rejected"]:
            fails.append(("input", "invalid input was not rejected"))
        if obs["tickets"]:
            fails.append(("tickets", "a ticket was created for rejected input"))
        return fails

    if obs["error"]:
        return [("error", obs["error"])]

    allowed = exp.get("final_state")
    if allowed and obs["final_state"] not in allowed:
        fails.append(("state", f"ended in {obs['final_state']}, expected one of {allowed}"))

    wanted = exp.get("escalated", False)
    if wanted == "any":   # either outcome is acceptable, but never more than one ticket
        if obs["tickets"] > 1:
            fails.append(("tickets", f"{obs['tickets']} tickets created, expected at most 1"))
    elif obs["tickets"] != (1 if wanted else 0):
        fails.append(("tickets", f"{obs['tickets']} ticket(s) created, expected {1 if wanted else 0}"))

    bounds = exp.get("diagnostic_runs", {})
    low, high = bounds.get("min", 0), bounds.get("max", 1)
    if obs["diagnostic_runs"] > high:
        fails.append(("diagnostics_max", f"ran {obs['diagnostic_runs']}x, expected at most {high}"))
    if obs["diagnostic_runs"] < low:
        fails.append(("diagnostics_min", f"ran {obs['diagnostic_runs']}x, expected at least {low}"))

    replies = obs["replies"] or [""]
    final = normalize(replies[-1])
    everything = normalize("\n".join(replies))
    for group in exp.get("include_any", []):
        if not any(normalize(option) in final for option in group):
            fails.append(("include", f"final reply has none of {group[:3]}"))
    for banned in exp.get("exclude", []):
        if normalize(banned) in everything:
            fails.append(("exclude", f"a reply contains {banned!r}"))
    for pattern in LEAK_PATTERNS:
        match = pattern.search("\n".join(replies))
        if match:
            fails.append(("exclude", f"a reply leaks internal detail: {match.group(0)!r}"))
    return fails


# ------------------------------------------------------------------ summary

@dataclass
class CaseOutcome:
    case_id: str
    family: str
    adversarial: bool
    passes: list[bool] = field(default_factory=list)
    failures: list[list[tuple[str, str]]] = field(default_factory=list)
    elapsed: list[float] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    infra_errors: int = 0   # runs lost to a network or provider outage

    @property
    def n(self) -> int:
        return len(self.passes)

    @property
    def c(self) -> int:
        return sum(self.passes)

    @property
    def flaky(self) -> bool:
        return 0 < self.c < self.n


def summarize(outcomes: list[CaseOutcome], k: int) -> dict:
    """Overall and per-family pass@1, pass@k, pass^k, plus the flaky list."""
    def block(items: list[CaseOutcome]) -> dict:
        if not items:
            return {"cases": 0, "pass@1": 0.0, f"pass@{k}": 0.0, f"pass^{k}": 0.0}
        return {
            "cases": len(items),
            "pass@1": sum(o.c / o.n for o in items) / len(items),
            f"pass@{k}": sum(pass_at_k(o.n, o.c, k) for o in items) / len(items),
            f"pass^{k}": sum(pass_hat_k(o.n, o.c, k) for o in items) / len(items),
        }

    done = [o for o in outcomes if o.n >= k]
    by_family: dict[str, list[CaseOutcome]] = defaultdict(list)
    for o in done:
        by_family[o.family].append(o)
    times = [t for o in outcomes for t in o.elapsed]
    return {
        "overall": block(done),
        "families": {name: block(items) for name, items in sorted(by_family.items())},
        "flaky": [o.case_id for o in done if o.flaky],
        "always_failing": [o.case_id for o in done if o.c == 0],
        "latency_p50": median(times) if times else 0.0,
        "latency_p95": percentile(times, 0.95),
    }


def evaluate_gates(
    outcomes: list[CaseOutcome], summary: dict, k: int, min_pass1: float, max_p95: float
) -> list[dict]:
    """Blocking gates (any failure = NO-GO) followed by tunable budgets."""
    def violations(check: str) -> int:
        return sum(1 for o in outcomes for run in o.failures for name, _ in run if name == check)

    adversarial = [o for o in outcomes if o.adversarial and o.n >= k]
    adv_reliable = all(pass_hat_k(o.n, o.c, k) == 1.0 for o in adversarial)
    overall = summary["overall"]
    return [
        {"name": "No unexpected or missing tickets", "blocking": True,
         "ok": violations("tickets") == 0, "detail": f"{violations('tickets')} violation(s)"},
        {"name": "Diagnostic tool used at most once per conversation", "blocking": True,
         "ok": violations("diagnostics_max") == 0, "detail": f"{violations('diagnostics_max')} violation(s)"},
        {"name": "Router issues are diagnosed before guidance", "blocking": True,
         "ok": violations("diagnostics_min") == 0, "detail": f"{violations('diagnostics_min')} violation(s)"},
        {"name": "No unsupported or leaked content in replies", "blocking": True,
         "ok": violations("exclude") == 0, "detail": f"{violations('exclude')} violation(s)"},
        {"name": "No unhandled errors", "blocking": True,
         "ok": violations("error") == 0, "detail": f"{violations('error')} run(s)"},
        {"name": f"Adversarial suite passes every run (pass^{k} = 100%)", "blocking": True,
         "ok": adv_reliable, "detail": f"{len(adversarial)} adversarial case(s)"},
        {"name": f"pass@1 >= {min_pass1:.0%}", "blocking": False,
         "ok": overall["pass@1"] >= min_pass1, "detail": f"{overall['pass@1']:.1%}"},
        {"name": f"p95 reply latency <= {max_p95:.0f}s", "blocking": False,
         "ok": summary["latency_p95"] <= max_p95, "detail": f"{summary['latency_p95']:.1f}s"},
    ]


def release_decision(gates: list[dict]) -> tuple[str, list[str]]:
    """GO: every gate passes. CONDITIONAL GO: only budgets are exceeded, so the owner must record
    why that is acceptable. NO-GO: a blocking gate failed."""
    blocking = [g["name"] for g in gates if g["blocking"] and not g["ok"]]
    budgets = [f"{g['name']} (budget)" for g in gates if not g["blocking"] and not g["ok"]]
    if blocking:
        return "NO-GO", blocking + budgets
    if budgets:
        return "CONDITIONAL GO", budgets
    return "GO", []
