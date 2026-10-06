"""
Stage 3: Knowledge retrieval.

Combines the RAG engine (retrieval) with the model boundary's structured
output (decision). The model no longer answers from its own "memory" of
policy — it is given the retrieved passage and told to ground its decision
in it. This is what fixes the hallucination and missed-escalation failures
documented in reports/analysis.md.
"""
from src.model_client import ModelClient
from src.rag_engine import RAGEngine
from src.schemas import AgentDecision

SYSTEM_PROMPT = """You are a customer support decision engine for Velo.
You will be given the customer's message and a RETRIEVED POLICY PASSAGE
from the official technical support manual.

Rules:
- Base your decision ONLY on the retrieved passage below. Do not invent
  policy details (numbers, deadlines, rules) that are not in the passage.
- If the passage says an action MUST be escalated, you MUST set
  requires_escalation=true and action=escalate. Do not suggest manual
  troubleshooting steps in that case.
- If the customer describes a device/hardware problem (e.g. router issues)
  and no [DIAGNOSTIC RESULT] is present yet in the message, you MUST choose
  action=run_diagnostic instead of guessing what's wrong. Do not answer
  or escalate a hardware complaint until a diagnostic result is available.
- If a [DIAGNOSTIC RESULT] IS present in the message, use it directly to
  decide (do not request another diagnostic).
- Cite the specific rule you used in `reasoning`.
"""


class RetrievalAgent:
    def __init__(self, model: ModelClient, rag: RAGEngine):
        self.model = model
        self.rag = rag

    def decide(self, user_message: str) -> AgentDecision:
        retrieved_context = self.rag.retrieve(user_message)

        user_prompt = f"""RETRIEVED POLICY PASSAGE:
{retrieved_context}

CUSTOMER MESSAGE:
{user_message}"""

        return self.model.generate_structured(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            schema=AgentDecision,
        )
