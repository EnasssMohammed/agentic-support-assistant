"""
Conversation state: everything the agent has to remember between customer messages.

Without it every message was handled as if it were the first, so the knowledge base's
"not resolved within 3 interaction turns" rule (Policy Rule #2) could not be applied. The
state is a plain Pydantic model, so it can be saved and restored as JSON.
"""
from enum import Enum

from pydantic import BaseModel, Field

from src.diagnostics import DiagnosticResult
from src.escalation import EscalationTicket


class Role(str, Enum):
    CUSTOMER = "customer"
    AGENT = "agent"


class Message(BaseModel):
    role: Role
    content: str


class Conversation(BaseModel):
    messages: list[Message] = Field(default_factory=list)
    # The diagnostic outcome (measured by the tool, or reported by the customer). Having one
    # means the tool is not run again for the rest of the conversation.
    diagnostic: DiagnosticResult | None = None
    # Set once the conversation has been escalated; later messages never create a second ticket.
    ticket: EscalationTicket | None = None

    @property
    def customer_turns(self) -> int:
        return sum(1 for m in self.messages if m.role == Role.CUSTOMER)

    @property
    def agent_replies(self) -> int:
        return sum(1 for m in self.messages if m.role == Role.AGENT)

    @property
    def escalated(self) -> bool:
        return self.ticket is not None

    def add(self, role: Role, content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def drop_last(self) -> None:
        self.messages.pop()

    def transcript(self) -> str:
        return "\n".join(f"{m.role.value.capitalize()}: {m.content}" for m in self.messages)
