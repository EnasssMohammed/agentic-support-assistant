"""
Velo — interactive CLI entry point.

For the full evaluation run instead, use `run_eval.py`.
"""
from src.agent_loop import VeloAgent
from src.model_client import get_model_client
from src.rag_engine import RAGEngine


def main():
    print("Velo support agent (type 'quit' to exit)\n")
    agent = VeloAgent(model=get_model_client(), rag=RAGEngine(provider="ollama"))

    while True:
        user_message = input("You: ").strip()
        if user_message.lower() in ("quit", "exit"):
            break
        if not user_message:
            continue

        result = agent.run(user_message)
        print(f"\n[{result.terminal_state.value}, {result.turns_used} turn(s)]")
        print(f"Velo: {result.final_decision.response_to_user}")
        if result.ticket:
            print(f"(Escalation ticket created: {result.ticket.ticket_id})")
        print()


if __name__ == "__main__":
    main()
