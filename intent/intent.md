# Intent: Minimal agent framework from scratch

Author: Suresh GL. Status: draft. Date: 2026-10-09.
Source: take-home assignment from SAP Labs India, Office of the CTO (Mahesh Palavalli).
Due: Monday 2026-10-12.
Repo: https://github.com/sureshgl/agent_framework_from_scratch

## Problem

SAP wants to evaluate:

- architectural thinking,
- design choices,
- awareness of current and emerging agentic patterns,
- how coherently a set of capabilities fits together.

The evaluation is based on a small agent framework built from scratch with a coding agent. Code volume matters less than the rationale and the coherence of the choices.

Most "minimal agent frameworks" are a prompt loop with tools attached. They don't show where control, safety, and observability live. The opportunity here is to show an agent treated as a runtime, with explicit contracts, rather than as a prompt.

## Proposed outcome

The deliverable is a small Python framework in which another developer can define and run an agent in a few lines. The design rests on one organizing idea:

> **The agent run is an explicit, inspectable runtime.** Every model call and tool call flows through a single lifecycle and a single policy layer, and every step is recorded as a typed event. The system enforces control (budgets, permissions, human approval) deterministically, outside the model. It does not ask the model to comply.

Each capability below is a consequence of that idea, not an item on a checklist.

### Core capabilities (must have)

1. **Agent loop with explicit budgets and stop reasons.**
   - Budgets cover turns, tokens, cost, and wall-clock time.
   - Every run ends with a named reason: completed, budget exhausted, denied, or error.
2. **Typed tools.**
   - Tools are plain Python functions. Their schemas are derived from type hints.
   - Arguments are validated before execution.
   - **MCP client** support lets external MCP servers be mounted as tools.
3. **Lifecycle hooks and a policy layer.**
   - Hooks run before and after each model call and each tool call. Each hook returns allow, ask, or deny.
   - **Human-in-the-loop approval** is required for side-effecting actions.
   - This is the governance story.
4. **Event log and tracing.**
   - Each run is an append-only JSONL log of typed events.
   - The log provides an audit trail and can be rendered as a readable trace.
   - Runs can be **replayed** from the log without calling the LLM.
5. **Structured output.**
   - The final answer is validated against a declared schema.
   - On validation failure, the framework retries with feedback.

### Stretch (if time permits, in this order)

6. **Subagents as tools.** A delegated agent runs with an isolated context and its own tool and permission scope.
7. **Context compaction.** The conversation is summarized when it approaches the context budget.
8. **Skills.** Instructions are loaded on demand, using progressive disclosure.

### Example agents

- **Primary: Invoice / PO reconciliation agent (SAP-flavored).**
  - It performs a three-way match of purchase orders, goods receipts, and supplier invoices over mock ERP data.
  - Its tools are:
    - mock ERP data exposed through a **local MCP server**,
    - **filesystem** access for documents,
    - **web search** for vendor verification,
    - a **shell** tool for calculations and exports.
  - It produces a structured reconciliation report.
  - Any posting or blocking action pauses for human approval.
- **Secondary: A second agent defined in about 20 lines.** It reuses the framework with different tools and a different output schema, to prove the framework is reusable.

## Affected users and systems

- **Reviewers.** owner reading the repo in a short review.
- **Framework users.** A developer defining a new agent.
- **External systems.** The Anthropic API (model and server-side web search), a local MCP server, the local filesystem, and a shell.

## Success criteria

- A reviewer can clone the repo, set `ANTHROPIC_API_KEY`, and run one command. The reconciliation agent then completes end to end against the real LLM and produces a readable trace.
- The second agent runs with no changes to the framework.
- A small unit test suite passes.
- A handful of **agent evals** pass. Each eval checks a task against its expected outcome, for example that the mismatched invoice is flagged and the approval gate fired.
- A captured end-to-end run, with its event log and trace, is committed.
- The SDLC artifact chain is committed and readable in order: `intent.md` → `spec.md` → `plan.md` → code → evals.

## Constraints

- **Language:** Python.
- **LLM:** Anthropic API through the plain `anthropic` SDK. The model sits behind a thin provider interface so other providers can be added later.
- **Allowed libraries:** general-purpose libraries and the official MCP Python SDK (it is a protocol library). pydantic is used for schemas.
- **Not allowed:** any agent or orchestration framework, including the Claude Agent SDK and LangChain/LangGraph-style libraries.
- **Effort:** Comprehensive testing, CI/CD, and production hardening are not expected.
- **Process:** the development approach itself is a deliverable. The repo must describe how the coding agent was used, how the solution evolved, and how it was validated, and must name the coding agent.

## Out of scope

- Breadth across multiple providers. The interface exists, but only Anthropic is implemented.
- Any UI.
- Persistence beyond local files.
- A2A, durable execution, and distributed runs. These are discussed in the docs as next steps, not implemented.
- Production security hardening of the shell tool, beyond the approval gate and an allowlist.

## Open questions

