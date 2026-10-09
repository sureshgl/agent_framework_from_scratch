"""MCP tools behave exactly like local tools: namespaced, policy-gated, and with
failures surfaced as error results. The server is a real stdio subprocess (the
project's ERP server) — no network."""

import sys

import pytest

from conftest import FakeProvider, text_response, tool_response

from minagent.agent import Agent
from minagent.events import EventLog, EventType
from minagent.mcp_tools import MCPToolset

SERVER_CMD = [sys.executable, "-m", "examples.reconciliation.erp_server"]


@pytest.fixture(scope="module")
def erp():
    toolset = MCPToolset(SERVER_CMD, cwd=".", namespace="erp",
                         side_effecting={"post_invoice", "block_invoice"})
    toolset.start()
    yield toolset
    toolset.close()


def _tool_results(result):
    return [e for e in EventLog.load(result.log_path).events()
            if e.type == EventType.tool_result]


def test_lists_namespaced_tools(erp):
    names = sorted(t.name for t in erp.tools())
    assert "erp.read_po" in names
    assert "erp.post_invoice" in names
    assert len(names) == 7


def test_mcp_tool_result_flows_through_the_loop(erp, tmp_path):
    provider = FakeProvider([tool_response("c1", "erp.read_po", {"po_id": "PO-1001"}),
                             text_response("done")])
    agent = Agent("t", "x", tools=erp.tools(), provider=provider, store_dir=tmp_path)
    result = agent.run("read PO-1001")

    assert result.status == "completed"
    tr = _tool_results(result)[0]
    assert tr.data["is_error"] is False
    assert "PO-1001" in tr.data["result"]


def test_mcp_error_becomes_error_result(erp, tmp_path):
    provider = FakeProvider([tool_response("c1", "erp.read_po", {"po_id": "NOPE"}),
                             text_response("recovered")])
    agent = Agent("t", "x", tools=erp.tools(), provider=provider, store_dir=tmp_path)
    result = agent.run("read a bad PO")

    assert result.status == "completed"
    tr = _tool_results(result)[0]
    assert tr.data["is_error"] is True
    assert "unknown purchase order" in tr.data["error"]


def test_side_effecting_mcp_tool_pauses_for_approval(erp, tmp_path):
    provider = FakeProvider([tool_response("c1", "erp.post_invoice", {"invoice_id": "INV-9001"}),
                             text_response("done")])
    agent = Agent("t", "x", tools=erp.tools(), provider=provider, store_dir=tmp_path)
    result = agent.run("post the invoice")

    assert result.status == "paused"
    assert result.pending_approvals[0]["tool"] == "erp.post_invoice"
