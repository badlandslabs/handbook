# S-1876 · The Tool Definition Stack — When Your Agent Knows What to Do But Not How to Do It Right

Your agent has a `search_database` tool. It has a description. It has parameters. And yet the agent calls it with the wrong table name, passes `{"limit": "five"}` instead of `{"limit": 5}`, and retries the same failed query three times without changing anything. The model is not broken. The interface is. Tool definition — not model size, not prompt length, not orchestration complexity — is the root cause of most agent failures in production.

## Forces

- **A model can only reason from the interface it is given.** A tool's name, description, parameter schema, and error messages are the only information the model has to decide when to call it, how to format arguments, and how to recover from failure. Stronger models cannot compensate for a flawed interface — they just fail more confidently.
- **Token pressure makes definition quality load-bearing.** Modern agents run dozens to hundreds of tools via MCP. Loading all tool definitions into context consumes tokens proportionally to tool count, degrading both performance and cost. Well-scoped, well-described tools reduce the definition surface faster than any caching strategy.
- **The taxonomy problem blocks shared tooling.** NIST's AISIC consortium (August 2025) gathered ~140 experts and found that no comprehensive taxonomy of agent tools exists — which means no shared vocabulary for comparing, debugging, or governing tool sets across teams or vendors.
- **The code-execution shift changes where the interface lives.** Anthropic's November 2025 engineering post introduced a pattern where agents write code to call tools rather than calling tools directly — effectively adding a layer between the model and the tool surface that must itself be designed.

## The move

**Atomic, well-described tools with structured error outputs — and let the tool do the work, not the model.**

- **One tool, one verb.** Each tool should do exactly one thing. Split `search_and_filter_database` into `search_database` and `filter_results`. Multi-behavior tools with `action` parameters force the model to first decide which mode to invoke before it can reason about the actual goal.
- **Name tools imperatively, in snake_case.** `get_customer_orders`, not `CustomerOrderSearch` or `customer_orders`. Verbs signal action; snake_case matches JSON conventions the model already understands from its training.
- **Write tool descriptions as if for a new employee, not a spec sheet.** The first sentence should state what the tool does in plain language. The rest should cover edge cases, output shape, and what "success" looks like — not just the parameter list. Descriptions drive tool selection; parameter docs drive correct usage.
- **Schema parameters tightly, not permissively.** Use specific types (`integer`, `enum`) over `string` wherever the domain allows. For fields with known valid values, use `enum` so the model cannot invent an invalid option. For free-text fields, provide examples via `description`.
- **Return structured errors, not raw exceptions.** A `KeyError` traceback in an LLM's context window gives it nothing actionable. Return `{"error": "not_found", "message": "Order ID 12345 does not exist", "hint": "Verify the order ID format (8 digits)"}` — a structure the model can reason about and respond to correctly.
- **Prefer tool recommendations over direct calls in high-volume scenarios.** Anthropic's MCP code-execution pattern has the agent write a Python script that imports and calls tools, rather than issuing tool calls directly. This amortizes token cost across execution and moves parameter validation into code, not context. One tool call definition now serves many invocations with minimal per-call token overhead.
- **Self-describe tool output when it is non-obvious.** If a tool returns a format the model won't naturally interpret — a raw binary, a paginated cursor, a nested dict with implicit conventions — prepend or append a brief description of the output structure.

## Evidence

- **NIST AISIC Workshop (August 2025):** ~140 experts from industry, academia, and government identified the absence of a comprehensive agent tool taxonomy as a foundational gap. Seven taxonomy approaches were discussed (functionality-focused, access-pattern-based, risk-based, environment-based, action-modality-based, capability-based, and resource-based), but no consensus emerged. The consortium concluded this gap impedes tool sharing, security evaluation, and governance across the agent supply chain. — [NIST AISIC News](https://www.nist.gov/news-events/news/2025/08/lessons-learned-consortium-tool-use-agent-systems)
- **Anthropic Engineering: Code Execution with MCP (November 2025):** Anthropic documented two token-cost anti-patterns as MCP scales: (1) loading all tool definitions into context causes linear token growth, and (2) direct tool calls consume context for each definition and result. Their recommended pattern shifts agents to write code that calls tools — amortizing definition cost and moving argument validation into deterministic execution rather than model reasoning. — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Machine Learning Mastery (June 2026):** A practitioner's analysis of 28 production agent failures found that tool design — not model capability, not prompt quality, not orchestration choice — was the primary failure mode in 19 of 28 cases. Root causes included underspecified schemas, ambiguous naming, unstructured error outputs, and multi-behavior tools that conflated distinct operations. — [Machine Learning Mastery](https://machinelearningmastery.com/ai-agent-tool-design-what-works-and-what-doesnt/)

## Gotchas

- **Underspecified schemas produce plausible-wrong arguments.** If a parameter accepts any string, the model will pass a string — sometimes formatted as a date, sometimes as a date-plus-time, sometimes as a Unix timestamp. Lock the type, lock the format.
- **Descriptions drift out of sync with implementation.** A tool that once returned IDs starts returning full objects. The schema says `string`, the implementation says `object`. The model sees the schema and fails. Treat tool descriptions as code: review them in the same PR that changes the tool.
- **Loading all tools blinds the model to what matters.** An agent with 50 tools in context has to reason through all 50 to pick one. Contextual tool loading — providing only the relevant subset for the current step — is more effective than a longer, more complete tool list. Anthropic's code-execution pattern and MCP's tool recommendation features both address this.
- **Error messages that apologize waste context.** `"I apologize, but I encountered an error"` tells the model nothing it can act on. Error messages should state what happened, what the constraints are, and what the model should try next.
