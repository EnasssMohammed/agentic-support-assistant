"""
End-to-end test of the bounded agent loop: decide -> run diagnostic ->
decide again -> terminal state. The diagnostic result is random, so this
test checks the INVARIANTS that must hold regardless of which outcome
happened, not one fixed expected answer.
"""
from src.agent_loop import MAX_TURNS, TerminalState, VeloAgent
from src.model_client import get_model_client
from src.rag_engine import RAGEngine


def test_router_complaint_runs_diagnostic_then_terminates():
    agent = VeloAgent(model=get_model_client(), rag=RAGEngine())
    result = agent.run("My router's internet light is red and nothing works.")

    print("\n--- Agent run result ---")
    print(f"Terminal state: {result.terminal_state}")
    print(f"Turns used: {result.turns_used}")
    if result.final_decision is not None:
        print(result.final_decision.model_dump_json(indent=2))

    # Any normal ending is fine. FAILED_SAFELY is not: against a live model it means the
    # provider could not be reached or returned unusable output, and that should be visible.
    assert result.terminal_state in (
        TerminalState.RESOLVED,
        TerminalState.AWAITING_CUSTOMER,
        TerminalState.ESCALATED,
        TerminalState.BUDGET_EXHAUSTED,
    ), result.error_message
    # It must never exceed the turn budget.
    assert result.turns_used <= MAX_TURNS
