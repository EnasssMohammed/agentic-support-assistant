"""
Non-agentic baseline: one LLM call, no retrieval, no tools, no memory.

This exists ONLY to be compared against. It is expected to fail on cases
that require grounded knowledge or policy-driven escalation. That failure
is the evidence that justifies building the agent (see docs/00-problem.md).
"""
from src.model_client import ModelClient

SYSTEM_PROMPT = "You are a customer support assistant. Answer the user's question."


class BaselineAgent:
    def __init__(self, model: ModelClient):
        self.model = model

    def answer(self, user_message: str) -> str:
        return self.model.generate([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])
