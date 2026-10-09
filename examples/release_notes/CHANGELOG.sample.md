# Changelog

## Unreleased
- Add `SlidingWindow` context strategy to bound long-run prompts.
- Add `Agent.replay()` for keyless, networkless re-runs of a recorded log.
- Mount MCP servers as tools via `MCPToolset`.
- BREAKING: `Agent(max_steps=...)` now seeds `budgets`; pass `budgets=Budgets(...)`
  for the full set (tokens, cost, wall-clock, tool calls).
- Fix: tool exceptions become error results instead of crashing the run.
