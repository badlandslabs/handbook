# S-833 · The Tool-Validation Stack — When Agents Call the Right Tool with the Wrong Arguments

Agents reliably pick the right tool name. They reliably hallucinate the arguments. A database query with a non-existent table ID, a payment call with an invalid enum value, a search API with a malformed date range — the agent sails through tool selection and crashes on execution. Tool parameter validation is the pattern that closes this gap.

## Forces

- **LLMs are better at intent than specifics.** Tool selection maps to semantic understanding; parameter construction requires exact knowledge the model may not have.
- **Fabricated parameters are syntactically valid.** The JSON parses cleanly, the API call succeeds in structure, and the error arrives from the downstream service as a semantic rejection — not a validation failure the agent can self-correct.
- **Schema drift is silent.** When an API adds a required field or renames an enum value, a tool-definition that's missing the update causes the agent to guess — and guess wrong — without any error at the schema level.
- **Generic validation catches the wrong thing.** A length check on a user ID field doesn't tell you whether that ID exists. Agents learn to satisfy the format and still call non-existent resources.
- **No-look tool calling compounds cost.** Agents that skip tool-output reflection (S-832) produce more malformed calls because there's no pause to evaluate whether the output looks reasonable before proceeding.

## The move

Validate tool parameters at two layers: **schema enforcement** before the call, **semantic verification** after.

**Layer 1 — Schema enforcement (gate before the tool fires):**
- Define tool parameters with strict types: enums over strings, integers over floats where floats aren't valid, ISO 8601 date constraints, UUID format validation.
- Use Pydantic models (Python) or Zod schemas (TypeScript) as the canonical tool definition. These aren't just documentation — they're the validation layer. The framework rejects calls that don't satisfy the schema before they reach the API.
- Auto-generate tool schemas from API specs (OpenAPI/Swagger) rather than hand-writing descriptions. This keeps schema and implementation in sync and removes the manual description as a drift source.
- Flag enum fields explicitly: list every valid value in the schema, not "a valid status." The agent must see the full set.

**Layer 2 — Semantic verification (check the response plausibility):**
- After any tool call that returns a resource (get_user, fetch_order), verify the returned ID or key matches the one requested. A mismatch means the call resolved to a default or fallback, and the agent should know.
- For database or search tool calls, verify the result set size against expected bounds. Zero results on a query that should match suggests the parameters were wrong, not that nothing exists.
- Add a lightweight "dry-run" mode to destructive or expensive tools (delete, payment, send). Return what would happen without executing. Let the agent evaluate plausibility before committing.

**Layer 3 — Feedback loops:**
- When a tool call returns an error, feed the error message back to the agent with a directive to retry or adjust. Don't just surface the error — tell the agent what class of error it is (auth, validation, not-found, rate-limit) so it can adapt.
- Track parameter error rates per tool. A tool with a >5% parameter-error rate needs schema review — either the schema is unclear, the agent doesn't have enough context to construct valid args, or the API behavior has drifted.

## Evidence

- **Engineering blog:** An Asynq.ai candidate evaluation agent hallucinated tool parameters — calling APIs with IDs that didn't exist in the system. The agent had selected the right tools but constructed parameters from thin air. The fix required adding strict schema validation at the tool boundary, not improving the prompt. — [Agentic AI in Production: Error Recovery, Observability, and Scaling Patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns) (March 2026)
- **Engineering blog:** A Modelia.ai image generation pipeline agent approved obviously flawed outputs because it optimized for task completion over quality — a parameter-refinement failure where the approval threshold was never enforced as a hard constraint. The agent chose a low-effort interpretation of the quality parameter rather than escalating. — [same source](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Research survey:** Zylos Research's 2025 production failure analysis categorizes "semantic failures" as a distinct failure class: syntactically valid tool calls with logically wrong parameters. Notes that traditional exception handling doesn't catch these — they require semantic validation of the parameter-to-outcome relationship. — [Agent Workflow Orchestration Patterns: DAG, Event-Driven, and Actor Models](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/) (April 2026)
- **Framework pattern:** Microsoft Semantic Kernel enforces tool parameter types via native schema generation from C# method signatures, catching type mismatches before the LLM sees them. The framework also supports pre-execution validation hooks. — [Microsoft Agent Framework: Building Production-Ready AI Agents](https://medium.com/@LakshmiNarayana_U/microsoft-agent-framework-building-production-ready-ai-agents-bc1c0268e56d) (October 2025)
- **HN discussion:** OpenSwarm (multi-agent Claude CLI orchestrator) uses a Worker/Reviewer pipeline where the Reviewer validates tool call outputs before the Worker proceeds — a human-in-the-loop validation step at the agent boundary. — [Show HN: OpenSwarm](https://news.ycombinator.com/item?id=47160980) (HN, 2025)

## Gotchas

- **Schema validation catches format, not meaning.** A tool that takes a `user_id` field will happily accept `user_id="xxxx-xxxx-xxxx"` even if that ID doesn't exist. Always pair structural validation with existence checks on returned resources.
- **Overly strict schemas cause agent loops.** If the schema rejects parameters too aggressively, the agent retries with small variations that also fail — creating the same loop trap the validation was meant to prevent. Add retry-count limits and error-class routing to break the cycle.
- **Tool descriptions are not schemas.** Many frameworks let you describe parameters in free text. This is documentation, not enforcement. The agent reads it but isn't constrained by it. Use typed schemas, not descriptions.
- **API changes break agents silently.** When an upstream API adds a required field, the LLM-generated parameter set won't include it. Version your tool schemas and run regression tests when the API changes — not just when you update the agent.
- **Dry-run modes add latency.** A pre-flight check before every destructive call doubles the round-trip. Budget this in your latency budget, or limit dry-run to calls above a cost/confidence threshold.
