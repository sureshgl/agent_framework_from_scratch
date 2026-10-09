"""A local MCP server exposing the mock ERP as tools.

Run standalone over stdio:  python -m examples.reconciliation.erp_server
It is mounted into the agent via `minagent.MCPToolset`. Read tools look data up
in `data/erp.json`; `post_invoice` / `block_invoice` are the side-effecting
actions the agent must get approval for. `post_invoice` is idempotent by
invoice id (so an at-least-once retry after a crash is safe — spec C3).
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

_DATA = json.loads((Path(__file__).parent / "data" / "erp.json").read_text(encoding="utf-8"))
_VENDORS = {v["vendor_id"]: v for v in _DATA["vendors"]}
_POS = {p["po_id"]: p for p in _DATA["purchase_orders"]}
_INVOICES = {i["invoice_id"]: i for i in _DATA["invoices"]}
_GRS = _DATA["goods_receipts"]

_posted: dict[str, dict] = {}   # in-memory effect log, reset per process
_blocked: dict[str, dict] = {}

mcp = MCPServer("erp")


@mcp.tool()
def read_vendor(vendor_id: str) -> dict:
    """Return the vendor master record (incl. whether it is an approved supplier)."""
    if vendor_id not in _VENDORS:
        raise ToolError(f"unknown vendor: {vendor_id}")
    return _VENDORS[vendor_id]


@mcp.tool()
def read_po(po_id: str) -> dict:
    """Return a purchase order and its line items."""
    if po_id not in _POS:
        raise ToolError(f"unknown purchase order: {po_id}")
    return _POS[po_id]


@mcp.tool()
def read_goods_receipts(po_line: str) -> list[dict]:
    """Return all goods receipts recorded against a PO line (may be empty)."""
    return [g for g in _GRS if g["po_line"] == po_line]


@mcp.tool()
def read_invoice(invoice_id: str) -> dict:
    """Return a supplier invoice and its line items."""
    if invoice_id not in _INVOICES:
        raise ToolError(f"unknown invoice: {invoice_id}")
    return _INVOICES[invoice_id]


@mcp.tool()
def list_invoices() -> list[str]:
    """List all supplier invoice ids awaiting reconciliation."""
    return list(_INVOICES)


@mcp.tool()
def post_invoice(invoice_id: str) -> dict:
    """Post an invoice for payment (side-effecting; idempotent by invoice id)."""
    if invoice_id not in _INVOICES:
        raise ToolError(f"unknown invoice: {invoice_id}")
    _posted.setdefault(invoice_id, {"invoice_id": invoice_id, "status": "posted"})
    return _posted[invoice_id]


@mcp.tool()
def block_invoice(invoice_id: str, reason: str) -> dict:
    """Block an invoice from payment (side-effecting)."""
    if invoice_id not in _INVOICES:
        raise ToolError(f"unknown invoice: {invoice_id}")
    _blocked[invoice_id] = {"invoice_id": invoice_id, "status": "blocked", "reason": reason}
    return _blocked[invoice_id]


if __name__ == "__main__":
    mcp.run("stdio")
