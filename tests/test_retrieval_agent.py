"""
Live-model checks (need Ollama/OpenAI, so excluded from CI) for the two critical
baseline failures documented in reports/analysis.md:
  1. Hallucinated return window (baseline said 30 days; real policy is 14)
  2. Missed Hard Fault escalation (baseline suggested manual steps)

Failure 2 is guaranteed in code by VeloAgent (Policy Rule #1), so it is tested at that
level. The deterministic version of that test is in test_agent_loop_unit.py and runs in CI.
"""
from src.agent_loop import TerminalState, VeloAgent
from src.model_client import get_model_client
from src.rag_engine import RAGEngine
from src.retrieval_agent import RetrievalAgent


def test_return_window_is_not_hallucinated():
    agent = RetrievalAgent(model=get_model_client(), rag=RAGEngine())
    decision = agent.decide("My product stopped working 10 days after purchase, can I return it?")

    print("\n--- Return window decision ---")
    print(decision.model_dump_json(indent=2))

    # The one thing a small local model can be checked on reliably: it must not invent the
    # baseline's "30 days". Whether its final decision is right still needs a human read of
    # the printed output above.
    assert "30" not in decision.reasoning + decision.response_to_user


def test_hard_fault_is_escalated_end_to_end():
    agent = VeloAgent(model=get_model_client(), rag=RAGEngine())
    result = agent.run("Diagnostics came back as a Hard Fault on my router.")

    print("\n--- Hard Fault result ---")
    print(result)

    assert result.terminal_state == TerminalState.ESCALATED
