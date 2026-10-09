# Development log

How this project was built, as a deliverable in its own right (FR-6).

**Coding agents.** Planning and design were done with Claude via claude.ai. The
implementation was done with **Claude Code** (model `claude-opus-4-8`), driven
increment by increment against the plan. Each increment is a commit on its own
branch, verified with `make test` before being called done.

**Process.** AI-native SDLC: each artifact is read by the next —
`intent/intent.md` → `spec/spec.md` → `plan/plan.md` → code, with `REVIEW.md` as
the review policy. The drive loop reads state only from the event log; that
invariant was the design constraint everything else followed.

## Before increment 0: exploratory spike
A throwaway spike explored whether the event-log design holds up. It lives on the
`spike` branch as reference only; `main` was rebuilt incrementally from the spec.

## Increment 0: intent, spec, plan (2026-10-09)
- Wrote `intent/intent.md` (the assignment and its unstated constraints) and
  `spec/spec.md` (requirements, interfaces, lifecycle, policy, event schema,
  replay, MCP, the two examples, eval cases, and flagged concerns C-*).
- Key decisions: providers = interface + Anthropic + Replay only (no OpenAI
  adapter, per intent); MCP built local-first so it stays off the critical path.
- Produced `plan/plan.md` (8 increments, core before stretch).

## Increment 1: foundations (`inc-01-foundations`)
- Built `events.py` (Event/EventLog, JSONL append + fsync), neutral
  `messages.py`/`provider.py`, `tools.py` (`@tool` schema from hints), `state.py`
  (`project()`), a minimal `loop.py`, `agent.py`, the Anthropic adapter, and a
  console tracer.
- Verification: `make test` → 16 passed (keyless, via a scripted fake provider).

## Increment 2: budgets & log-as-source-of-truth (`inc-02`)
- `budgets.py` with steps/tokens/cost/wall-clock/tool-call limits; wired into the
  loop; `RunResult` derived from the terminal event.
- Deviation: `Budgets` lives in its own module, not `policy.py`.
- Verification: `make test` → 24 passed, incl. an NFR-5 test that re-derives the
  result from the reloaded log alone.

## Increment 3: policy, hooks, approvals, pause/resume (`inc-03`)
- `policy.py` (glob allow/ask/deny, fail-closed, side-effecting floor),
  `hooks.py` (four fire points), approval + durable pause/resume in the loop and
  `Agent.resume()`.
- Verification: `make test` → 37 passed, incl. pause → reload-in-a-fresh-Agent →
  resume to completion.

## Increment 4: structured output + retry-with-feedback (`inc-04`)
- `output.py` (schema guidance, JSON extraction, validation); a new
  `output_rejected` event feeds the validation error back to the model.
- Deviation: `output_rejected` is not in spec §7.1; recorded in the plan.
- Verification: `make test` → 44 passed. This completes the core framework.

## Increment 5: built-in tools, MCP, ERP server (`inc-05`)
- `builtins.py` (file/shell/web_search factories), `mcp_tools.py` (`MCPToolset`,
  async-bridged stdio), and the ERP example (models, seeded data, MCP server).
- Correction: the installed `mcp` is **2.x** — `FastMCP` is now `MCPServer`, and
  tools must raise `ToolError` for the reason to reach the client (generic
  exceptions are masked). Adjusted the server accordingly.
- Verification: `make test` → 54 passed, incl. MCP tests against the real ERP
  server subprocess.

## Increment 6: reconciliation agent, demo, evals (`inc-06`)
- Assembled the primary agent (ERP-over-MCP + report schema + approval policy),
  `make demo`, and the E1–E9 eval suite with a pure scorer.
- Correction: tests needed `pythonpath = ["."]` to import `examples`/`evals`.
- Verification: `make test` → 57 passed.
- Live validation (later, once a key was available): `make demo` runs end to end;
  `make evals` scored **9/9 in each of 3 rounds**. The live run exposed and fixed:
  (1) Anthropic rejects dotted tool names, so the MCP namespace separator is now
  `__` (e.g. `erp__read_po`); (2) the duplicate pair was symmetric, so the prompt
  now treats the earliest-by-date invoice as the original (E1 posts, E5 blocks);
  (3) a duplicate's `three_way_match` is ambiguous, so E5 no longer asserts it.

## Increment 7: replay & committed recorded run (`inc-07`)
- `ReplayProvider` + `Agent.replay()` (reexecute vs recorded tools), divergence
  detection, and a committed recording for the keyless reviewer path (C2).
- Correction: the E10 replay agent needs `output_schema` set so the recorded
  final answer re-parses into a typed report.
- The committed recording is a genuine live `make demo` capture of the INV-9002
  reconciliation; `evals/record_fixture.py` remains as a keyless fallback
  regenerator.
- Verification: `make test` → 61 passed; E10 replays the live capture keyless.

## Increment 8: secondary agent, context window, docs (`inc-08`)
- `context.py` (`FullHistory`, `SlidingWindow`) wired into the loop; the
  `release_notes` secondary agent (~20 lines, no framework changes, FR-9); README
  quickstart and this log.
- Verification: `make test` → 68 passed.

## Flagged-concern outcomes
- C1 (MCP): included, local-first; stdio only. C2 (reviewer without key): replay
  + committed recording. C3 (at-least-once): `tool_started` logged; ERP
  `post_invoice` idempotent. C4 (eval non-determinism): `make evals` runs 3
  rounds, each reported. C5 (policy ambiguity): block the whole invoice; mapping
  fixed in the prompt + answer key. C6 (model name): `MINAGENT_MODEL`. C7
  (timebox): core (Inc 1–4) first; examples/hardening after. C8 (spike):
  reference only.
