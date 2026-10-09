"""Keyless checks for the reconciliation example: the scorer logic, and that the
agent assembles and runs end to end over the real ERP MCP server (with a scripted
fake model standing in for the LLM)."""

import sys

from conftest import FakeProvider, text_response, tool_response

from examples.reconciliation.agent import agent_tools, build_agent, erp_toolset
from examples.reconciliation.models import InvoiceVerdict, LineFinding
from evals.cases import ANSWER_KEY, score_verdict, all_passed

REPORT_JSON = """{
  "verdicts": [{
    "invoice_id": "INV-9001", "vendor_id": "V100", "vendor_verified": true,
    "three_way_match": "pass",
    "findings": [{"po_line": "PO-1001-10", "issue": "ok", "detail": "matches", "variance_usd": 0.0}],
    "recommendation": "post", "duplicate_of": null
  }],
  "summary": "Invoice INV-9001 matches the PO and goods receipt."
}"""


def test_scorer_passes_a_correct_verdict():
    verdict = InvoiceVerdict(
        invoice_id="INV-9002", vendor_id="V200", vendor_verified=True,
        three_way_match="fail", recommendation="block",
        findings=[LineFinding(po_line="PO-1002-20", issue="price_variance",
                              detail="0.105 vs 0.10", variance_usd=5.0)],
    )
    assert all_passed(score_verdict(verdict, ANSWER_KEY["INV-9002"]))


def test_scorer_flags_a_wrong_recommendation():
    verdict = InvoiceVerdict(
        invoice_id="INV-9002", vendor_id="V200", vendor_verified=True,
        three_way_match="fail", recommendation="post",  # should be block
        findings=[LineFinding(po_line="PO-1002-20", issue="price_variance", detail="x")],
    )
    checks = score_verdict(verdict, ANSWER_KEY["INV-9002"])
    assert not all_passed(checks)


def test_agent_assembles_and_runs_over_mcp(tmp_path):
    # The model is faked (keyless); the ERP tools are the real MCP server.
    provider = FakeProvider([
        tool_response("c1", "erp__read_invoice", {"invoice_id": "INV-9001"}),
        text_response(REPORT_JSON),
    ])
    with erp_toolset() as toolset:
        agent = build_agent(agent_tools(toolset), provider=provider, store_dir=str(tmp_path))
        result = agent.run("Reconcile INV-9001", approver=lambda req: True)

    assert result.status == "completed"
    assert result.output.verdicts[0].recommendation == "post"
    assert all_passed(score_verdict(result.output.verdicts[0], ANSWER_KEY["INV-9001"]))
