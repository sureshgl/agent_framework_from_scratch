"""The event log: the single source of truth for a run.

Every step of a run is appended here as one typed, immutable JSON line. The
drive loop holds no other state; `state.project()` folds this log back into the
current `RunState`. Durability, tracing, and replay are all consequences of
this file existing.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field


class EventType(str, Enum):
    run_started = "run_started"
    run_resumed = "run_resumed"
    llm_request = "llm_request"
    llm_response = "llm_response"
    llm_retry = "llm_retry"
    approval_requested = "approval_requested"
    approval_decided = "approval_decided"
    tool_started = "tool_started"
    tool_result = "tool_result"
    run_paused = "run_paused"
    budget_exceeded = "budget_exceeded"
    run_failed = "run_failed"
    run_completed = "run_completed"


class Event(BaseModel):
    seq: int
    type: EventType
    ts: str
    run_id: str
    data: dict[str, Any] = Field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLog:
    """An append-only JSONL log, one file per run.

    `append` is the only writer: it assigns a gap-free `seq`, stamps the time,
    fsyncs the line to disk (so a crash after append is recoverable), and
    notifies subscribers.
    """

    def __init__(self, path: Path | str, run_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id
        self._events: list[Event] = []
        self._subscribers: list[Callable[[Event], None]] = []

    @classmethod
    def create(cls, store_dir: Path | str, run_id: str) -> "EventLog":
        store = Path(store_dir)
        store.mkdir(parents=True, exist_ok=True)
        return cls(store / f"{run_id}.jsonl", run_id)

    @classmethod
    def load(cls, path: Path | str) -> "EventLog":
        """Reload a run from disk into memory (used by resume and replay)."""
        path = Path(path)
        log = cls(path, run_id=path.stem)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = Event.model_validate_json(line)
                log._events.append(ev)
                log.run_id = ev.run_id
        return log

    def append(self, type: EventType | str, data: dict[str, Any]) -> Event:
        ev = Event(
            seq=len(self._events),
            type=EventType(type),
            ts=_now_iso(),
            run_id=self.run_id,
            data=data,
        )
        self._events.append(ev)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(ev.model_dump_json() + "\n")
            f.flush()
            os.fsync(f.fileno())
        for sink in self._subscribers:
            sink(ev)
        return ev

    def events(self) -> list[Event]:
        return list(self._events)

    def subscribe(self, sink: Callable[[Event], None]) -> None:
        self._subscribers.append(sink)
