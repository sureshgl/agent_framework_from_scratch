"""Demo: reconcile an invoice end to end against the real LLM.

Approval modes (post/block are side-effecting and gated by policy):

    python -m examples.reconciliation [INVOICE_ID]               # auto-approve (default)
    python -m examples.reconciliation [INVOICE_ID] --interactive # prompt y/N at the gate
    python -m examples.reconciliation [INVOICE_ID] --await       # pause at the gate and exit
    python -m examples.reconciliation resume <run_id> approve|deny

INVOICE_ID defaults to INV-9002. `--await` returns a paused run whose state lives
only in runs/<run_id>.jsonl; `resume` reloads it in a fresh process and supplies
the decision. Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from minagent import ConsoleTracer, EventLog
from minagent.state import project

from .agent import reconcile_task, reconciliation_agent

STORE_DIR = "runs"


def _has_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    print("ANTHROPIC_API_KEY is not set; the demo needs a live model.")
    return False


def _prompt_approver(req) -> bool:
    print(f"\n>>> APPROVAL NEEDED: {req.tool}({req.args})")
    return input("    approve? [y/N] ").strip().lower() in ("y", "yes")


def _print_result(result) -> None:
    print(f"\nstop_reason={result.status}")
    if result.output is not None:
        for verdict in result.output.verdicts:
            print(f"  {verdict.invoice_id}: {verdict.recommendation} "
                  f"(match={verdict.three_way_match}, vendor_verified={verdict.vendor_verified})")
            for f in verdict.findings:
                print(f"    - {f.po_line}: {f.issue} {f.detail}")
    print(f"event log: {result.log_path}")


def _print_pause(result) -> None:
    print(f"\nstop_reason=paused  run_id={result.run_id}")
    print("pending approvals:")
    for req in result.pending_approvals:
        print(f"  - {req['call_id']}: {req['tool']}({req['args']})")
    print(f"event log: {result.log_path}")
    print("\nResume with your decision:")
    print(f"  python -m examples.reconciliation resume {result.run_id} approve")
    print(f"  python -m examples.reconciliation resume {result.run_id} deny")


def _run(invoice_id: str, *, interactive: bool, await_mode: bool) -> int:
    if not _has_key():
        return 1
    approver = None if await_mode else (_prompt_approver if interactive else (lambda req: True))
    with reconciliation_agent(store_dir=STORE_DIR, on_event=[ConsoleTracer()]) as agent:
        result = agent.run(reconcile_task(invoice_id), approver=approver)
    if result.status == "paused":
        _print_pause(result)
        return 0
    _print_result(result)
    return 0 if result.status == "completed" else 1


def _resume(run_id: str, decision: str) -> int:
    approved = decision.lower() in ("approve", "yes", "y", "true")
    if not _has_key():
        return 1
    log_path = Path(STORE_DIR) / f"{run_id}.jsonl"
    if not log_path.exists():
        print(f"no such run: {log_path}")
        return 1
    state = project(EventLog.load(log_path).events())
    pending = [cid for cid in state.approval_requests if cid not in state.approvals]
    if not pending:
        print(f"run {run_id} has no pending approvals.")
        return 1
    decisions = {cid: approved for cid in pending}
    print(f"{'approving' if approved else 'denying'} {len(pending)} pending call(s): {pending}")
    with reconciliation_agent(store_dir=STORE_DIR, on_event=[ConsoleTracer()]) as agent:
        result = agent.resume(run_id, decisions=decisions)
    _print_result(result)
    return 0 if result.status == "completed" else 1


def main(argv: list[str]) -> int:
    if argv and argv[0] == "resume":
        if len(argv) != 3 or argv[2].lower() not in ("approve", "deny"):
            print("usage: python -m examples.reconciliation resume <run_id> approve|deny")
            return 2
        return _resume(argv[1], argv[2])

    flags = {a for a in argv if a.startswith("-")}
    positionals = [a for a in argv if not a.startswith("-")]
    invoice_id = positionals[0] if positionals else "INV-9002"
    interactive = "--interactive" in flags or "-i" in flags
    await_mode = "--await" in flags or "--pause" in flags
    if interactive and await_mode:
        print("choose one of --interactive or --await, not both")
        return 2
    return _run(invoice_id, interactive=interactive, await_mode=await_mode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
