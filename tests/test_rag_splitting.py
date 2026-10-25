from pathlib import Path

from src.rag_engine import split_policy_entries

KB = Path("data/technical_docs.txt")


def test_each_policy_entry_is_one_chunk():
    entries = split_policy_entries(KB.read_text(encoding="utf-8"))
    titles = [e["entry"] for e in entries]
    assert len(entries) == 8
    assert "Policy Rule #1 - Hard Fault Escalation" in titles


def test_rules_are_never_cut_in_half():
    entries = {e["entry"]: e["text"] for e in split_policy_entries(KB.read_text(encoding="utf-8"))}
    rule = entries["Policy Rule #1 - Hard Fault Escalation"]
    assert "MUST NOT" in rule and "immediately" in rule


def test_chunks_carry_their_section_title():
    entries = split_policy_entries(KB.read_text(encoding="utf-8"))
    refund = next(e for e in entries if e["entry"] == "Return Window")
    assert refund["text"].startswith("3. REFUND & RETURN POLICIES")


def test_unstructured_text_returns_nothing_so_the_fallback_runs():
    assert split_policy_entries("just some plain text\nwith no entries") == []


def test_entries_are_tagged_so_an_account_issue_never_sees_router_rules():
    from src.intents import policy_topic, topic_compatible

    entries = split_policy_entries(KB.read_text(encoding="utf-8"))
    tags = {e["entry"]: policy_topic(f"{e['entry']} {e['text']}") for e in entries}
    assert tags["Locked Account"] == "account"
    assert tags["Policy Rule #1 - Hard Fault Escalation"] == "router"
    assert tags["Policy Rule #2 - Maximum Retry Limit"] == "general"
    visible = {name for name, tag in tags.items() if topic_compatible(tag, "account")}
    assert visible == {"Locked Account", "Policy Rule #2 - Maximum Retry Limit"}
