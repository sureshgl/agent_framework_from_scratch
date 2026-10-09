"""The mock ERP data model and the agent's structured output schema.

Entities mirror a minimal three-way-match world: vendors, purchase orders (with
lines), goods receipts against PO lines, and supplier invoices (with lines).
`ReconciliationReport` is what the agent must produce and validate against.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# -- ERP entities ------------------------------------------------------------

class Vendor(BaseModel):
    vendor_id: str
    name: str
    approved: bool          # on the approved-supplier list
    tax_id: str
    country: str


class POLine(BaseModel):
    po_line: str            # e.g. "PO-1001-10"
    material: str
    qty_ordered: int
    unit_price: float


class PurchaseOrder(BaseModel):
    po_id: str
    vendor_id: str
    currency: str
    lines: list[POLine]


class GoodsReceipt(BaseModel):
    gr_id: str
    po_line: str            # FK -> POLine.po_line
    qty_received: int
    received_date: str


class InvoiceLine(BaseModel):
    po_line: str            # FK; may not match any PO line -> no_po finding
    qty_billed: int
    unit_price: float


class Invoice(BaseModel):
    invoice_id: str
    vendor_id: str
    po_id: str
    currency: str
    lines: list[InvoiceLine]
    total: float
    received_date: str


# -- the agent's structured output -------------------------------------------

Issue = Literal["ok", "price_variance", "qty_variance", "missing_gr", "over_tolerance", "no_po"]


class LineFinding(BaseModel):
    po_line: str
    issue: Issue
    detail: str
    variance_usd: float = 0.0


class InvoiceVerdict(BaseModel):
    invoice_id: str
    vendor_id: str
    vendor_verified: bool
    three_way_match: Literal["pass", "fail"]
    findings: list[LineFinding]
    recommendation: Literal["post", "block", "hold_for_review"]
    duplicate_of: str | None = None


class ReconciliationReport(BaseModel):
    verdicts: list[InvoiceVerdict]
    summary: str
