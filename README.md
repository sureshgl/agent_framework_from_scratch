# minagent

A minimal agent framework, built from scratch. Its one organizing idea:

> **An agent run is an append-only log of typed events.** The runtime holds no
> conversation state of its own — on every step it derives state by folding the
> log. Tracing, durable pause/resume, human approval, policy, structured output,
> and deterministic replay are all consequences of that one decision, not
> separate subsystems.

Control (budgets, permissions, approval) is enforced deterministically in the
runtime, not requested of the model. No agent or orchestration framework is used;
the runtime dependencies are `pydantic`, the `anthropic` SDK, and the `mcp`
protocol SDK.

## Quickstart

```bash
pip install -e ".[dev]"
make test            # unit tests — no API key, no network
export ANTHROPIC_API_KEY=sk-...
make demo            # reconcile one invoice end to end, with a live trace
make evals           # score the reconciliation agent against the answer key
```

No API key handy? You can still replay a committed run with no key and no
network:

```python
from minagent import Agent
from examples.reconciliation.models import ReconciliationReport

agent = Agent("reconciliation", "", output_schema=ReconciliationReport)
result = agent.replay("evals/recorded/reconcile_INV-9002.jsonl", replay_tools="recorded")
print(result.status, result.output.verdicts[0].recommendation)   # completed block
```

## Define an agent (reusability)

A complete agent — a different tool, a different output schema — in ~20 lines
(`examples/release_notes/agent.py`), with no changes to the framework:

```python
from pathlib import Path
from pydantic import BaseModel
from minagent import Agent, tool

class ReleaseNotes(BaseModel):
    headline: str
    highlights: list[str]
    breaking: list[str]

@tool
def read_changelog(path: str) -> str:
    """Read a changelog file and return its contents."""
    return Path(path).read_text(encoding="utf-8")

agent = Agent(
    name="release-notes",
    instructions="Draft release notes from the changelog. Read it, then produce the notes.",
    tools=[read_changelog],
    output_schema=ReleaseNotes,
)
notes = agent.run("Draft notes from CHANGELOG.md").output   # a typed ReleaseNotes
```

## Capabilities, and where each comes from

| Capability | How it works |
|---|---|
| Typed tools | `@tool` turns type hints into a JSON schema; pydantic validates the model's arguments before the call |
| Self-correction | Bad arguments, unknown tools, and tool exceptions become error results, never crashes |
| Budgets & stop reasons | Steps, tokens, cost, wall-clock, and tool-call limits checked in the loop; every run ends with a named reason |
| Policy | Per-tool allow / ask / deny globs (first-match, fail-closed); side-effecting tools floored to `ask` |
| Human in the loop | `ask` pauses with `approval_requested`; the decision is an event, from an inline approver or supplied on `resume` |
| Durability | `resume(run_id)` reloads the JSONL log in a fresh process and continues |
| Structured output | A declared `output_schema` is validated after the model stops; failures are fed back and retried |
| Observability | Subscribers render events as they are appended; the JSONL file *is* the trace |
| Replay | `replay(path)` re-drives a recorded run with no key or network; recorded approvals answer the gates |
| MCP tools | `MCPToolset` mounts a stdio MCP server's tools as ordinary tools |
| Context control | A `ContextStrategy` (`FullHistory`, `SlidingWindow`) chooses the model's view; the log keeps everything |

## How it works

```
Agent (immutable config)
  │  run() / resume(run_id) / replay(path)
  ▼
drive loop ───── append ─────▶ EventLog (JSONL, append-only)  ── subscribe ─▶ tracers
  ▲   │                               │
  │   └── project(events) ◀───────────┘
Provider (Anthropic / Replay)   Policy + Hooks gate every model & tool call, in the loop
```

Each loop iteration recomputes `state = project(log.events())`, settles any
pending tool call (policy → approval → validate → execute), checks budgets, calls
the model, and completes when no tools are requested. Because state lives only in
the log, a fresh run, a resumed run, crash recovery, and replay share one code
path.

## Examples

- **`examples/reconciliation`** (primary) — an SAP-flavored invoice/PO
  reconciliation agent. ERP data is served over a local MCP server
  (`erp_server.py`); the agent does a three-way match (PO ↔ goods receipts ↔
  invoice), verifies the vendor, and posts or blocks the invoice behind an
  approval gate, producing a validated `ReconciliationReport`.
  Run: `make demo` or `python -m examples.reconciliation INV-9002`.
- **`examples/release_notes`** (secondary) — the ~20-line agent above, proving
  reuse. Run: `python -m examples.release_notes`.

## Project layout & process

```
src/minagent/     the framework (events, state, loop, tools, policy, hooks,
                  budgets, output, context, providers, mcp_tools)
examples/         reconciliation (primary) and release_notes (secondary)
tests/            unit tests — no network, no key (scripted fake provider)
evals/            agent evals (real LLM) + committed recorded run for replay
intent/ spec/ plan/   the design chain: intent.md -> spec/spec.md -> plan/plan.md
```

Development followed an artifact chain: `intent/intent.md` → `spec/spec.md` →
`plan/plan.md` → code, in eight reviewed increments. See `DEVELOPMENT.md` for the
log and `REVIEW.md` for the review policy.

## Coding agents used

Design and planning were done with Claude via claude.ai; the implementation was
done with **Claude Code** (model `claude-opus-4-8`). Default runtime model is
`claude-sonnet-4-6`, overridable with `MINAGENT_MODEL`.

## Non-goals

Streaming, async/parallel tool execution, long-term memory, remote/SSE MCP
transport, multi-provider breadth (the `Provider` interface exists; only
Anthropic + replay are implemented), production hardening of the shell tool, and
any UI.
