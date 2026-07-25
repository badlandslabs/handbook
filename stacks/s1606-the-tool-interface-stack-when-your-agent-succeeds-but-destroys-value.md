# S-1606 · The Tool Interface Stack — When Your Agent Succeeds but Destroys Value

The demo works. The agent calls the tool, gets the result, completes the task. In production, the same agent sends the same invoice email three times, charges the customer twice, and inserts a duplicate row into the database — all while returning HTTP 200 the entire time. No error logs. No alerts. The model "succeeded." Your system didn't.

The root cause is almost never the LLM. It is the tool interface — the schema, the failure handling, the side-effect boundaries, and the monitoring around how the agent interacts with external systems.

## Forces

- **Tool definitions get a fraction of the attention prompts do.** Teams spend weeks tuning system prompts but ship tool schemas as afterthoughts, then wonder why the agent passes wrong arguments or calls tools it shouldn't.
- **Non-idempotent tools and retry logic are incompatible.** Agents retry tool calls 15–30% of the time due to rate limits, timeouts, and transient errors. When retries hit non-idempotent operations (send email, charge card, write record), every retry is a potential duplicate side effect in production.
- **Loading all tool definitions upfront is a context tax.** MCP-scale deployments reach hundreds or thousands of tools across dozens of servers. Loading all definitions upfront burns token budget and degrades model tool-selection quality.
- **Rate limiters don't distinguish agents from attackers.** An agent making hundreds of requests per minute to an external API looks like a DoS attack to that API's infrastructure. The workflow silently stalls.
- **Schemas are written once and never revisited.** Tool behavior changes. API fields are renamed. The schema the agent was calibrated against diverges from reality — silently, without any test catching it.

## The move

Design tool interfaces as first-class contracts, not afterthoughts. Treat the tool schema like an API contract: version it, validate it, test it independently of the agent, and instrument it for production observability.

**Schema design**
- Name tools with verb-noun pairs that state the exact outcome: `send_invoice_email` not `email_tool`. The model's tool-selection quality depends on this more than on the description text.
- Write descriptions in the second person, imperative mood: "Retrieves the current weather for a specified city. Returns temperature, conditions, and humidity." not "This tool can be used to get weather information."
- Be explicit about preconditions and failure modes in the description — not just the happy path. If a tool requires authentication, returns partial results on some inputs, or has rate limits, say so.
- Use enums for constrained parameter values rather than free-text strings. The fewer degrees of freedom the model has with arguments, the more reliable the call.
- Design tools for single responsibility. A `search_and_update_record` tool is a trap — split it into `search_records` and `update_record` so each step is independently observable and retryable.

**Idempotency by default**
- Every tool that writes or transmits must accept an `idempotency_key` parameter. The tool implementation deduplicates on this key; the agent generates it (e.g., `sha256(task_id + action_name + timestamp_bucket)`).
- If a tool cannot be made idempotent, add an explicit `dry_run` mode that returns the planned action without executing it. Let the agent or a human approve before live execution.
- Never retry a non-idempotent tool call without a human-in-the-loop gate.

**On-demand tool loading**
- Instead of loading all MCP tool definitions into context at session start, load a manifest of available tools with minimal metadata (name, category, one-line description). Let the agent request full definitions for the tools it actually intends to use.
- Anthropic's MCP code execution pattern illustrates this: instead of the model calling `gdrive.getDocument(id, fields)` directly, the model writes code that calls the tool internally — collapsing multiple operations into one tool call and reducing per-call context overhead.
- Tier tools into "always loaded" (core actions), "on-demand" (peripheral), and "requires explicit approval" (high-stakes writes/transmits).

**Harness-layer guards (the part most teams skip)**
- Enforce a `max_steps_per_task` hard limit and a `no_progress_window` (stop if N consecutive steps produce no new artifacts or facts). These prevent infinite loops without requiring the model to self-correct.
- Track `repeated_tool_signature_rate` — if the same `tool+args` appears twice in one run, surface it. Repeated identical calls are almost always a loop, not a valid retry.
- Instrument every tool call with a trace: input args, output summary, duration, and error flag. Send these traces to a dedicated span store, not just logs. You cannot fix what you cannot see.

**Separation of workflow logic and tool implementation**
- Keep orchestration (when to call which tool, in what order, with what context) in the agent/harness layer. Keep tool implementation in the MCP server or equivalent. Don't embed business logic inside tool descriptions — that's coupling that will bite you on the next schema update.

## Evidence

- **Engineering post — Harness Engineering (Dr. Sarah Chen, March 2026):** "The first time you deploy an AI agent into production, it will fail in a way you did not anticipate. Not because the model generated a bad output. Not because your prompt was wrong. It will fail because the infrastructure wrapping the model—the harness—was not built to handle the edge cases that only appear under real load." — [Harness Engineering Blog](https://harness-engineering.ai/blog/lessons-learned-from-deploying-ai-agents-in-production)
- **Engineering post — Anthropic (2025):** "Direct tool calls consume context for each definition and result. Agents scale better by writing code to call tools instead. Here's how it works with MCP." — Demonstrates the code-execution-over-direct-call pattern for reducing per-tool context overhead. — [Anthropic Engineering](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Industry analysis — AgentMarketCap (April 2026):** "LLM API calls fail 1–5% of the time due to rate limits, timeouts, and transient server errors. More critically, agents retry tool calls 15–30% of the time — and without the right guards, every retry is a potential duplicate side-effect detonating in your production systems." — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/11/tool-call-reliability-patterns-production-agents-2026)
- **arXiv — Production-Grade Agentic AI Workflows (Bandara et al., 2025):** Nine best practices including tool-over-MCP design, pure-function invocation, single-responsibility agents, externalized prompt management, and separation of workflow logic from MCP servers. — [arXiv:2512.08769](https://arxiv.org/html/2512.08769v1)
- **Primary pattern — FailureModes.ai:** Infinite loop detection via `steps_per_task`, `repeated_tool_signature_rate`, and `no_progress_steps` metrics. "A long run does not always mean a loop. The key question: does a new useful signal appear." — [FailureModes.ai](https://www.agentpatterns.tech/en/failures/infinite-loop)

## Gotchas

- **Adding a tool is not the same as integrating it safely.** A tool that can send email or mutate data needs idempotency keys, dry-run modes, and explicit approval gates before it goes live. Adding it to the agent's tool list is the beginning of integration, not the end.
- **Tool descriptions drift from reality.** The schema you shipped in January describes the tool as it was then. APIs change. Fields are renamed. The agent's learned association between description and behavior becomes incorrect. Treat tool schemas as versioned, tested, and reviewed artifacts.
- **Context window pressure from tools scales with MCP server count.** A naive MCP client that loads all tool definitions for all servers at startup can consume 30–50% of the context window before the agent does anything useful. Lazy loading isn't a micro-optimization — it's what makes larger multi-server deployments viable at all.
- **Silent semantic failures are harder to detect than errors.** The agent that sends three emails, charges twice, and inserts a duplicate row returned HTTP 200 every time. Your error rate dashboard shows green. You need semantic monitoring — did the right thing happen, not just: did the tool execute without throwing.
