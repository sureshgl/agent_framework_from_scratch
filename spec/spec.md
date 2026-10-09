# Spec: minimal agent framework (`miniagent`)

Source of intent: `intent/intent.md` (Suresh GL, 2026-10-09). Status: draft,
awaiting review.

This document is the requirements-and-design spec derived directly from
`intent/intent.md`. It is deliberately more ambitious than the earlier
`intent/spec.md`, which scoped the work down to fit a 4-hour timebox (expense
auditor, MCP excluded). Where the two disagree, this spec follows `intent.md`
and flags the cost in §16. Read §16 before planning any increment.

---

## 1. Summary

`miniagent` is a small Python library in which **an agent run is an
append-only log of typed events**. The runtime holds no conversation state of
its own; on every step it derives state by folding the log. Tracing, durable
pause/resume, human approval, policy enforcement, structured output, and
deterministic replay are each a consequence of that one decision, not separate
subsystems.

The organizing claim, from `intent.md`:

> The agent run is an explicit, inspectable runtime. Every model call and tool
> call flows through a single lifecycle and a single policy layer, and every
> step is recorded as a typed event. Control (budgets, permissions, human
> approval) is enforced deterministically, outside the model. It does not ask
> the model to comply.

Two example agents exercise the framework against a real LLM: a primary
**invoice/PO reconciliation agent** (SAP-flavored, MCP + filesystem + web
search + shell) and a secondary ~20-line agent that proves reusability. A
small eval suite scores the primary agent against a known answer key.

---

## 2. Requirements

### 2.1 Functional (traced to `intent.md`)

| ID | Requirement | Source | Acceptance check |
|---|---|---|---|
| FR-1 | Agent loop with explicit budgets and named stop reasons (turns, tokens, cost, wall-clock) | intent §Core 1 | Every run ends with exactly one of: `completed`, `budget_exceeded`, `denied`, `failed`, `paused` |
| FR-2 | Typed tools from plain Python functions; schemas from type hints; args validated before execution | intent §Core 2 | A tool with a wrong-typed argument from the model yields an error tool result, not a crash |
| FR-3 | MCP client: external MCP servers mounted as tools | intent §Core 2 | The reconciliation agent calls a tool served by a local MCP server |
| FR-4 | Lifecycle hooks before/after each model call and each tool call; each returns allow / ask / deny | intent §Core 3 | A deny hook blocks a tool; an ask hook pauses the run |
| FR-5 | Human-in-the-loop approval required for side-effecting actions | intent §Core 3 | A posting/blocking tool pauses with `approval_requested`; resume supplies the decision |
| FR-6 | Append-only JSONL event log; renderable as a readable trace | intent §Core 4 | The on-disk JSONL is the trace; a tracer renders events as they append |
| FR-7 | Replay a run from the log without calling the LLM | intent §Core 4 | A committed run replays with no API key and no network |
| FR-8 | Structured final output validated against a declared schema; retry-with-feedback on failure | intent §Core 5 | A malformed final answer triggers one or more feedback retries, then succeeds or stops with a named reason |
| FR-9 | Reusable: another developer defines and runs a new agent in ~20 lines | intent §Example secondary; §Success | Secondary agent runs with zero changes to the framework |
| FR-10 | One command, one real end-to-end run producing a committed trace | intent §Success | `python -m examples.reconciliation.run` completes live and writes a JSONL trace |
| FR-11 | Development approach documented; coding agent named | intent §Constraints/Process | `DEVELOPMENT.md` logs each increment; names tools + models |

Stretch (implement in this order, only if the timebox allows — see §16):

| ID | Requirement | Source |
|---|---|---|
| FR-S1 | Subagents as tools: a delegated agent with isolated context + its own tool/permission scope | intent §Stretch 6 |
| FR-S2 | Context compaction: summarize the conversation as it nears the context budget | intent §Stretch 7 |
| FR-S3 | Skills: instructions loaded on demand (progressive disclosure) | intent §Stretch 8 |

### 2.2 Non-functional

| ID | Requirement | Source |
|---|---|---|
| NFR-1 | No agent/orchestration frameworks. Runtime deps: `pydantic`, `anthropic`, official `mcp` SDK (protocol lib), `httpx` | intent §Constraints |
| NFR-2 | Core library small enough to read in one sitting (target < 1,000 lines, excluding examples/tests) | intent §Problem; spec NFR |
| NFR-3 | Runtime tests run with no API key and no network | intent §Success; replay |
| NFR-4 | Language Python 3.10+, type hints throughout, small modules | intent §Constraints |
| NFR-5 | The drive loop reads state **only** from the event log; no conversation state on the Agent object | this spec, §4 |

---

## 3. Architecture overview

```
Agent (immutable config)
  │  run() / resume(run_id) / replay(path)
  ▼
drive loop ──────────────── append ──────────────▶ EventLog (JSONL, append-only)
  ▲   │                                               │  subscribe
  │   └── project(events) ◀───────────────────────────┘
  │                                                    │
Provider (Anthropic / OpenAI-compat / Replay)    tracers / sinks
  ▲
  └── Tools (local @tool, MCP-mounted, agent.as_tool())
Policy + Hooks gate every model and tool call, in the loop.
```

- **EventLog** is the single source of truth. `project(events) -> RunState`
  folds the log into the current state (messages for the model, pending tool
  calls, pending approvals, budget counters, terminal status).
- **drive loop** is a pure function of the log plus the Agent config. A fresh
  run, a resumed run, crash recovery, and replay share one code path.
- **Provider** is a thin, synchronous, neutral interface. Adapters translate
  the neutral `Message`/`ToolSpec` to a vendor API and back.
- **Policy + Hooks** are enforced inside the loop, never in the prompt.

---

## 4. Core interfaces

Signatures are the target shape (illustrative, not final). All types use
pydantic models or dataclasses; everything is synchronous (async is a
non-goal, §17).

### 4.1 Event

```python
class Event(BaseModel):
    seq: int                 # 0-based, strictly increasing, gap-free
    type: EventType          # see §7.1
    ts: str                  # ISO-8601 UTC, set at append time
    data: dict               # type-specific payload (schemas in §7)
    run_id: str
```

Events are immutable once appended. `data` shapes per type are in §7.1.

### 4.2 EventLog

```python
class EventLog:
    def __init__(self, path: Path): ...
    def append(self, type: EventType, data: dict) -> Event    # assigns seq+ts, fsync, notifies subscribers
    def events(self) -> list[Event]                           # full history, in order
    def subscribe(self, sink: Callable[[Event], None]) -> None
    @classmethod
    def load(cls, path: Path) -> "EventLog"                   # re-read JSONL into memory
```

One JSONL file per run: `<store_dir>/<run_id>.jsonl`, one event per line.
`append` is the only writer; it fsyncs so a resume after a crash sees the line.

### 4.3 Tool

```python
@tool                                   # derives name, description (docstring), JSON schema from hints
def read_po(po_id: str) -> dict: ...

class Tool(Protocol):
    name: str
    description: str
    schema: dict                        # JSON Schema for arguments
    side_effecting: bool                # default False; True => approval-gated by convention
    def call(self, **kwargs) -> Any     # may raise; the loop converts exceptions to error results
```

- `@tool` inspects the signature; pydantic builds and validates args from the
  JSON Schema before `call`. Return values are JSON-serialized into the
  `tool_result` event.
- Three Tool sources, one interface: local `@tool` functions, MCP-mounted
  tools (§8), and `agent.as_tool()` subagents (§11, stretch).

### 4.4 Hook

```python
class HookPoint(str, Enum):
    before_model = "before_model"
    after_model  = "after_model"
    before_tool  = "before_tool"
    after_tool   = "after_tool"

class Decision(BaseModel):
    action: Literal["allow", "ask", "deny"]
    reason: str = ""

class Hook(Protocol):
    def __call__(self, point: HookPoint, ctx: HookContext) -> Decision | None: ...
```

- `before_*` hooks are **gates**: a returned `Decision` of `deny` blocks the
  action (emits an error result / stops the run); `ask` triggers approval
  (§6). Returning `None` or `allow` lets the loop proceed.
- `after_*` hooks are **observers** that may request a retry — used by
  structured-output validation (FR-8) to reject a final answer and feed the
  validation error back to the model.
- `ctx` (`HookContext`) carries the projected state, the pending model request
  or tool call, and the running budget counters. Hooks must not mutate the log
  directly.
- **Policy (§6) is a built-in before_tool hook**, but is enforced by the
  runtime regardless of user hooks; a user hook can tighten but not loosen it.

### 4.5 Provider

```python
class Message(BaseModel):              # one neutral message type across providers
    role: Literal["system", "user", "assistant", "tool"]
    content: list[ContentBlock]        # text | tool_use | tool_result blocks

class LLMRequest(BaseModel):
    messages: list[Message]
    tools: list[ToolSpec]
    max_tokens: int
    model: str

class LLMResponse(BaseModel):
    content: list[ContentBlock]        # text and/or tool_use blocks
    stop_reason: str
    usage: Usage                       # input/output tokens, cost estimate

class Provider(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...
```

Adapters: `AnthropicProvider` (plain `anthropic` SDK; default, model from
`MINIAGENT_MODEL`), `OpenAICompatibleProvider` (any OpenAI-shaped endpoint),
`ReplayProvider` (returns recorded `llm_response` events in order; §7.2). The
model always sits behind this interface — the loop never imports a vendor SDK.

### 4.6 Policy

```python
class Rule(BaseModel):
    pattern: str                       # glob over tool name, e.g. "post_*", "erp.*", "*"
    action: Literal["allow", "ask", "deny"]

class Budgets(BaseModel):
    max_steps: int | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_wallclock_s: float | None = None
    max_tool_calls: int | None = None

class Policy(BaseModel):
    rules: list[Rule] = [Rule(pattern="*", action="allow")]
    budgets: Budgets = Budgets()
    def decide(self, tool_name: str) -> Decision   # first matching rule wins; default deny if no match
```

### 4.7 Agent

```python
class Agent:
    def __init__(self, name: str, instructions: str, tools: list[Tool] = [],
                 llm: Provider | None = None,               # default AnthropicProvider
                 policy: Policy = Policy(),
                 context: ContextStrategy = FullHistory(),  # §10
                 output_schema: type[BaseModel] | None = None,  # FR-8
                 hooks: list[Hook] = [],
                 store_dir: str = ".runs",
                 on_event: list[Callable] = []): ...

    def run(self, task: str, approver: Approver | None = None) -> RunResult: ...
    def resume(self, run_id: str, decisions: dict[str, bool] | None = None) -> RunResult: ...
    def replay(self, path: str) -> RunResult: ...
    def as_tool(self, name: str | None = None) -> Tool: ...   # §11, stretch
```

The Agent object is immutable config. It carries no per-run mutable state
(NFR-5).

### 4.8 RunResult

```python
class RunResult(BaseModel):
    run_id: str
    status: Literal["completed", "paused", "budget_exceeded", "denied", "failed"]
    output: Any | None            # final text, or validated output_schema instance (FR-8)
    stop_reason: str              # human-readable; mirrors status with detail
    pending_approvals: list[ApprovalRequest]   # non-empty iff status == "paused"
    usage: Usage
    log_path: str
```

`status` is derived from the terminal event in the log, so a resumed or
replayed run reports the same way as a fresh one.

---

## 5. Run lifecycle and where hooks fire

The drive loop, per iteration. `state = project(log.events())` is recomputed
at the top of every iteration; the loop holds no other state.

```
run(task):
  append run_started{task, agent, policy, budgets}
  loop:
    state = project(log.events())

    1. TERMINAL CHECK
       if state.terminal: break

    2. SETTLE PENDING TOOL CALLS (from the last llm_response)
       for each pending tool_use not yet resolved:
         a. decision = Policy.decide(tool) combined with before_tool hooks
            (most restrictive wins)
         b. if deny:  append tool_result{is_error, "denied by policy: <reason>"}
         c. if ask:   append approval_requested{call_id, tool, args}
                      if approver callback present: get decision now
                         append approval_decided{call_id, approved, by}
                      else: append run_paused; return RunResult(status="paused")
            if approval_decided == False:
                      append tool_result{is_error, "denied by approver"}
         d. if allow (or approved):
                      append tool_started{call_id, tool, args}       # C3 crash window
                      validate args (pydantic); on failure ->
                          append tool_result{is_error, validation msg}; continue
                      try: result = tool.call(**args)
                      except Exception as e:
                          append tool_result{is_error, repr(e)}      # self-correction
                      else:
                          after_tool hooks (observe)
                          append tool_result{call_id, result}

    3. BUDGET CHECK
       if any Budgets exceeded (steps/tokens/cost/wallclock/tool_calls):
          append budget_exceeded{which, limit, actual}; break

    4. BUILD MODEL VIEW + CALL LLM
       messages = context.view(state)                 # §10
       before_model hooks (may deny -> append run_failed/denied; break)
       append llm_request{messages_digest, model}
       try: resp = provider.complete(req)   with retry+backoff on transient errors
            (each retry: append llm_retry{attempt, error})
       except: append run_failed{error}; break
       append llm_response{content, stop_reason, usage}

    5. AFTER-MODEL / COMPLETION
       after_model hooks (FR-8: if output_schema set and final answer present,
         validate; on failure append a synthetic tool_result-style feedback and
         continue the loop instead of completing)
       if resp requests no tools:
          if output_schema and not yet valid: continue (retry with feedback)
          append run_completed{output}; break
```

Hook firing points, explicitly:

| Point | When | Can gate? | Primary use |
|---|---|---|---|
| `before_model` | before every `provider.complete` | yes (deny) | rate/scope limits, redaction |
| `after_model` | after every `llm_response` | retry only | structured-output validation (FR-8) |
| `before_tool` | before every tool execution | yes (allow/ask/deny) | policy, approval, arg-level guards |
| `after_tool` | after every successful tool result | no | logging, metrics, PII scrub |

---

## 6. Policy model (allow / ask / deny + approval)

- **Rules** are globs over tool names; **first matching rule wins**; if no rule
  matches, the action is **deny** (fail-closed). Example:
  `[{"post_*": "ask"}, {"erp.read_*": "allow"}, {"shell": "ask"}, {"*": "deny"}]`.
- **Budgets** (turns, tokens, cost, wall-clock, tool-call count) are checked in
  the loop (step 3) and produce `budget_exceeded`, a named terminal reason.
- **Approval** fires when the effective decision is `ask`:
  - If an `approver` callback is supplied to `run()`, the loop asks it inline
    and records `approval_decided`.
  - If no approver, the loop appends `run_paused` and returns
    `status="paused"` with the pending request. The process can exit.
  - `resume(run_id, decisions={call_id: True})` reloads the log in a new
    process, appends the `approval_decided` events, and continues — durable
    HITL falls out of the log, not a server.
- **Side-effecting tools** (`side_effecting=True`, e.g. `post_invoice`,
  `block_invoice`, `write_file`, `shell`) default to `ask` even if a broader
  `allow` rule would match; policy can only tighten this, matching intent's
  "approval required for side-effecting actions."
- Enforcement is in the runtime. The prompt may *describe* the policy for the
  model's benefit, but the loop never relies on the model to honor it.

---

## 7. Event-log schema and replay semantics

### 7.1 Event types and payloads

Each event is one JSON line: `{seq, type, ts, run_id, data}`.

| type | data payload | emitted when |
|---|---|---|
| `run_started` | `{task, agent_name, instructions_digest, policy, budgets, model}` | start of `run()` |
| `run_resumed` | `{resumed_from_seq, by}` | start of `resume()` |
| `llm_request` | `{messages_digest, n_messages, model, max_tokens}` | before each model call |
| `llm_response` | `{content:[blocks], stop_reason, usage:{in,out,cost}}` | after each model call |
| `llm_retry` | `{attempt, error, backoff_s}` | transient provider error |
| `approval_requested` | `{call_id, tool, args}` | effective decision == ask |
| `approval_decided` | `{call_id, approved:bool, by, reason}` | approver/resume answers |
| `tool_started` | `{call_id, tool, args}` | immediately before `tool.call` (C3 marker) |
| `tool_result` | `{call_id, tool, result?, is_error:bool, error?}` | after tool returns/raises |
| `run_paused` | `{pending:[call_id...]}` | ask with no inline approver |
| `budget_exceeded` | `{which, limit, actual}` | budget check fails |
| `run_failed` | `{error, where}` | unrecoverable loop/provider error |
| `run_completed` | `{output, usage_total}` | model requests no tools (+ schema valid) |

Invariants: `seq` is gap-free and increasing; exactly one terminal event per
log (`run_completed` | `budget_exceeded` | `run_failed`), except a log ending
in `run_paused` which is non-terminal and resumable. `project()` must handle a
log that ends mid-tool (a `tool_started` with no matching `tool_result`): see
C3.

### 7.2 Replay semantics

`replay(path)` re-runs the drive loop with:

- a **`ReplayProvider`** that returns the recorded `llm_response` events in
  `seq` order instead of calling an LLM (no key, no network — NFR-3);
- recorded `approval_decided` events answering the approval gates;
- **tools re-executed for real by default.** Replay reproduces the reasoning
  trajectory deterministically; tool *results* are only deterministic if the
  tool is pure. A `replay_tools="recorded"` option returns the logged
  `tool_result` instead of re-calling, for fully hermetic replay. The default
  and the trade-off are stated in the README.
- Divergence (the live loop would request a tool the recording didn't have a
  response for) stops replay with a clear `run_failed{where:"replay-divergence"}`.

Replay is how reviewers without a key verify a run, and how regression tests
pin behavior (NFR-3).

---

## 8. MCP tool integration

MCP is allowed by `intent.md` (the official `mcp` SDK is a protocol library,
not an agent framework). Integration treats an MCP server as **one more Tool
source behind the same `Tool` interface** — the drive loop, policy, and log do
not know a tool came from MCP.

```python
erp = MCPToolset(command=["python", "-m", "examples.reconciliation.erp_server"])
agent = Agent(..., tools=[*erp.tools(), read_file, web_search, shell])
```

- `MCPToolset` spawns/connects to a server (stdio for the local example),
  lists its tools, and wraps each as a `Tool` whose `schema` is the MCP tool's
  input schema and whose `call` issues an MCP `tools/call` and returns the
  result content.
- Tool names are namespaced (`erp.read_po`) so policy globs can target them.
- MCP failures (server down, protocol error) become **error tool results**,
  never crashes (FR-2 self-correction extends to MCP).
- Lifecycle: the toolset is a context manager; the server is torn down when the
  run ends. Only stdio transport is in scope; remote/SSE transport is a
  non-goal (§17). This is the seam where additional MCP transports plug in.

Concern: MCP adds process-management and protocol surface area that competes
with the timebox (§16, C-timebox / C-mcp).

---

## 9. Structured output (FR-8)

- When `output_schema` is set, the final answer must validate against it.
- The schema is passed to the model as guidance (and, where the provider
  supports it, as a tool/JSON-mode spec), but validation is enforced by the
  runtime with pydantic after the model stops requesting tools.
- On validation failure, `after_model` appends feedback (the pydantic error)
  as a user message and the loop continues — a **retry-with-feedback** bounded
  by a dedicated `max_output_retries` (default 2). Exhausting retries ends the
  run as `failed` with the last validation error, never a silent bad result.

---

## 10. Context management

- A `ContextStrategy` chooses the model's *view*; the log always keeps
  everything. `view(state) -> list[Message]`.
- Shipped: `FullHistory` (default) and `SlidingWindow(max_messages|max_tokens)`
  which keeps the system prompt + task + most recent N.
- Stretch `Compaction` (FR-S2): when the view nears the context budget,
  summarize older turns via the provider and splice the summary in, logging a
  `compaction` event so replay stays faithful. Deferred unless the timebox
  allows (§16).

---

## 11. Subagents as tools (FR-S1, stretch)

`agent.as_tool(name)` returns a `Tool` whose `call(task=...)` runs a nested
Agent with its **own event log** (`<store_dir>/<parent_id>.<child>.jsonl`), its
own policy, and an isolated context. The parent sees only the child's final
output as a `tool_result`; the child's full trace is independently inspectable
and replayable. This reuses the entire loop — a subagent is just a tool that
happens to be an agent. Deferred unless the timebox allows (§16).

---

## 12. Example agents

### 12.1 Primary: invoice / PO reconciliation (SAP-flavored)

Performs a **three-way match** of purchase orders, goods receipts, and
supplier invoices over mock ERP data, verifies vendors, computes variances,
and produces a structured reconciliation report. Posting or blocking an
invoice pauses for human approval.

Tools:
- **ERP data via a local MCP server** (§8): `erp.read_po`, `erp.read_goods_receipts`,
  `erp.read_invoice`, `erp.list_invoices`, `erp.read_vendor`, and the
  side-effecting `erp.post_invoice`, `erp.block_invoice` (approval-gated).
- **Filesystem** (`read_file`, `write_file`): read invoice PDFs/notes; write
  the report. Path-allowlisted; `write_file` is side-effecting.
- **Web search** (`web_search`): vendor verification (server-side Anthropic
  web search where available; otherwise a stub returning fixture data so the
  eval is deterministic — flagged in §16).
- **Shell** (`shell`): calculations/exports; allowlisted + approval-gated.

Output schema (FR-8): `ReconciliationReport`.

```python
class LineFinding(BaseModel):
    po_line: str
    issue: Literal["ok", "price_variance", "qty_variance", "missing_gr",
                   "over_tolerance", "no_po"]
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
```

#### Mock ERP data model

Pydantic entities, seeded as JSON fixtures served by the MCP server. Prices in
USD; a per-line price tolerance of ±2% and quantity tolerance of 0 units
unless stated (tolerances live in one `policy.json`, not in the prompt).

```python
class Vendor(BaseModel):
    vendor_id: str
    name: str
    approved: bool            # on the approved-supplier list
    tax_id: str
    country: str

class POLine(BaseModel):
    po_line: str              # e.g. "PO-1001-10"
    material: str
    qty_ordered: int
    unit_price: float

class PurchaseOrder(BaseModel):
    po_id: str                # "PO-1001"
    vendor_id: str
    currency: str
    lines: list[POLine]

class GoodsReceipt(BaseModel):
    gr_id: str                # "GR-5001"
    po_line: str              # FK to POLine.po_line
    qty_received: int
    received_date: str

class InvoiceLine(BaseModel):
    po_line: str              # FK; may be absent -> no_po finding
    qty_billed: int
    unit_price: float

class Invoice(BaseModel):
    invoice_id: str           # "INV-9001"
    vendor_id: str
    po_id: str
    currency: str
    lines: list[InvoiceLine]
    total: float
    received_date: str
```

Seeded dataset: one vendor master (approved + unapproved vendors), ~6 POs with
goods receipts, and ~10 invoices containing a known set of discrepancies (the
answer key for §13). At least one discrepancy must require arithmetic the model
can get wrong without the shell/calc tool (e.g. a per-line unit-price ×
quantity rollup that hides a small per-unit overcharge).

### 12.2 Secondary: ~20-line reusability agent

A different agent, defined in ≤ 20 lines, reusing the framework with different
tools and a different `output_schema` and **no framework changes** (FR-9).
Proposed: a *release-notes drafter* — tools `read_file` (changelog) +
`web_search`; `output_schema = ReleaseNotes(headline, highlights, breaking)`.
Intentionally has no approval gate, to contrast with the primary agent.

---

## 13. Eval cases and expected outcomes

Each eval runs (or replays) the primary agent and asserts on the resulting
**event log + final `ReconciliationReport`** against the seeded answer key.
Because one live run is a weak signal, the suite runs the live scoring 3× and
records each score (not only an average). Replay-based evals are deterministic
and run keyless in CI (NFR-3).

| # | Scenario (seeded) | Expected report outcome | Expected log/gate assertion |
|---|---|---|---|
| E1 | Clean invoice, PO + GR + price all match | `three_way_match=pass`, `recommendation=post` | `post_invoice` requested → `approval_requested` fires |
| E2 | Unit price above tolerance (small per-unit overcharge hidden in a large line total) | `price_variance` finding with correct `variance_usd`; `recommendation=block` | shell/calc tool used; `block_invoice` is approval-gated |
| E3 | Qty billed > qty received | `qty_variance`; `recommendation=hold_for_review` | no posting without approval |
| E4 | Invoice line references a PO line with **no goods receipt** | `missing_gr`; `recommendation=block` | — |
| E5 | Duplicate invoice (same vendor/PO/amount as an already-posted one) | `duplicate_of` set; `recommendation=block` | detected without posting |
| E6 | Invoice from an **unapproved vendor** | `vendor_verified=false`; `recommendation=hold_for_review` | `web_search`/`erp.read_vendor` consulted |
| E7 | Invoice line with no matching PO line (`no_po`) | `no_po` finding; `recommendation=block` | — |
| E8 | Budget starvation: `max_steps` set too low | run ends `budget_exceeded` | terminal `budget_exceeded`, no partial post |
| E9 | Approval denied on resume for a flagged post | invoice not posted | `approval_decided{approved:false}` → error `tool_result`, no side effect |
| E10 | Replay of a committed E1–E7 run | identical verdicts | keyless, networkless replay matches recorded `run_completed` |

Misses the eval exposes are written up as a *new intent* before being fixed
(the eval-driven loop in §15 of `intent.md`'s process).

---

## 14. Dependency boundary / framework-ban compliance

- **Allowed runtime deps:** `pydantic` (schemas/validation), `anthropic` (model
  + server-side web search), the official `mcp` SDK (protocol), `httpx`
  (OpenAI-compatible transport). Dev-only: `pytest`.
- **Banned:** any agent/orchestration framework — Claude Agent SDK, LangChain,
  LangGraph, LlamaIndex, CrewAI, AutoGen, Haystack, or equivalents. The drive
  loop, tool schema derivation, policy, and event log are all first-party.
- The provider interface (§4.5) keeps vendor SDK imports out of the loop; only
  adapter modules import `anthropic`/`httpx`.

---

## 15. Increment map

Extends the spec §4 map in `intent/spec.md`; aligned to this spec's scope.

| # | Increment | Exit criterion |
|---|---|---|
| 0 | Intent, this spec, CLAUDE.md, REVIEW.md | This spec accepted |
| 1 | Minimal loop: `Event`/`EventLog`, `@tool`, Anthropic adapter, `max_steps` | Live run with one trivial tool |
| 2 | Log as source of truth: `project()`, tracer, `RunResult` | Loop holds no state outside the log (NFR-5) |
| 3 | Policy, hooks, approvals, pause/resume from disk | Pause, kill process, resume to completion |
| 4 | Structured output + retry-with-feedback | A malformed answer recovers via feedback |
| 5 | MCP toolset + local ERP server + filesystem/shell tools | Reconciliation agent calls an MCP tool |
| 6 | Reconciliation agent + eval suite (E1–E9) | Live scores recorded 3× |
| 7 | Replay + OpenAI-compatible adapter + regression evals (E10) | Keyless replay of a committed run |
| 8 | Secondary agent; context window; docs; fresh-clone < 5 min | Secondary runs unchanged |
| S | Subagents, compaction, skills | Only if time remains (§16) |

Each increment gets `plans/NN-<name>.md` before implementation.

---

## 16. Concerns, open questions, and constraint conflicts

Decide the starred items before increment 1.

| ID | Concern / conflict | Recommended default |
|---|---|---|
| **C-timebox*** | **Hard conflict.** `intent.md` makes MCP, structured output, web search, shell, and the full reconciliation agent *must-haves*, but also fixes effort at ~4 hours. The earlier `intent/spec.md` resolved this by cutting to an expense auditor and excluding MCP. This spec keeps the fuller scope per your instruction — it will not fit 4 hours. | Treat §15 increments 1–4 as the real deliverable; 5–8 as stretch. Cut from the bottom of §15; record each cut as a non-goal. Do **not** cut quality (NFR-2/3). |
| **C-mcp*** | MCP integration (§8) adds process/protocol surface that is the single biggest timebox risk. | Build tools as plain `@tool` first; mount the ERP server via MCP only once increments 1–4 are green. If cut, keep the ERP tools local and note the MCP seam. |
| **C-websearch*** | `web_search` against the real web makes evals non-deterministic and may need network in CI (conflicts with NFR-3). | Use Anthropic server-side web search live; back E6 with a deterministic fixture/stub so replay + CI stay keyless and stable. |
| **C-shell*** | A `shell` tool is a real security surface even in a demo. | Allowlist + approval-gate + non-interactive + working-dir jail; document that this is not production hardening (intent out-of-scope). |
| **C-replay-tools** | Replay re-executes tools by default; impure tools (shell, web, clock) won't reproduce. | Default re-execute; offer `replay_tools="recorded"` for hermetic replay; state the trade-off (§7.2). |
| **C-at-least-once** | A crash after `tool_started` but before `tool_result` re-runs the tool on resume (carried from spec C3). | Log `tool_started` so the window is detectable; document at-least-once; make the ERP post idempotent by `invoice_id`. |
| **C-eval-nondeterminism** | One live run is weak signal (carried from spec C4). | Run live scoring 3×; report each (E-suite §13). |
| **C-policy-ambiguity** | For a disallowed line, is the whole invoice blocked or only the offending line? (analogue of spec C5) | Block the whole invoice; record findings per line; state the assumption in `policy.json`. |
| **C-model-name** | Model identifiers drift (carried from spec C6). | Read `MINIAGENT_MODEL`; document the default in one place. |
| **C-spec-dualism*** | Two specs now exist (`intent/spec.md`, this `spec/spec.md`) that disagree on scope. | Pick one as authoritative before coding. Recommended: adopt this `spec/spec.md` and either delete or mark `intent/spec.md` as superseded, to avoid CLAUDE.md's "read the spec" pointing at two files. |
| OQ-1 | Does the secondary agent need its own eval, or is "runs unchanged" enough for FR-9? | A smoke test asserting it completes is enough. |
| OQ-2 | Cost budget needs a price table per model; where does it live? | A small `prices.json`; absent entry ⇒ cost budget disabled with a warning. |
| OQ-3 | `after_model` doing both observation and retry-gating blurs the hook model (§4.4). | Acceptable for now; revisit if a second retry-style hook appears. |

---

## 17. Non-goals

Streaming; async and parallel tool execution; long-term memory; remote/SSE MCP
transport (stdio only); A2A; sandboxed code execution; production hardening of
the shell tool beyond allowlist + approval; multi-provider breadth (interface
only, Anthropic + one OpenAI-compatible endpoint implemented); any UI;
persistence beyond local JSONL files; CI/CD beyond the keyless replay evals.
