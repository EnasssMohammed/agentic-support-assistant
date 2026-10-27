"""
Test configuration.

Tests that need a live Ollama/OpenAI model are slow and can't run on a
CI runner, so they are auto-marked `requires_llm` here. CI runs
`pytest -m "not requires_llm"`; run everything locally with plain `pytest`.
"""
import pytest

LLM_TEST_FILES = {
    "test_baseline.py",
    "test_structured_output.py",
    "test_retrieval_agent.py",
    "test_agent_loop.py",
}


CONFIG_VARIABLES = ("MODEL_PROVIDER", "MODEL_NAME", "OPENAI_API_KEY")


@pytest.fixture(autouse=True)
def isolate_configuration(request, monkeypatch):
    """Unit tests must not depend on the developer's .env or shell. Live-model tests do need them."""
    if request.node.get_closest_marker("requires_llm"):
        return
    for name in CONFIG_VARIABLES:
        monkeypatch.delenv(name, raising=False)


MAX_TEST_ID_LENGTH = 20_000


def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name in LLM_TEST_FILES:
            item.add_marker(pytest.mark.requires_llm)

    # pytest copies a test's name into an environment variable, and Windows rejects values over 32,767 characters.
    # A large parameter value without an explicit id silently becomes part of that name, so refuse it at collection
    # time on every platform instead of letting it fail only on Windows.
    too_long = [item.nodeid[:90] + "..." for item in items if len(item.nodeid) > MAX_TEST_ID_LENGTH]
    if too_long:
        raise pytest.UsageError(
            f"Test ids longer than {MAX_TEST_ID_LENGTH} characters (give the parameter an explicit id=...):\n"
            + "\n".join(too_long)
        )
