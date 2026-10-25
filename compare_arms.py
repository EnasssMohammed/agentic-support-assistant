"""
Put the evaluation arms side by side: the evidence that agentic complexity pays for itself.

    uv run python compare_arms.py baseline=reports/eval_v2_baseline_openai_gpt-5-nano.json \
                                  rag=reports/eval_v2_rag_openai_gpt-5-nano.json \
                                  agent=reports/eval_v2_openai_gpt-5-nano.json

All arms must use the same cases file, the same model and the same k, otherwise the comparison
is refused. Writes reports/arm_comparison.md and prints it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HIGHLIGHT = ("adversarial", "escalation", "no_evidence", "connectivity", "refund", "tool_failure")


class ComparisonError(ValueError):
    """The reports are not comparable."""


def load_report(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_comparable(reports: dict[str, dict]) -> None:
    metas = {label: r["meta"] for label, r in reports.items()}
    for field in ("model", "provider", "cases_file", "runs", "total_cases"):
        values = {str(m.get(field)) for m in metas.values()}
        if len(values) > 1:
            raise ComparisonError(f"Arms differ in '{field}': {sorted(values)}. Re-run them under the same setup.")
    if any(m.get("dry_run") for m in metas.values()):
        raise ComparisonError("A dry run verifies the harness only; it cannot be compared.")
    if any(r["decision"] == "INVALID RUN" for r in reports.values()):
        raise ComparisonError("An INVALID RUN (provider outage) cannot be compared.")


def render(reports: dict[str, dict]) -> str:
    check_comparable(reports)
    meta = next(iter(reports.values()))["meta"]
    k = meta["runs"]
    labels = list(reports)
    header = "| Measure | " + " | ".join(labels) + " |"
    sep = "|---|" + "---|" * len(labels)

    def row(name, fn):
        return f"| {name} | " + " | ".join(fn(reports[label]) for label in labels) + " |"

    pct = lambda v: f"{v:.1%}"  # noqa: E731
    lines = [
        f"# Arm comparison: {meta['provider']} / {meta['model']}",
        "",
        f"- Cases: {meta['total_cases']} frozen cases (`{meta['cases_file']}`), {k} run(s) each",
        "- Same cases, same model, same deterministic checks for every arm.",
        "",
        "## Overall",
        "",
        header, sep,
        row("pass@1", lambda r: pct(r["summary"]["overall"]["pass@1"])),
        row(f"pass@{k} (capability)", lambda r: pct(r["summary"]["overall"][f"pass@{k}"])),
        row(f"pass^{k} (reliability)", lambda r: pct(r["summary"]["overall"][f"pass^{k}"])),
        row("Flaky cases", lambda r: str(len(r["summary"]["flaky"]))),
        row("Always failing", lambda r: str(len(r["summary"]["always_failing"]))),
        row("Latency p95 per reply", lambda r: f"{r['summary']['latency_p95']:.1f}s"),
        row("Blocking gates passed",
            lambda r: f"{sum(g['ok'] for g in r['gates'] if g['blocking'])}/{sum(g['blocking'] for g in r['gates'])}"),
        row("Decision", lambda r: r["decision"]),
        "",
        f"## pass^{k} by family",
        "",
        header, sep,
    ]
    families = [f for f in HIGHLIGHT if all(f in r["summary"]["families"] for r in reports.values())]
    families += sorted(
        {f for r in reports.values() for f in r["summary"]["families"]} - set(families)
    )
    for family in families:
        lines.append(row(family, lambda r, f=family: (
            pct(r["summary"]["families"][f][f"pass^{k}"]) if f in r["summary"]["families"] else "n/a")))
    lines += [
        "",
        "## How to read this",
        "",
        "- `baseline` has no retrieval, tools, state or policy. Its failures are the problem statement.",
        "- `rag` adds grounded retrieval and history but no tools and no code-level policy. The gap between "
        "`baseline` and `rag` is what retrieval buys; the gap between `rag` and `agent` is what tools, state "
        "and enforced policy buy.",
        "- Ablation arms cannot create tickets or run diagnostics, so they fail those checks by construction. "
        "Judge them on the families where that is not the whole story (no_evidence, refund, adversarial).",
        "- A larger cost or latency with no gain would be a valid conclusion too: report it either way.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    pairs = [a.split("=", 1) for a in args if "=" in a]
    if len(pairs) < 2:
        print(__doc__)
        return 2
    try:
        text = render({label: load_report(Path(p)) for label, p in pairs})
    except (ComparisonError, FileNotFoundError, KeyError) as exc:
        print(f"Cannot compare: {exc}")
        return 1
    out = Path("reports/arm_comparison.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
