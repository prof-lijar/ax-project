"""Deterministic metric for the test agent's expected function call."""


def evaluate(instance: dict) -> dict:
    """Scores whether the trace contains the expected tool call and response."""
    expected_tool = instance.get("expected_tool")
    expected_arguments = instance.get("expected_arguments") or {}
    saw_expected_call = False
    saw_successful_response = False

    for turn in (instance.get("agent_data") or {}).get("turns", []):
        for event in turn.get("events", []):
            for part in (event.get("content") or {}).get("parts", []):
                function_call = part.get("function_call") or part.get("functionCall")
                if function_call and function_call.get("name") == expected_tool:
                    actual_arguments = function_call.get("args") or {}
                    saw_expected_call = all(
                        str(actual_arguments.get(name, "")).lower()
                        == str(expected_value).lower()
                        for name, expected_value in expected_arguments.items()
                    )

                function_response = part.get("function_response") or part.get(
                    "functionResponse"
                )
                if function_response and function_response.get("name") == expected_tool:
                    response = function_response.get("response") or {}
                    saw_successful_response = response.get("status") == "success"

    passed = saw_expected_call and saw_successful_response
    return {
        "score": 1.0 if passed else 0.0,
        "explanation": (
            f"expected call={saw_expected_call}, "
            f"successful response={saw_successful_response}"
        ),
    }
