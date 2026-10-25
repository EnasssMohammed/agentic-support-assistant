"""
Retrieval check: does an Arabic question find the same policy entry as the English one?

    uv run python run_retrieval_check.py

Uses your real embeddings (MODEL_PROVIDER in .env). For every query it shows the top passages,
then reports hit@1 / hit@3 per language, with and without the topic filter, and how often the
FIRST passage belongs to the wrong topic (the failure that produced router steps for a login
problem). Writes reports/retrieval_check_<provider>.md.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.intents import classify_topic

# (language, query, acceptable entry names)
CASES = [
    ("en", "My router has a red Internet light and no connectivity", ["Error 500 - Router Connection Fault"]),
    ("en", "The diagnostic says software glitch", ["Diagnostic Result: 'Software Glitch'"]),
    ("en", "The diagnostic reported a hard fault", ["Diagnostic Result: 'Hard Fault'", "Policy Rule #1 - Hard Fault Escalation"]),
    ("en", "The issue is still not resolved after several attempts", ["Policy Rule #2 - Maximum Retry Limit"]),
    ("en", "Can I return a product I bought last week?", ["Return Window"]),
    ("en", "Can I get a refund for my digital license?", ["Non-Refundable Items"]),
    ("en", "I cannot log in, my account is locked after wrong passwords", ["Locked Account"]),
    ("ar", "لمبة الإنترنت حمراء ولا يوجد اتصال", ["Error 500 - Router Connection Fault"]),
    ("ar", "الفحص أظهر خللاً برمجياً في الراوتر", ["Diagnostic Result: 'Software Glitch'"]),
    ("ar", "الفحص أظهر عطلاً في العتاد", ["Diagnostic Result: 'Hard Fault'", "Policy Rule #1 - Hard Fault Escalation"]),
    ("ar", "المشكلة لم تُحل بعد عدة محاولات", ["Policy Rule #2 - Maximum Retry Limit"]),
    ("ar", "هل يمكنني إرجاع منتج اشتريته الأسبوع الماضي؟", ["Return Window"]),
    ("ar", "هل يمكنني استرداد ثمن رخصة رقمية؟", ["Non-Refundable Items"]),
    ("ar", "لا أستطيع تسجيل الدخول إلى حسابي", ["Locked Account"]),
    ("ar", "الحساب مقفل بعد كلمات مرور خاطئة", ["Locked Account"]),
]


def entry_of(source: str) -> str:
    return source.split(" > ")[-1]


def main() -> None:
    from src.rag_engine import RAGEngine, resolve_provider

    provider = resolve_provider()
    rag = RAGEngine(provider=provider)
    stats = {lang: {"n": 0, "h1": 0, "h3": 0, "h3_filtered": 0, "wrong_topic_top1": 0} for lang in ("en", "ar")}
    lines = [f"# Retrieval check ({provider})", "", "| Lang | Query | Topic | Top 3 (no filter) | Hit@1 | Hit@3 | Hit@3 filtered |",
             "|---|---|---|---|---|---|---|"]

    for lang, query, expected in CASES:
        topic = classify_topic(query)
        plain = rag.retrieve_passages(query, k=3)
        filtered = rag.retrieve_passages(query, k=3, topic=topic if topic != "other" else None)
        names = [entry_of(p.source) for p in plain]
        h1 = bool(names) and names[0] in expected
        h3 = any(n in expected for n in names)
        h3f = any(entry_of(p.source) in expected for p in filtered)
        wrong = bool(plain) and topic != "other" and plain[0].topic not in ("general", topic)

        s = stats[lang]
        s["n"] += 1
        s["h1"] += h1
        s["h3"] += h3
        s["h3_filtered"] += h3f
        s["wrong_topic_top1"] += wrong
        shown = "; ".join(f"{n} ({p.distance:.2f})" for n, p in zip(names, plain))
        lines.append(f"| {lang} | {query} | {topic} | {shown} | {'yes' if h1 else 'NO'} | "
                     f"{'yes' if h3 else 'NO'} | {'yes' if h3f else 'NO'} |")

    lines += ["", "## Summary", "", "| Lang | Queries | Hit@1 | Hit@3 | Hit@3 with topic filter | Wrong-topic top-1 |",
              "|---|---|---|---|---|---|"]
    for lang, s in stats.items():
        n = s["n"]
        lines.append(f"| {lang} | {n} | {s['h1']}/{n} | {s['h3']}/{n} | {s['h3_filtered']}/{n} | {s['wrong_topic_top1']}/{n} |")

    report = "\n".join(lines)
    out = Path("reports") / f"retrieval_check_{re.sub(r'[^A-Za-z0-9._-]+', '-', provider)}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
