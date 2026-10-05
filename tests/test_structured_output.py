"""
Verifies the model can return a structured AgentDecision instead of free text.
Uses only ONE case (not the full eval set) to keep this fast during development.
"""
from src.model_client import get_model_client
from src.schemas import AgentDecision

SYSTEM_PROMPT = """You are a customer support decision engine.
Given the customer's message, decide the single best next action.
Respond only in the structured format you are given."""


def test_structured_decision_for_hard_fault_case():
    client = get_model_client()
    decision = client.generate_structured(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Diagnostics came back as a Hard Fault on my router."},
        ],
        schema=AgentDecision,
    )

    assert isinstance(decision, AgentDecision)
    print("\n--- Structured decision ---")
    print(decision.model_dump_json(indent=2))
