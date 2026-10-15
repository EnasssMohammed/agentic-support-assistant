"""
Velo — interactive multi-turn CLI.

One Conversation is kept for the whole session, so the agent sees the earlier messages and
applies the "not resolved within 3 turns" rule. Type /new for a fresh conversation and
/quit to exit. For the full evaluation run, use `run_eval.py`.
"""
from collections.abc import Callable

from src.agent_loop import InvalidInputError, VeloAgent
from src.conversation import Conversation
from src.model_client import get_model_client
from src.rag_engine import RAGEngine


def main(agent: VeloAgent | None = None, input_fn: Callable[[str], str] = input) -> None:
    if agent is None:
        agent = VeloAgent(model=get_model_client(), rag=RAGEngine())
    print("Velo support agent (/new = new conversation, /quit = exit)\n")
    conversation = Conversation()

    while True:
        text = input_fn("You: ").strip()
        if text.lower() in ("/quit", "quit", "exit"):
            break
        if text.lower() == "/new":
            conversation = Conversation()
            print("(new conversation)\n")
            continue
        if not text:
            continue

        try:
            result = agent.reply(conversation, text)
        except InvalidInputError as e:
            print(f"({e})\n")
            continue

        print(f"\n[{result.terminal_state.value}, {result.turns_used} model turn(s)]")
        if result.final_decision is None:
            print(f"Velo could not answer right now ({result.error_message}). Please send it again.")
        else:
            print(f"Velo: {result.final_decision.response_to_user}")
        if result.ticket:
            print(f"(Escalation ticket: {result.ticket.ticket_id})")
        print()


if __name__ == "__main__":
    main()
