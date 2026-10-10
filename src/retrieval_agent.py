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
- Choose action=run_diagnostic ONLY if the customer is describing a
  ROUTER/CONNECTIVITY/HARDWARE problem (e.g. no internet, red light,
  device errors) AND no [DIAGNOSTIC RESULT] is present yet in the message.
  Never choose run_diagnostic for account/password, billing/refund, or
  any non-device issue - those are decided from the retrieved passage
  alone.
- If a [DIAGNOSTIC RESULT] IS already present anywhere in this
  conversation, you MUST NOT choose run_diagnostic again. Decide using
  the result you already have. A diagnostic outcome the customer states in
  their own message (for example "Hard Fault") counts as a diagnostic result.
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
