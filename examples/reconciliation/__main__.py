"""Demo: reconcile one invoice end to end against the real LLM.

    python -m examples.reconciliation [INVOICE_ID]   # default INV-9002

Prints a readable trace, the stop reason, and the path to the event log.
Approvals are auto-granted so the run completes; the gate still fires and is
visible in the trace.
"""

from __future__ import annotations

import os
import sys

from minagent import ConsoleTracer

from .agent import reconcile_task, reconciliation_agent


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; the demo needs a live model.")
        return 1

    invoice_id = sys.argv[1] if len(sys.argv) > 1 else "INV-9002"
    with reconciliation_agent(on_event=[ConsoleTracer()]) as agent:
        result = agent.run(reconcile_task(invoice_id), approver=lambda req: True)

    print()
    print(f"stop_reason={result.status}")
    if result.output is not None:
        for verdict in result.output.verdicts:
            print(f"  {verdict.invoice_id}: {verdict.recommendation} "
                  f"(match={verdict.three_way_match}, vendor_verified={verdict.vendor_verified})")
            for f in verdict.findings:
                print(f"    - {f.po_line}: {f.issue} {f.detail}")
    print(f"event log: {result.log_path}")
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
