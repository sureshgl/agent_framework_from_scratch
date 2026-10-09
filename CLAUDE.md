# minagent

A minimal agent framework built from scratch. The source of truth for what to
build is `intent/intent.md` → `spec/spec.md` → `plan/plan.md`. Read them first.

## Layout
- `src/minagent/` – the framework (loop, tools, hooks/policy, events, providers)
- `examples/` – reconciliation agent (primary) and the ~20-line second agent
- `tests/` – unit tests (no network, no API key)
- `evals/` – agent evals: task → expected-outcome checks (real LLM)

## Commands
- Setup: `pip install -e ".[dev]"`
- Test: `make test`
  - Healthy output: ends with `N passed`. No failures, no errors.
- Evals: `make evals`
  - Needs `ANTHROPIC_API_KEY`.
  - Healthy output: one PASS/FAIL line per case, ending with `evals: K/K passed`.
- Demo: `make demo`
  - Runs the reconciliation agent end to end.
  - Healthy output: a readable trace, then `stop_reason=completed`, then the path to the event log under `runs/`.

## Conventions
- Python 3.11+. Use type hints everywhere.
- Use pydantic v2 for all schemas: tool arguments, events, and structured output.
- Allowed dependencies: `anthropic`, `mcp`, `pydantic`, and the standard library.
  - Ask before adding anything else.
- Never use any agent or orchestration framework. That includes the Claude Agent SDK, LangChain, LangGraph, LlamaIndex agents, and similar. This is a hard constraint of the assignment.
- Model calls go only through the `Provider` interface.
- Side effects go only through tools, which pass through the hook/policy layer.
- Every step emits a typed event. Never bypass the event log.
- Unit tests must not hit the network. Use a fake provider.
- Keep `plan/plan.md` in sync. If the implementation departs from it, update it in the same commit.

## Verifying your work
Run `make test` and `make evals` before reporting any task complete, and paste the output.

If a test or eval fails, fix the code, not the test. Never skip, weaken, or delete a failing test or eval case.