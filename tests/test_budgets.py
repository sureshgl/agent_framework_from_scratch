from conftest import FakeProvider, text_response, tool_response

from minagent.agent import Agent
from minagent.budgets import Budgets, elapsed_seconds
from minagent.events import EventLog, EventType
from minagent.messages import ToolUseBlock, Usage
from minagent.provider import LLMResponse
from minagent.tools import tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def _final_event(result):
    return EventLog.load(result.log_path).events()[-1]


def _budget_which(result):
    ev = _final_event(result)
    assert ev.type == EventType.budget_exceeded, f"expected budget_exceeded, got {ev.type}"
    return ev.data["which"]


class _AlwaysTool:
    def __init__(self, cost: float = 0.0):
        self.n = 0
        self.cost = cost

    def complete(self, req):
        self.n += 1
        return LLMResponse(
            content=[ToolUseBlock(id=f"c{self.n}", name="add", input={"a": 1, "b": 1})],
            stop_reason="tool_use",
            usage=Usage(input_tokens=4, output_tokens=4, cost_usd=self.cost),
        )


def test_max_tokens_budget(tmp_path):
    agent = Agent("t", "x", tools=[add], provider=_AlwaysTool(),
                  budgets=Budgets(max_tokens=5), store_dir=tmp_path)
    result = agent.run("go")
    assert result.status == "budget_exceeded"
    assert _budget_which(result) == "max_tokens"


def test_max_tool_calls_budget(tmp_path):
    agent = Agent("t", "x", tools=[add], provider=_AlwaysTool(),
                  budgets=Budgets(max_tool_calls=2), store_dir=tmp_path)
    result = agent.run("go")
    assert result.status == "budget_exceeded"
    assert _budget_which(result) == "max_tool_calls"
    events = EventLog.load(result.log_path).events()
    assert sum(1 for e in events if e.type == EventType.tool_result) == 2


def test_max_cost_budget(tmp_path):
    agent = Agent("t", "x", tools=[add], provider=_AlwaysTool(cost=1.0),
                  budgets=Budgets(max_cost_usd=0.5), store_dir=tmp_path)
    result = agent.run("go")
    assert result.status == "budget_exceeded"
    assert _budget_which(result) == "max_cost_usd"


def test_max_wallclock_budget_fires_immediately_at_zero(tmp_path):
    # A zero wall-clock budget trips at the first budget check, before any model call.
    agent = Agent("t", "x", tools=[add], provider=FakeProvider([text_response("hi")]),
                  budgets=Budgets(max_wallclock_s=0.0), store_dir=tmp_path)
    result = agent.run("go")
    assert result.status == "budget_exceeded"
    assert _budget_which(result) == "max_wallclock_s"
    # no model call happened
    assert not any(e.type == EventType.llm_response
                   for e in EventLog.load(result.log_path).events())


def test_normal_run_is_unaffected_by_generous_budgets(tmp_path):
    provider = FakeProvider([tool_response("c1", "add", {"a": 2, "b": 3}), text_response("5")])
    agent = Agent("t", "x", tools=[add], provider=provider,
                  budgets=Budgets(max_steps=10, max_tokens=10_000), store_dir=tmp_path)
    result = agent.run("2+3?")
    assert result.status == "completed"
    assert result.output == "5"


def test_elapsed_seconds_empty_log_is_zero():
    assert elapsed_seconds([]) == 0.0
