"""Replay is keyless and networkless: a recorded run re-drives from its log.

Covers both tool modes and the divergence guard, plus E10 — replaying the
committed reconciliation recording with no key and no MCP server."""

from pathlib import Path

from conftest import FakeProvider, text_response, tool_response

from minagent.agent import Agent
from minagent.events import EventLog, EventType
from minagent.tools import tool

from examples.reconciliation.models import ReconciliationReport

RECORDED = Path(__file__).resolve().parents[1] / "evals" / "recorded" / "reconcile_INV-9002.jsonl"


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def _record(tmp_path):
    provider = FakeProvider([tool_response("c1", "add", {"a": 2, "b": 3}), text_response("sum is 5")])
    agent = Agent("t", "x", tools=[add], provider=provider, store_dir=tmp_path)
    return agent, agent.run("2+3?")


def test_replay_reexecute_reproduces_output(tmp_path):
    agent, original = _record(tmp_path)
    replayed = agent.replay(original.log_path)  # default: re-execute tools

    assert replayed.status == "completed"
    assert replayed.output == "sum is 5"
    assert replayed.run_id != original.run_id
    events = EventLog.load(replayed.log_path).events()
    assert sum(1 for e in events if e.type == EventType.llm_response) == 2
    assert events[0].data["replay_of"] == original.run_id


def test_replay_recorded_tools_is_hermetic(tmp_path):
    agent, original = _record(tmp_path)
    # A bare agent with NO tools can still replay in recorded mode.
    bare = Agent("t", "x", tools=[], store_dir=tmp_path)
    replayed = bare.replay(original.log_path, replay_tools="recorded")

    assert replayed.status == "completed"
    assert replayed.output == "sum is 5"
    tr = [e for e in EventLog.load(replayed.log_path).events() if e.type == EventType.tool_result][0]
    assert tr.data["result"] == 5


def test_replay_divergence_is_named(tmp_path):
    agent, original = _record(tmp_path)
    # Truncate the recording after the first tool result, so the replayed loop
    # asks for a model response that was never recorded.
    events = EventLog.load(original.log_path).events()
    cut = []
    for e in events:
        cut.append(e)
        if e.type == EventType.tool_result:
            break
    truncated = tmp_path / "truncated.jsonl"
    truncated.write_text("\n".join(e.model_dump_json() for e in cut) + "\n")

    bare = Agent("t", "x", tools=[], store_dir=tmp_path)
    replayed = bare.replay(str(truncated), replay_tools="recorded")

    assert replayed.status == "failed"
    assert EventLog.load(replayed.log_path).events()[-1].data["where"] == "replay-divergence"


def test_e10_replays_committed_run_keyless(tmp_path):
    # No API key, no MCP server — just the committed JSONL.
    assert RECORDED.exists(), "run `python -m evals.record_fixture` to create it"
    # No tools and no MCP server, but the schema is declared so the final answer
    # is re-parsed into a typed report.
    bare = Agent("reconciliation", "x", tools=[], output_schema=ReconciliationReport,
                 store_dir=tmp_path)
    replayed = bare.replay(str(RECORDED), replay_tools="recorded")

    assert replayed.status == "completed"
    verdict = replayed.output.verdicts[0]
    assert verdict.invoice_id == "INV-9002"
    assert verdict.recommendation == "block"
    assert "price_variance" in {f.issue for f in verdict.findings}
