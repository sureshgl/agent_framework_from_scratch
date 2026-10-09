"""The invoice / PO reconciliation agent.

Assembles the framework into an SAP-flavored agent: ERP data over a local MCP
server, a fixture-backed web search for vendor verification, a policy that gates
the two side-effecting actions (post / block) behind approval, and a declared
`ReconciliationReport` output schema. The matching rules live in the prompt; the
*enforcement* (approval, budgets, schema validation) lives in the runtime.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterable, Iterator

from minagent import Agent, MCPToolset, Policy, Provider, Tool, web_search_tool

from .models import ReconciliationReport

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_CMD = [sys.executable, "-m", "examples.reconciliation.erp_server"]
_SIDE_EFFECTING = {"post_invoice", "block_invoice"}

# Deterministic, offline vendor lookups (see spec C-websearch).
VENDOR_FIXTURES = {
    "Acme": "Acme Corp is a verified, registered supplier in good standing.",
    "Globex": "Globex Industries is a verified, registered supplier.",
    "Shady": "No business registration found for Shady Supplies LLC; it is not a verified supplier.",
}

INSTRUCTIONS = """\
You are an accounts-payable reconciliation agent. For the invoice you are given,
perform a three-way match across the purchase order, the goods receipts, and the
supplier invoice, then take the correct action and report.

Gather data with the ERP tools:
- erp.read_invoice(invoice_id), erp.read_po(po_id), erp.read_vendor(vendor_id)
- erp.read_goods_receipts(po_line) for each invoiced line
- erp.list_invoices() when you need to check for duplicates

For EACH invoice line, classify the issue:
- no_po: the invoice line's po_line does not exist on the purchase order
- price_variance: billed unit price differs from the PO unit price by more than
  2% (check per-unit, not just the line total — a small per-unit overcharge can
  hide inside a large quantity)
- qty_variance: quantity billed exceeds the quantity received (goods receipts)
- missing_gr: there is no goods receipt for the line's po_line
- ok: price within tolerance, quantity received covers quantity billed

Verify the vendor: call web_search for the vendor name and set vendor_verified
to whether it is a verified/approved supplier. Also check erp.read_vendor.

Detect duplicates: if another invoice has the same vendor, PO, line items and
total, set duplicate_of to that invoice id.

Decide the recommendation:
- post: every line ok, vendor verified, not a duplicate
- block: any price_variance, missing_gr, no_po, or a duplicate
- hold_for_review: qty_variance, or the vendor is not verified (and no harder
  violation applies)

Take the action, which requires approval:
- if recommendation is post, call erp.post_invoice(invoice_id)
- if recommendation is block, call erp.block_invoice(invoice_id, reason)
- if hold_for_review, take no action

Then produce the final ReconciliationReport with one verdict for this invoice.
three_way_match is "pass" only if every line is ok; otherwise "fail".
"""


def load_policy() -> Policy:
    return Policy.model_validate_json((Path(__file__).parent / "policy.json").read_text())


def reconcile_task(invoice_id: str) -> str:
    return (
        f"Reconcile supplier invoice {invoice_id}. Do the three-way match, take "
        f"the correct action, and produce the reconciliation report."
    )


def build_agent(
    tools: Iterable[Tool],
    *,
    store_dir: str = "runs",
    max_steps: int = 24,
    model: str | None = None,
    provider: Provider | None = None,
    on_event: Iterable[Callable] = (),
) -> Agent:
    return Agent(
        name="reconciliation",
        instructions=INSTRUCTIONS,
        tools=list(tools),
        policy=load_policy(),
        output_schema=ReconciliationReport,
        store_dir=store_dir,
        max_steps=max_steps,
        max_tokens=2048,
        model=model,
        provider=provider,
        on_event=list(on_event),
    )


@contextmanager
def erp_toolset() -> Iterator[MCPToolset]:
    """Open the ERP MCP server for the duration of a block."""
    toolset = MCPToolset(
        SERVER_CMD, cwd=str(REPO_ROOT), namespace="erp", side_effecting=_SIDE_EFFECTING
    )
    toolset.start()
    try:
        yield toolset
    finally:
        toolset.close()


def agent_tools(toolset: MCPToolset) -> list[Tool]:
    return [*toolset.tools(), web_search_tool(VENDOR_FIXTURES)]


@contextmanager
def reconciliation_agent(**kwargs) -> Iterator[Agent]:
    """Convenience: open the ERP server and yield a ready-to-run agent."""
    with erp_toolset() as toolset:
        yield build_agent(agent_tools(toolset), **kwargs)
