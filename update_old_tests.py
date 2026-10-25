"""
One-off: bring the 10 old tests in line with the behaviour decided in steps 1-3.

    uv run python update_old_tests.py

The old tests encoded behaviour that was changed on purpose:
  - a plain answer ends in AWAITING_CUSTOMER; only the customer's confirmation resolves a case;
  - a repeated diagnostic request is rejected and the model re-plans (it no longer ends the run);
  - a router issue is diagnosed before guidance, and a customer's claim is not a diagnostic;
  - a ticket names the customer's issue, not the last message.

Each change is exact and reported. Originals are saved next to the files as *.bak.
Running it twice is safe.
"""
import re
import shutil
import sys
from pathlib import Path

RESOLVED, AWAITING = "TerminalState.RESOLVED", "TerminalState.AWAITING_CUSTOMER"

REWRITES = {
    "test_second_diagnostic_request_is_blocked_by_policy_check": '''def test_second_diagnostic_request_is_blocked_by_policy_check(monkeypatch):
    """The documented failure/recovery case: the model ignores 'diagnose at most once'.
    The code rejects the request and the model re-plans to a usable answer."""
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK)
    agent, model = make_agent(
        [
            make_decision(ActionType.RUN_DIAGNOSTIC),
            make_decision(ActionType.RUN_DIAGNOSTIC),  # rejected by policy
            make_decision(ActionType.ANSWER),          # the model re-plans
        ]
    )
    result = agent.run("My router has no internet.")
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER  # recovered, not abandoned
    assert model.calls == 3


''',
    "test_customer_reported_software_glitch_does_not_rerun_the_diagnostic": '''def test_customer_reported_software_glitch_does_not_replace_the_real_diagnostic(monkeypatch):
    """A customer's claim is not tool output: the diagnostic still runs before any guidance."""
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK)
    agent, model = make_agent([make_decision(ActionType.ANSWER), make_decision(ActionType.ANSWER)])
    result = agent.run("The diagnostic says software glitch on my router.")
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert model.calls == 2  # the first ANSWER triggered the policy diagnostic, then the real answer


''',
    "test_earlier_messages_are_sent_to_the_model_on_the_next_turn": '''def test_earlier_messages_are_sent_to_the_model_on_the_next_turn(monkeypatch):
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK, [])
    agent, model = make_agent(
        [
            decision(ActionType.ASK_CLARIFYING_QUESTION, "Which light is red?"),
            decision(ActionType.ANSWER, "Restart it."),  # a router issue is diagnosed before guidance,
            decision(ActionType.ANSWER, "Restart it."),  # so the model is asked once more with the result
        ]
    )
    conversation = Conversation()

    first = agent.reply(conversation, "My router is broken.")
    second = agent.reply(conversation, "The internet light.")

    assert first.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert second.terminal_state == TerminalState.AWAITING_CUSTOMER
    assert "My router is broken." in model.prompts[1]
    assert "Which light is red?" in model.prompts[1]


''',
    "test_the_diagnostic_runs_at_most_once_per_conversation": '''def test_the_diagnostic_runs_at_most_once_per_conversation(monkeypatch):
    runs: list = []
    fix_diagnostic(monkeypatch, DiagnosticStatus.OK, runs)
    agent, _ = make_agent(
        [
            decision(ActionType.RUN_DIAGNOSTIC),
            decision(ActionType.ASK_CLARIFYING_QUESTION, "Is the cable plugged in?"),
            decision(ActionType.RUN_DIAGNOSTIC),  # the model asks again on the next message
            decision(ActionType.ANSWER, "Please restart the router."),  # it re-plans after the rejection
        ]
    )
    conversation = Conversation()
    agent.reply(conversation, "No internet.")
    result = agent.reply(conversation, "Yes it is plugged in.")
    assert len(runs) == 1
    assert result.terminal_state == TerminalState.AWAITING_CUSTOMER


''',
}

# (file, test name, [(old, new)], rename (old, new) or None)
EDITS = [
    ("tests/test_agent_loop_unit.py", "test_direct_answer_resolves_in_one_turn",
     [(RESOLVED, AWAITING)], ("resolves_in_one_turn", "awaits_confirmation_in_one_turn")),
    ("tests/test_agent_loop_unit.py", "test_diagnostic_then_answer_resolves_in_two_turns",
     [(RESOLVED, AWAITING)], ("resolves_in_two_turns", "awaits_confirmation_after_two_turns")),
    ("tests/test_conversation.py", "test_a_customer_still_writing_after_three_replies_is_escalated_in_code",
     [('assert ticket["customer_message"] == "still not fixed"',
       'assert ticket["customer_message"] == "one"  # the ticket names the issue, not the last message')], None),
    ("tests/test_conversation.py", "test_a_conversation_resolved_in_time_is_not_escalated",
     [(RESOLVED, AWAITING)], None),
    ("tests/test_conversation.py", "test_a_failed_model_call_leaves_the_conversation_as_it_was",
     [(RESOLVED, AWAITING)], None),
]
# (file, test name, [(regex, replacement, required)], marker present once updated)
CLI_TEST = "test_the_cli_keeps_one_conversation_and_survives_a_failed_reply"
REGEX_EDITS = [
    ("tests/test_conversation.py", CLI_TEST, [
        (rf"def ({CLI_TEST})\(capsys\):",
         r"def \1(capsys, monkeypatch):\n    fix_diagnostic(monkeypatch, DiagnosticStatus.OK, [])", True),
        (r'^([ \t]*)decision\(ActionType\.ANSWER, "Restart it\."\),[ \t]*$',
         r'\1decision(ActionType.ANSWER, "Restart it."),  # a router issue is diagnosed before guidance\n'
         r'\1decision(ActionType.ANSWER, "Restart it."),  # so the model is asked once more with the result', True),
        (r"model\.calls == 3", "model.calls == 4", False),
    ], "a router issue is diagnosed before guidance"),
]
REWRITE_FILES = {
    "test_second_diagnostic_request_is_blocked_by_policy_check": "tests/test_agent_loop_unit.py",
    "test_customer_reported_software_glitch_does_not_rerun_the_diagnostic": "tests/test_agent_loop_unit.py",
    "test_earlier_messages_are_sent_to_the_model_on_the_next_turn": "tests/test_conversation.py",
    "test_the_diagnostic_runs_at_most_once_per_conversation": "tests/test_conversation.py",
}
REWRITE_DONE = {  # a name that exists only after the rewrite
    "test_second_diagnostic_request_is_blocked_by_policy_check": "model.calls == 3",
    "test_customer_reported_software_glitch_does_not_rerun_the_diagnostic":
        "test_customer_reported_software_glitch_does_not_replace_the_real_diagnostic",
    "test_earlier_messages_are_sent_to_the_model_on_the_next_turn": "a router issue is diagnosed before guidance",
    "test_the_diagnostic_runs_at_most_once_per_conversation": "it re-plans after the rejection",
}


def block(text: str, name: str):
    start = re.search(rf"^def {re.escape(name)}\(", text, re.M)
    if not start:
        return None
    nxt = re.search(r"^(?=def |@|class )", text[start.end():], re.M)
    return start.start(), (start.end() + nxt.start() if nxt else len(text))


def main() -> int:
    files = {}
    for rel in {f for f, *_ in EDITS} | {f for f, *_ in REGEX_EDITS} | set(REWRITE_FILES.values()):
        path = Path(rel)
        if not path.exists():
            print(f"ERROR: {rel} not found. Run this from the project root.")
            return 1
        files[rel] = path.read_text(encoding="utf-8")

    log, failed = [], False
    for rel, name, replacements, rename in EDITS:
        text = files[rel]
        span = block(text, name)
        if span is None:
            renamed = rename and name.replace(*rename)
            state = "already updated" if renamed and block(text, renamed) else "NOT FOUND"
            failed |= state == "NOT FOUND"
            log.append(f"{state:16} {rel}::{name}")
            continue
        body = text[span[0]:span[1]]
        if all(new in body and old not in body for old, new in replacements):
            log.append(f"already updated  {rel}::{name}")
            continue
        for old, new in replacements:
            if old not in body:
                failed = True
                log.append(f"EXPECTED LINE MISSING  {rel}::{name}: {old[:60]}")
                break
            body = body.replace(old, new)
        else:
            if rename:
                body = body.replace(*rename, 1)
            files[rel] = text[:span[0]] + body + text[span[1]:]
            log.append(f"updated          {rel}::{name}")

    for rel, name, patterns, marker in REGEX_EDITS:
        text = files[rel]
        span = block(text, name)
        if span is None:
            failed = True
            log.append(f"NOT FOUND        {rel}::{name}")
            continue
        body = text[span[0]:span[1]]
        if marker in body:
            log.append(f"already updated  {rel}::{name}")
            continue
        for pattern, replacement, required in patterns:
            body, count = re.subn(pattern, replacement, body, flags=re.M)
            if required and count == 0:
                failed = True
                log.append(f"EXPECTED LINE MISSING  {rel}::{name}: {pattern[:50]}")
                break
        else:
            files[rel] = text[:span[0]] + body + text[span[1]:]
            log.append(f"updated          {rel}::{name}")

    for name, new_block in REWRITES.items():
        rel = REWRITE_FILES[name]
        text = files[rel]
        span = block(text, name)
        if span is None:
            done = REWRITE_DONE[name]
            state = "already updated" if done in text else "NOT FOUND"
            failed |= state == "NOT FOUND"
            log.append(f"{state:16} {rel}::{name}")
            continue
        if text[span[0]:span[1]].strip() == new_block.strip():
            log.append(f"already updated  {rel}::{name}")
            continue
        files[rel] = text[:span[0]] + new_block + text[span[1]:]
        log.append(f"rewritten        {rel}::{name}")

    print("\n".join(log))
    if failed:
        print("\nNothing was written because some tests were not found as expected. "
              "Send me the two test files and I will fix them directly.")
        return 1
    for rel, text in files.items():
        path = Path(rel)
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            shutil.copy(path, backup)
        path.write_text(text, encoding="utf-8")
    print("\nDone. Originals saved as *.bak. Now run: uv run pytest -m \"not requires_llm\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
