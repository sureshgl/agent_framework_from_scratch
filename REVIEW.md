# Review instructions

Run three passes and tag each finding with its pass:
- **Bugs:** logic errors, broken edge cases, regressions.
- **Safety:** tool calls that bypass policy, side effects without approval,
  secrets in logs, path traversal in file tools.
- **Compliance:** the diff matches `intent/spec.md` and the increment's
  `plans/NN-*.md`; the log-is-source-of-truth invariant holds; anything
  done that the plan did not ask for is flagged.

## What Important means here
Reserve Important for findings that break behaviour, violate the spec's
invariant, or bypass policy. Style and naming are nits.

## Cap the nits
At most five nits per review; summarise the rest as a count.

## Do not report
Formatting the linter would catch; anything under `spike/` branches.
