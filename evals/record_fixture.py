"""Regenerate the committed replay fixture.

    python -m evals.record_fixture

Produces a reconciliation of INV-9002 (a hidden per-unit overcharge -> block,
with the approval gate firing), recorded keyless — a scripted stand-in model over
the *real* ERP MCP server — so it can be regenerated anywhere.

Note: the committed `evals/recorded/reconcile_INV-9002.jsonl` is a GENUINE live
capture from `make demo`. This script is a keyless fallback regenerator; it
overwrites that file with a synthetic (but structurally identical) recording, so
only run it when you cannot capture a live run.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from minagent.messages import TextBlock, ToolUseBlock, Usage
from minagent.provider import LLMResponse

from examples.reconciliation.agent import agent_tools, build_agent, erp_toolset, reconcile_task

RECORDED = Path(__file__).parent / "recorded"
TARGET = RECORDED / "reconcile_INV-9002.jsonl"

REPORT = (
    '{"verdicts": [{"invoice_id": "INV-9002", "vendor_id": "V200", '
    '"vendor_verified": true, "three_way_match": "fail", "findings": ['
    '{"po_line": "PO-1002-10", "issue": "ok", "detail": "50 @ 10.00 matches", "variance_usd": 0.0}, '
    '{"po_line": "PO-1002-20", "issue": "price_variance", '
    '"detail": "billed 0.105 vs PO 0.10 (5%)", "variance_usd": 5.0}], '
    '"recommendation": "block", "duplicate_of": null}], '
    '"summary": "INV-9002 has a per-unit overcharge on PO-1002-20; blocked."}'
)


def _tool(call_id: str, name: str, inp: dict) -> LLMResponse:
    return LLMResponse(content=[ToolUseBlock(id=call_id, name=name, input=inp)],
                       stop_reason="tool_use", usage=Usage(input_tokens=12, output_tokens=6))


def _text(text: str) -> LLMResponse:
    return LLMResponse(content=[TextBlock(text=text)],
                       stop_reason="end_turn", usage=Usage(input_tokens=12, output_tokens=30))


class _Scripted:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self._i = 0

    def complete(self, req) -> LLMResponse:
        resp = self._responses[self._i]
        self._i += 1
        return resp


RESPONSES = [
    _tool("c1", "erp__read_invoice", {"invoice_id": "INV-9002"}),
    _tool("c2", "erp__read_po", {"po_id": "PO-1002"}),
    _tool("c3", "erp__read_goods_receipts", {"po_line": "PO-1002-10"}),
    _tool("c4", "erp__read_goods_receipts", {"po_line": "PO-1002-20"}),
    _tool("c5", "web_search", {"query": "Globex Industries supplier"}),
    _tool("c6", "erp__block_invoice", {"invoice_id": "INV-9002", "reason": "price variance on PO-1002-20"}),
    _text(REPORT),
]


def main() -> int:
    RECORDED.mkdir(parents=True, exist_ok=True)
    with erp_toolset() as toolset:
        agent = build_agent(agent_tools(toolset), provider=_Scripted(RESPONSES), store_dir=str(RECORDED))
        result = agent.run(reconcile_task("INV-9002"), approver=lambda req: True)
    shutil.move(result.log_path, TARGET)
    print(f"wrote {TARGET} (status={result.status})")
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
