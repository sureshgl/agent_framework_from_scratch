from conftest import FakeProvider, text_response, tool_response

from minagent.agent import Agent
from minagent.events import EventLog, EventType
from minagent.hooks import HookContext, HookPoint
from minagent.policy import Decision
from minagent.tools import tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def _events(result):
    return EventLog.load(result.log_path).events()


def test_before_tool_deny_hook_blocks_execution(tmp_path):
    def deny_add(ctx: HookContext):
        if ctx.point == HookPoint.before_tool and ctx.tool_name == "add":
            return Decision(action="deny", reason="no adding")
        return None

    provider = FakeProvider([tool_response("c1", "add", {"a": 1, "b": 2}), text_response("ok")])
    agent = Agent("t", "x", tools=[add], provider=provider, hooks=[deny_add], store_dir=tmp_path)
    result = agent.run("go")

    assert result.status == "completed"
    events = _events(result)
    # denied before execution: an error result, but no tool_started
    assert not any(e.type == EventType.tool_started for e in events)
    tr = [e for e in events if e.type == EventType.tool_result][0]
    assert tr.data["is_error"] is True
    assert "denied by policy" in tr.data["error"]


def test_before_tool_hook_combines_with_policy_most_restrictive(tmp_path):
    # policy would allow, hook asks -> effective ask -> pauses (no approver)
    def ask_hook(ctx: HookContext):
        if ctx.point == HookPoint.before_tool:
            return Decision(action="ask", reason="double-check")
        return None

    provider = FakeProvider([tool_response("c1", "add", {"a": 1, "b": 2}), text_response("ok")])
    agent = Agent("t", "x", tools=[add], provider=provider, hooks=[ask_hook], store_dir=tmp_path)
    result = agent.run("go")

    assert result.status == "paused"
    assert result.pending_approvals and result.pending_approvals[0]["tool"] == "add"


def test_before_model_deny_hook_fails_the_run(tmp_path):
    def block_model(ctx: HookContext):
        if ctx.point == HookPoint.before_model:
            return Decision(action="deny", reason="budget freeze")
        return None

    agent = Agent("t", "x", tools=[add], provider=FakeProvider([text_response("hi")]),
                  hooks=[block_model], store_dir=tmp_path)
    result = agent.run("go")

    assert result.status == "failed"
    failed = [e for e in _events(result) if e.type == EventType.run_failed][0]
    assert failed.data["where"] == "before_model"


def test_all_four_hook_points_fire(tmp_path):
    seen = []

    def recorder(ctx: HookContext):
        seen.append(ctx.point)
        return None

    provider = FakeProvider([tool_response("c1", "add", {"a": 1, "b": 1}), text_response("2")])
    agent = Agent("t", "x", tools=[add], provider=provider, hooks=[recorder], store_dir=tmp_path)
    agent.run("1+1?")

    assert HookPoint.before_model in seen
    assert HookPoint.after_model in seen
    assert HookPoint.before_tool in seen
    assert HookPoint.after_tool in seen
