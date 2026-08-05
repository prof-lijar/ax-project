import pytest
from ax_agents import graph


def test_graph_returns_deterministic_response() -> None:
    assert graph.invoke({"message": "hello"}) == {
        "message": "hello",
        "response": "ack: hello",
    }


@pytest.mark.parametrize("value", ["", "   ", None, 42])
def test_graph_rejects_invalid_message(value: object) -> None:
    with pytest.raises(ValueError, match="message must be a non-empty string"):
        graph.invoke({"message": value})  # type: ignore[arg-type]
