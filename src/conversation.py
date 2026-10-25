"""
Conversation state: everything the agent has to remember between customer messages.

Without it every message was handled as if it were the first, so the knowledge base's
"not resolved within 3 interaction turns" rule (Policy Rule #2) could not be applied. The
state is a plain Pydantic model, so it can be saved and restored as JSON.

The conversation also remembers WHICH issue is being worked on (`topic`, `issue`,
`issue_start`). A follow-up such as "still not working" belongs to that issue, so the agent
never has to guess the topic again from a message that does not mention it.
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
    # The issue currently being worked on.
    topic: str | None = None      # router | account | billing (None until the customer names one)
    issue: str | None = None      # the customer message that started this issue
    issue_start: int = 0          # index in `messages` where this issue began

    @property
    def customer_turns(self) -> int:
        return sum(1 for m in self.messages if m.role == Role.CUSTOMER)

    @property
    def agent_replies(self) -> int:
        return sum(1 for m in self.messages if m.role == Role.AGENT)

    @property
    def escalated(self) -> bool:
        return self.ticket is not None

    def replies_in_issue(self) -> int:
        """Agent replies since the current issue began (Policy Rule #2 counts these)."""
        return sum(1 for m in self.messages[self.issue_start:] if m.role == Role.AGENT)

    def add(self, role: Role, content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def drop_last(self) -> None:
        self.messages.pop()

    def transcript(self) -> str:
        return self._format(self.messages)

    def issue_transcript(self, exclude_last: bool = False) -> str:
        """Only the messages of the current issue, so an earlier topic cannot leak into it."""
        end = len(self.messages) - 1 if exclude_last else len(self.messages)
        return self._format(self.messages[self.issue_start:end])

    @staticmethod
    def _format(messages: list[Message]) -> str:
        return "\n".join(f"{m.role.value.capitalize()}: {m.content}" for m in messages)
