# Implementation plan: `minagent`

## Context

`minagent` is a from-scratch agent framework whose organizing idea is that **an
agent run is an append-only log of typed events**; the runtime derives all state
by folding that log, so tracing, pause/resume, approval, policy, structured
output, and replay all fall out of one decision. The design is fixed in
`intent/intent.md` → `spec/spec.md`; this plan turns it into code.

The repo is scaffolded (`pyproject.toml` → pkg `minagent`, `src/minagent/`,
`Makefile`, empty `examples/`, `evals/`) but has **no framework code yet**. Deps
are hard-limited to `anthropic`, `mcp`, `pydantic`, stdlib. The goal: build the
core framework so it is **buildable, tested, and demoable before any stretch
capability**, then layer the reconciliation example, evals, and replay on top.

Two scope decisions confirmed with the user:
- **Providers:** build the `Provider` interface + `AnthropicProvider` +
  `ReplayProvider` only. No OpenAI-compatible adapter (matches `intent.md`;
  `spec/spec.md` §4.5/§15 will be updated to drop it).
- **MCP:** build the ERP as plain local tools first so the demo works without
  MCP, then expose it via a local MCP server in the same increment — keeping MCP
  (the biggest timebox risk) off the critical path and cuttable.

Work lands increment by increment on a branch per the CLAUDE.md process, verified
with `make test` (and `make evals`/`make demo` where noted) before each is
called done. This file is kept in sync; if the implementation departs from it,
it is updated in the same commit.

---

## Target module layout

```
src/minagent/
  __init__.py        public API: Agent, tool, Policy, Rule, Budgets, RunResult, hooks, providers
  events.py          Event, EventType, EventLog (JSONL append/load/subscribe, fsync)
  state.py           RunState + project(events) -> RunState   ← load-bearing fold
  messages.py        Message, ContentBlock (text|tool_use|tool_result), Usage
  provider.py        Provider protocol, LLMRequest, LLMResponse
  providers/
    anthropic.py     AnthropicProvider (wraps the anthropic SDK)
    replay.py        ReplayProvider (returns recorded llm_response events)
  tools.py           @tool decorator, Tool protocol, JSON-schema from type hints
  budgets.py         Budgets + check (named terminal limits)   [landed Inc 2]
  policy.py          Decision, Rule, Policy (glob, fail-closed) + ApprovalRequest   [Inc 3]
  hooks.py           HookPoint, Hook, HookContext
  loop.py            the drive loop: _drive(agent, log) shared by run/resume/replay
  agent.py           Agent, RunResult, Approver
  context.py         ContextStrategy, FullHistory, SlidingWindow
  output.py          structured-output validation + retry-with-feedback
  builtins.py        read_file, write_file, shell, web_search tools
  mcp_tools.py       MCPToolset (stdio transport)
  tracing.py         ConsoleTracer

tests/               unit tests, no network, FakeProvider (conftest.py)
evals/               run.py (prints "evals: K/K passed"), cases.py, answer_key.json, recorded/*.jsonl
examples/reconciliation/  __main__.py (make demo), agent.py, erp_server.py, models.py, policy.json, data/
examples/release_notes/   __main__.py, agent.py   (secondary ~20-line agent)
```

---

## Order of work (core first, then example, then stretch)

Each increment ends green on `make test`. Milestones marked **DEMOABLE**.

### Inc 1 — Event log, types, tools, minimal loop, Anthropic provider
- Files: `events.py`, `messages.py`, `provider.py`, `providers/anthropic.py`,
  `tools.py`, minimal `state.py`, minimal `loop.py` (`max_steps` only, no policy
  yet), `agent.py` (`run()` only), `tracing.py`, `__init__.py`.
- Proof — tests: `test_events` (seq gap-free, append/load round-trip, fsync),
  `test_tools` (schema from hints, pydantic arg validation, tool exception →
  error `tool_result`), `test_state_project` (pairs `tool_use`↔`tool_result`,
  derives model messages), `test_loop` (FakeProvider: trivial tool → result →
  `run_completed`; `max_steps` → stop).
- **DEMOABLE #1:** live run with one trivial tool against Anthropic.

### Inc 2 — Log as the only source of truth
- Files: complete `state.py` `project()`; `RunResult` derivation in `agent.py`;
  wire `ConsoleTracer` via `EventLog.subscribe`; full `Budgets` (tokens, cost,
  wallclock, tool-call count) + `budget_exceeded` in `loop.py`.
  (Deviation: `Budgets` lives in its own `budgets.py`, not `policy.py`, to keep
  modules small; `policy.py` in Inc 3 imports it.)
- Proof — tests: budget cases per limit type; `RunResult.status` derived from the
  terminal event; tracer receives events in order. Assert the loop keeps **no**
  state outside the log (NFR-5) by re-projecting mid-run.

### Inc 3 — Policy, hooks, approvals, pause/resume from disk
- Files: `policy.py`, `hooks.py`; extend `loop.py` settle-step (policy +
  before/after hooks → allow/ask/deny → validate → execute); `agent.py`
  `resume()` + `approver`.
- Proof — tests: `test_policy` (glob first-match, fail-closed default-deny),
  `test_hooks` (four fire points; deny blocks; most-restrictive wins),
  `test_approvals_resume` (inline approver; no approver → `run_paused`;
  `resume(run_id, decisions)` reloads a fresh `EventLog` and continues; deny →
  error `tool_result`, no side effect; `tool_started` present as the C3 marker).
- **DEMOABLE #2:** pause on an `ask` tool, kill the process, `resume` to finish.

### Inc 4 — Structured output + retry-with-feedback
- Files: `output.py`; wire `output_schema` + `max_output_retries` (default 2)
  into `loop.py`/`after_model`.
- Proof — tests: `test_output` (valid passes; invalid → pydantic error fed back
  → retry → success; retries exhausted → `failed` with the validation error).
- **CORE COMPLETE & DEMOABLE #3:** a reusable framework — typed tools, event-log
  truth, policy/approval/pause-resume, structured output — demoable end-to-end
  with only built-in tools. Everything below is example/hardening, cuttable from
  the bottom under the timebox.

### Inc 5 — Built-in tools + MCP toolset + local ERP server
- Files: `builtins.py` (`read_file`/`write_file` path-allowlisted, `shell`
  allowlist + cwd-jail + side-effecting, `web_search` via Anthropic server-side
  with a **fixture fallback** for determinism), `mcp_tools.py` (`MCPToolset`,
  stdio); `examples/reconciliation/models.py` (ERP entities +
  `ReconciliationReport`), `erp_server.py`, `data/` fixtures.
- Build ERP logic as plain functions first (agent works via local `@tool`), then
  wrap in the MCP server — MCP stays cuttable.
- Proof — tests: `test_builtins` (path traversal denied; shell allowlist),
  `test_mcp` (spawn a tiny stdio MCP fixture server as a subprocess — no network;
  list/call tools; MCP error → error `tool_result`).

### Inc 6 — Reconciliation agent + eval suite E1–E9
- Files: `examples/reconciliation/agent.py`, `__main__.py`, `policy.json`; seed
  `data/` with ~6 POs/GRs and ~10 invoices carrying the 8 known discrepancies;
  `evals/run.py`, `cases.py`, `answer_key.json`.
- Proof: `make demo` → readable trace, `stop_reason=completed`, log path under
  `runs/`. `make evals` runs E1–E9 live **3×**, each score recorded
  (C-eval-nondeterminism). Cases assert on the final `ReconciliationReport` +
  gate events (e.g. E1 posts → `approval_requested` fires; E2 hidden per-unit
  overcharge → `price_variance` with correct `variance_usd`; E9 deny-on-resume →
  not posted).
- **DEMOABLE #4:** full primary agent, SAP-flavored, live.

### Inc 7 — Replay + committed recorded run (reviewer without key)
- Files: `providers/replay.py`, `agent.replay()`, `replay_tools` option;
  `evals/recorded/*.jsonl` committed; E10 keyless replay eval.
- Proof — tests: `test_replay` (keyless + networkless; divergence →
  `run_failed{where:"replay-divergence"}`; `replay_tools="recorded"` vs
  re-execute). Satisfies C2 (reviewers lacking a key).

### Inc 8 — Secondary agent, context window, docs
- Files: `examples/release_notes/` (≤20 lines, different tools + `output_schema`,
  no approval gate); wire `SlidingWindow` in `context.py`; README quickstart
  (fresh clone → first run < 5 min); `DEVELOPMENT.md` per-increment log.
- Proof — tests: `test_context` (window keeps system + task + recent N);
  secondary completes under FakeProvider with **zero** framework changes (FR-9).

### Stretch (only if the timebox allows; none blocks the core demo)
`agent.as_tool()` subagents (FR-S1) → context compaction (FR-S2) → skills
(FR-S3), each its own increment with its own tests.

---

## Main risks

1. **Timebox (highest).** Full scope exceeds ~4h. Mitigation: Inc 1–4 are the
   real core deliverable and demoable on built-in tools alone; Inc 5–8 layer on
   and are cut from the bottom, each cut recorded as a non-goal.
2. **`project()` is load-bearing.** The entire system reads state only from it;
   a bug here is systemic. Mitigation: it gets the heaviest unit coverage,
   including logs ending in `run_paused` and in `tool_started`-without-result.
3. **MCP (biggest single-feature risk).** Protocol/subprocess surface. Mitigation
   (per decision): local tools first, MCP as a cuttable wrapper in Inc 5.
4. **Eval non-determinism** (C-eval). Mitigation: live scoring 3×; replay evals
   are deterministic and keyless.
5. **web_search vs no-network tests** (C-websearch / NFR-3). Mitigation: live
   server-side search in the demo, fixture-backed for E6 and all CI.
6. **shell safety** (C-shell). Mitigation: allowlist + approval gate + cwd jail;
   explicitly not production-hardened.
7. **At-least-once tools on crash/resume** (C3). Mitigation: log `tool_started`;
   make ERP `post_invoice` idempotent by `invoice_id`.
8. **Anthropic message/tool-use mapping.** Isolated entirely in
   `providers/anthropic.py`; all loop/logic tests use `FakeProvider` so nothing
   core depends on the live wire format.

## Deviations from `spec/spec.md` to reconcile (same-commit updates)
- Package `minagent` (not `miniagent`); plan lives at `plan/plan.md` (not
  `plans/NN-*.md`); demo entry `python -m examples.reconciliation`; evals via
  `python -m evals.run`.
- **OpenAI-compatible adapter dropped** (interface-only per `intent.md`): update
  spec §4.5 and remove it from §15 Inc 7.
- **Added event type `output_rejected`** (Inc 4), not in spec §7.1 — it carries
  the structured-output validation error back into the conversation as a user
  message so retry-with-feedback stays in the log and replays faithfully. Spec
  §7.1 / §9 to be updated to list it.
- **MCP is 2.x** (Inc 5): the installed `mcp` is 2.3; the server uses
  `mcp.server.mcpserver.MCPServer` (FastMCP renamed) and tools raise `ToolError`
  so the reason reaches the agent. Spec §8 wording ("FastMCP") to be updated.
- **web_search is fixture-backed only** (Inc 5): deterministic/offline per
  C-websearch; live provider server-side search is not wired in this build.
- **Inc 6 live verification pending a key**: the reconciliation agent, `make
  demo`, and the E1-E9 eval suite are built and verified keyless (assembly over
  the real MCP server + scorer unit tests); `make demo` / `make evals` need
  `ANTHROPIC_API_KEY` and have not yet been run live. Recommendation mapping is
  fixed in the prompt + `answer_key.json` (qty_variance -> hold, duplicate ->
  block; resolves C-policy-ambiguity for this dataset).
- **Inc 7 recorded fixture is synthetic**: `evals/recorded/reconcile_INV-9002.jsonl`
  was captured keyless via `evals/record_fixture.py` (a scripted model over the
  real ERP MCP), since no key was available. The replay path is identical for a
  real capture; replace it with a `make demo` recording when a key is available.
  E10 (keyless replay of the committed run) lives in `tests/test_replay.py`, not
  `make evals` (which requires a key), so it runs in the normal `make test`.

## Verification (end to end)
- `make test` → ends with `N passed`, no failures (unit, no network/key).
- `make evals` → one PASS/FAIL per case, ends `evals: K/K passed` (needs
  `ANTHROPIC_API_KEY`; E10 replay case runs keyless).
- `make demo` → readable trace, `stop_reason=completed`, event-log path under
  `runs/`.
