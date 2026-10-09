"""Run the reconciliation eval suite against a live model.

    python -m evals.run            # 1 round (set EVAL_ROUNDS=3 for a stronger signal)

Prints one PASS/FAIL line per case, a per-round score, and a final
`evals: K/K passed`. A live eval is non-deterministic, so running several rounds
(EVAL_ROUNDS) and reading each score separately is a stronger signal than one
sample (spec C-eval); the default is 1 to keep it fast and cheap.
Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os

from minagent import EventLog, EventType

from examples.reconciliation.agent import (
    agent_tools,
    build_agent,
    erp_toolset,
    reconcile_task,
)
from evals.cases import ANSWER_KEY, REPORT_CASES, all_passed, failed_checks, score_verdict

ROUNDS = int(os.environ.get("EVAL_ROUNDS", "1"))
_APPROVE = lambda req: True  # noqa: E731


def _verdict_for(report, invoice_id):
    if report is None:
        return None
    for verdict in report.verdicts:
        if verdict.invoice_id == invoice_id:
            return verdict
    return None


def _run_report_case(agent, invoice_id) -> tuple[bool, str]:
    result = agent.run(reconcile_task(invoice_id), approver=_APPROVE)
    verdict = _verdict_for(result.output, invoice_id)
    if verdict is None:
        return False, f"no verdict (status={result.status})"
    checks = score_verdict(verdict, ANSWER_KEY[invoice_id])
    return all_passed(checks), ", ".join(failed_checks(checks)) or "ok"


def _run_budget_case(toolset) -> tuple[bool, str]:
    agent = build_agent(agent_tools(toolset), max_steps=1)
    result = agent.run(reconcile_task("INV-9001"), approver=_APPROVE)
    return result.status == "budget_exceeded", f"status={result.status}"


def _run_deny_resume_case(toolset) -> tuple[bool, str]:
    agent = build_agent(agent_tools(toolset))
    paused = agent.run(reconcile_task("INV-9001"))  # no approver -> pause on post
    if paused.status != "paused" or not paused.pending_approvals:
        return False, f"did not pause for approval (status={paused.status})"
    call_id = paused.pending_approvals[0]["call_id"]
    resumed = agent.resume(paused.run_id, decisions={call_id: False})
    denied = any(
        e.type == EventType.tool_result
        and e.data.get("is_error")
        and "denied by approver" in str(e.data.get("error", ""))
        for e in EventLog.load(resumed.log_path).events()
    )
    return denied, "post denied, not executed" if denied else "post was not denied"


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; evals require a live model.")
        return 1

    passed = total = 0
    for rnd in range(1, ROUNDS + 1):
        print(f"\n=== round {rnd}/{ROUNDS} ===")
        passed = total = 0
        with erp_toolset() as toolset:
            for eval_id, invoice_id in REPORT_CASES:
                ok, detail = _run_report_case(build_agent(agent_tools(toolset)), invoice_id)
                total += 1
                passed += ok
                print(f"[{'PASS' if ok else 'FAIL'}] {eval_id} {invoice_id}: {detail}")
            for eval_id, fn in (("E8", _run_budget_case), ("E9", _run_deny_resume_case)):
                ok, detail = fn(toolset)
                total += 1
                passed += ok
                print(f"[{'PASS' if ok else 'FAIL'}] {eval_id}: {detail}")
        print(f"round {rnd}: {passed}/{total} passed")

    print(f"\nevals: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
