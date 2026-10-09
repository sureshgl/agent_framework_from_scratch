"""The log is the only source of truth (NFR-5), and subscribers observe it live."""

from conftest import FakeProvider, text_response, tool_response

from minagent.agent import Agent, _result_from_log
from minagent.events import EventLog, EventType
from minagent.state import project
from minagent.tools import tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def test_result_is_reproducible_from_the_log_alone(tmp_path):
    provider = FakeProvider([tool_response("c1", "add", {"a": 2, "b": 3}), text_response("it is 5")])
    agent = Agent("t", "x", tools=[add], provider=provider, store_dir=tmp_path)
    result = agent.run("2+3?")

    # Reload the committed log in a fresh object — nothing from the live run — and
    # re-derive. If the loop kept hidden state, these would diverge.
    reloaded = EventLog.load(result.log_path)
    state = project(reloaded.events())
    assert state.status == "completed"
    assert state.output == result.output == "it is 5"

    rebuilt = _result_from_log(reloaded)
    assert rebuilt.status == result.status
    assert rebuilt.output == result.output


def test_subscriber_sees_every_event_in_order(tmp_path):
    seen = []
    provider = FakeProvider([tool_response("c1", "add", {"a": 1, "b": 1}), text_response("2")])
    agent = Agent("t", "x", tools=[add], provider=provider,
                  store_dir=tmp_path, on_event=[lambda e: seen.append(e.type)])
    result = agent.run("1+1?")

    assert seen[0] == EventType.run_started
    assert seen[-1] == EventType.run_completed
    assert EventType.tool_started in seen and EventType.tool_result in seen
    # the live subscriber stream matches the persisted log exactly
    persisted = [e.type for e in EventLog.load(result.log_path).events()]
    assert seen == persisted
