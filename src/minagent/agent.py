"""`Agent`: immutable run configuration, plus `run()`.

The Agent carries no per-run mutable state (NFR-5). Each `run()` creates a fresh
event log, seeds it with `run_started`, hands it to the drive loop, and derives a
`RunResult` from the terminal event. `resume()` and `replay()` arrive in later
increments and reuse the same loop.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .budgets import Budgets
from .events import EventLog
from .hooks import Hook
from .loop import Approver, drive
from .messages import Usage
from .policy import Policy
from .provider import Provider
from .state import project
from .tools import Tool

DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass
class RunResult:
    run_id: str
    status: str  # completed | paused | budget_exceeded | failed
    output: Any
    stop_reason: str
    log_path: str
    usage: Usage = field(default_factory=Usage)
    pending_approvals: list[dict] = field(default_factory=list)


def _result_from_log(log: EventLog) -> RunResult:
    state = project(log.events())
    status = state.status or "failed"
    pending_approvals = [
        {"call_id": cid, **req}
        for cid, req in state.approval_requests.items()
        if cid not in state.approvals
    ]
    return RunResult(
        run_id=log.run_id,
        status=status,
        output=state.output,
        stop_reason=status,
        log_path=str(log.path),
        usage=state.usage,
        pending_approvals=pending_approvals,
    )


class Agent:
    def __init__(
        self,
        name: str,
        instructions: str,
        tools: Iterable[Tool] = (),
        provider: Provider | None = None,
        model: str | None = None,
        max_steps: int | None = 10,
        budgets: Budgets | None = None,
        policy: Policy | None = None,
        hooks: Iterable[Hook] = (),
        max_tokens: int = 1024,
        store_dir: str = ".runs",
        on_event: Iterable[Callable] = (),
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.tools = list(tools)
        self.tools_by_name = {t.name: t for t in self.tools}
        self._provider = provider
        self.model = model or os.environ.get("MINAGENT_MODEL", DEFAULT_MODEL)
        # `budgets` is authoritative; `max_steps` is a convenience that seeds it.
        self.budgets = budgets if budgets is not None else Budgets(max_steps=max_steps)
        self.policy = policy if policy is not None else Policy()
        self.hooks = list(hooks)
        self.max_tokens = max_tokens
        self.store_dir = store_dir
        self.on_event = list(on_event)

    @property
    def provider(self) -> Provider:
        # Constructed lazily so building an Agent (or running with a fake
        # provider) never requires the anthropic SDK or an API key.
        if self._provider is None:
            from .providers.anthropic import AnthropicProvider

            self._provider = AnthropicProvider()
        return self._provider

    def run(self, task: str, approver: Approver | None = None) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        log = EventLog.create(self.store_dir, run_id)
        for sink in self.on_event:
            log.subscribe(sink)
        log.append(
            "run_started",
            {"task": task, "agent_name": self.name, "model": self.model},
        )
        drive(self, log, approver=approver)
        return _result_from_log(log)

    def resume(
        self,
        run_id: str,
        decisions: dict[str, bool] | None = None,
        approver: Approver | None = None,
    ) -> RunResult:
        """Reload a paused run from disk and continue it.

        `decisions` answers outstanding approvals (`{call_id: approved}`); they are
        appended as `approval_decided` events before the loop resumes, so the
        decision lives in the log exactly as an inline approver's would.
        """
        path = Path(self.store_dir) / f"{run_id}.jsonl"
        log = EventLog.load(path)
        for sink in self.on_event:
            log.subscribe(sink)
        for call_id, approved in (decisions or {}).items():
            log.append(
                "approval_decided",
                {"call_id": call_id, "approved": bool(approved), "by": "resume"},
            )
        log.append("run_resumed", {"by": "resume"})
        drive(self, log, approver=approver)
        return _result_from_log(log)
