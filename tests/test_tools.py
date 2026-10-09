import pytest
from pydantic import ValidationError

from minagent.tools import Tool, tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool(side_effecting=True)
def greet(name: str, excited: bool = False) -> str:
    return f"hi {name}{'!' if excited else ''}"


def test_tool_is_built_from_the_function():
    assert isinstance(add, Tool)
    assert add.name == "add"
    assert add.description == "Add two integers."
    assert greet.side_effecting is True


def test_schema_derived_from_type_hints():
    schema = add.schema
    assert schema["properties"]["a"]["type"] == "integer"
    assert schema["properties"]["b"]["type"] == "integer"
    assert set(schema["required"]) == {"a", "b"}
    # a defaulted argument is not required
    assert "excited" not in greet.schema.get("required", [])


def test_validate_coerces_and_rejects():
    assert add.validate({"a": 1, "b": 2}) == {"a": 1, "b": 2}
    with pytest.raises(ValidationError):
        add.validate({"a": "not-an-int", "b": 2})


def test_call_runs_the_function():
    assert add.call(a=2, b=3) == 5
    assert greet.call(name="sam", excited=True) == "hi sam!"
