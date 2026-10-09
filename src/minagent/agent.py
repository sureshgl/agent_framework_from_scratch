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
from typing import Any, Callable, Iterable

from .events import EventLog
from .loop import drive
from .messages import Usage
from .provider import Provider
from .state import project
from .tools import Tool

DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass
class RunResult:
    run_id: str
    status: str  # completed | budget_exceeded | failed | paused
    output: Any
    stop_reason: str
    log_path: str
    usage: Usage = field(default_factory=Usage)


def _result_from_log(log: EventLog) -> RunResult:
    state = project(log.events())
    status = state.status or "failed"
    return RunResult(
        run_id=log.run_id,
        status=status,
        output=state.output,
        stop_reason=status,
        log_path=str(log.path),
        usage=state.usage,
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
        self.max_steps = max_steps
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

    def run(self, task: str) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        log = EventLog.create(self.store_dir, run_id)
        for sink in self.on_event:
            log.subscribe(sink)
        log.append(
            "run_started",
            {"task": task, "agent_name": self.name, "model": self.model},
        )
        drive(self, log)
        return _result_from_log(log)
