# Development log

Coding agents: Claude (claude.ai, Claude Opus 5.5) for planning and design;
Claude Code for implementation. *(Update if this changes.)*

Process: AI-native SDLC playbook. Each increment commits an artifact that
the next one reads: intent → spec → plan → PR with review.

## Before increment 0: exploratory spike
An end-to-end spike was generated in a claude.ai session to test whether
the event-log design holds up. It lives on branch `spike` as reference
only. The work on `main` is rebuilt incrementally from the spec below.

## Increment 0: intent and design (YYYY-MM-DD)
- Brainstormed the assignment with Claude in claude.ai: identified the
  unstated requirements (dependency boundary, reviewer keys, what
  "validated" means, timebox) and compared an existing from-scratch
  framework to choose a different organising principle.
- Claude drafted `intent/intent.md`; I corrected: *(fill in)*.
- Claude drafted `intent/spec.md` from the intent; decisions on flagged
  concerns: *(fill in C1–C8 outcomes)*.
- Added `CLAUDE.md`, `REVIEW.md` and the plan template.

<!-- Copy this block for each increment:
## Increment N: <name> (YYYY-MM-DD)
- Plan: plans/NN-<name>.md (revisions: ...)
- What I asked Claude Code for:
- What it got wrong / what I corrected:
- Verification (commands + results):
- PR: #
-->
