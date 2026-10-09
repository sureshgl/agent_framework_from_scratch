from conftest import FakeProvider, text_response, tool_response

from minagent.agent import Agent
from minagent.events import EventType
from minagent.provider import LLMResponse
from minagent.messages import ToolUseBlock, Usage
from minagent.state import project
from minagent.tools import tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool
def boom() -> str:
    """Always raises."""
    raise RuntimeError("kaboom")


def _types(log_events):
    return [e.type for e in log_events]


def test_tool_call_then_completion(tmp_path):
    provider = FakeProvider([
        tool_response("c1", "add", {"a": 2, "b": 3}),
        text_response("the answer is 5"),
    ])
    agent = Agent("t", "add numbers", tools=[add], provider=provider, store_dir=tmp_path)
    result = agent.run("what is 2+3?")

    assert result.status == "completed"
    assert result.output == "the answer is 5"
    events = agent_events(result)
    assert EventType.tool_started in _types(events)
    tr = [e for e in events if e.type == EventType.tool_result][0]
    assert tr.data["result"] == 5 and tr.data["is_error"] is False


def test_unknown_tool_becomes_error_result(tmp_path):
    provider = FakeProvider([
        tool_response("c1", "does_not_exist", {}),
        text_response("ok, recovered"),
    ])
    agent = Agent("t", "x", tools=[add], provider=provider, store_dir=tmp_path)
    result = agent.run("go")

    assert result.status == "completed"
    tr = [e for e in agent_events(result) if e.type == EventType.tool_result][0]
    assert tr.data["is_error"] is True
    assert "unknown tool" in tr.data["error"]


def test_tool_exception_becomes_error_result(tmp_path):
    provider = FakeProvider([
        tool_response("c1", "boom", {}),
        text_response("handled it"),
    ])
    agent = Agent("t", "x", tools=[boom], provider=provider, store_dir=tmp_path)
    result = agent.run("go")

    assert result.status == "completed"
    tr = [e for e in agent_events(result) if e.type == EventType.tool_result][0]
    assert tr.data["is_error"] is True
    assert "kaboom" in tr.data["error"]


def test_invalid_arguments_become_error_result(tmp_path):
    provider = FakeProvider([
        tool_response("c1", "add", {"a": "nan", "b": 2}),
        text_response("recovered"),
    ])
    agent = Agent("t", "x", tools=[add], provider=provider, store_dir=tmp_path)
    result = agent.run("go")

    assert result.status == "completed"
    tr = [e for e in agent_events(result) if e.type == EventType.tool_result][0]
    assert tr.data["is_error"] is True
    assert "invalid arguments" in tr.data["error"]


class _AlwaysToolProvider:
    """Requests a tool on every turn, with a fresh id each time."""

    def __init__(self):
        self.n = 0

    def complete(self, req):
        self.n += 1
        return LLMResponse(
            content=[ToolUseBlock(id=f"c{self.n}", name="add", input={"a": 1, "b": 1})],
            stop_reason="tool_use",
            usage=Usage(input_tokens=1, output_tokens=1),
        )


def test_max_steps_budget_stops_the_run(tmp_path):
    agent = Agent("t", "x", tools=[add], provider=_AlwaysToolProvider(),
                  max_steps=2, store_dir=tmp_path)
    result = agent.run("loop forever")

    assert result.status == "budget_exceeded"
    events = agent_events(result)
    be = [e for e in events if e.type == EventType.budget_exceeded][0]
    assert be.data["which"] == "max_steps"
    # exactly max_steps model calls happened
    assert sum(1 for e in events if e.type == EventType.llm_response) == 2


# --- helper to reload the committed log for a finished run -------------------

def agent_events(result):
    from minagent.events import EventLog

    return EventLog.load(result.log_path).events()
