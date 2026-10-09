"""Primary example: an invoice / PO reconciliation agent (SAP-flavored).

The mock ERP data is served over a local MCP server (`erp_server.py`); the agent
performs a three-way match and produces a structured `ReconciliationReport`.
"""
