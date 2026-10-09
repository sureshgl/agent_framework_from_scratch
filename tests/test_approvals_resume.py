"""Approvals and durable pause/resume — the governance story.

Side-effecting tools are floored to `ask` by policy, so they pause (no approver)
or consult an inline approver. A paused run is reloaded from disk in a *fresh*
Agent (standing in for a new process) and resumed to completion.
"""

from conftest import FakeProvider, text_response, tool_response

from minagent.agent import Agent
from minagent.events import EventLog, EventType
from minagent.tools import tool


def _types(result):
    return [e.type for e in EventLog.load(result.log_path).events()]


def _error_results(result):
    return [e for e in EventLog.load(result.log_path).events()
            if e.type == EventType.tool_result and e.data.get("is_error")]


def test_inline_approver_allows_side_effecting_tool(tmp_path):
    executed = []

    @tool(side_effecting=True)
    def post(x: int) -> str:
        executed.append(x)
        return "posted"

    provider = FakeProvider([tool_response("c1", "post", {"x": 5}), text_response("done")])
    agent = Agent("t", "x", tools=[post], provider=provider, store_dir=tmp_path)
    result = agent.run("go", approver=lambda req: True)

    assert result.status == "completed"
    assert executed == [5]
    assert EventType.approval_requested in _types(result)
    assert EventType.approval_decided in _types(result)


def test_inline_approver_denial_blocks_tool(tmp_path):
    executed = []

    @tool(side_effecting=True)
    def post(x: int) -> str:
        executed.append(x)
        return "posted"

    provider = FakeProvider([tool_response("c1", "post", {"x": 5}), text_response("ok, skipped")])
    agent = Agent("t", "x", tools=[post], provider=provider, store_dir=tmp_path)
    result = agent.run("go", approver=lambda req: False)

    assert result.status == "completed"
    assert executed == []
    errs = _error_results(result)
    assert errs and "denied by approver" in errs[0].data["error"]


def test_pause_without_approver_then_resume_to_completion(tmp_path):
    executed = []

    @tool(side_effecting=True)
    def post_report(content: str) -> str:
        executed.append(content)
        return "ok"

    # First process: runs until it needs approval, then pauses.
    agent1 = Agent("t", "x", tools=[post_report],
                   provider=FakeProvider([tool_response("call-1", "post_report", {"content": "hi"}),
                                          text_response("done")]),
                   store_dir=tmp_path)
    paused = agent1.run("write the report")

    assert paused.status == "paused"
    assert executed == []  # nothing side-effecting has happened
    assert paused.pending_approvals == [{"call_id": "call-1", "tool": "post_report",
                                         "args": {"content": "hi"}}]
    assert _types(paused)[-1] == EventType.run_paused

    # Second process: a brand-new Agent + provider, same store_dir. State comes
    # only from the reloaded log.
    agent2 = Agent("t", "x", tools=[post_report],
                   provider=FakeProvider([text_response("done")]),
                   store_dir=tmp_path)
    resumed = agent2.resume(paused.run_id, decisions={"call-1": True})

    assert resumed.status == "completed"
    assert resumed.output == "done"
    assert executed == ["hi"]  # the tool ran only after approval on resume
    types = _types(resumed)
    assert EventType.run_resumed in types
    assert EventType.tool_started in types  # C3 marker is present
    assert resumed.pending_approvals == []


def test_resume_with_denial_does_not_execute(tmp_path):
    executed = []

    @tool(side_effecting=True)
    def post_report(content: str) -> str:
        executed.append(content)
        return "ok"

    agent1 = Agent("t", "x", tools=[post_report],
                   provider=FakeProvider([tool_response("call-1", "post_report", {"content": "hi"}),
                                          text_response("skipped")]),
                   store_dir=tmp_path)
    paused = agent1.run("write it")
    assert paused.status == "paused"

    agent2 = Agent("t", "x", tools=[post_report],
                   provider=FakeProvider([text_response("skipped")]),
                   store_dir=tmp_path)
    resumed = agent2.resume(paused.run_id, decisions={"call-1": False})

    assert resumed.status == "completed"
    assert executed == []
    errs = _error_results(resumed)
    assert errs and "denied by approver" in errs[0].data["error"]
