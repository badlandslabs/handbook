# S-1801 · The Tool Definition Stack — When Your Agent Knows What to Do But Calls the Wrong Tool

Your agent has a perfect prompt, a frontier model, and the right tools available. It still calls `get_user_by_id` when it should call `get_user_by_email`. It passes a raw timestamp where it needed an ISO string. It picks `search_documents` over `search_knowledge_base` and then can't figure out why nothing relevant came back. The model isn't confused about the goal — it's confused about the interface.

You need to treat tool definitions as a first-class engineering surface, not a schema you write once and forget.

## Forces

- **Tool definitions are invisible context.** They occupy tokens in the model's context window, influence attention patterns, and shape every decision about what to do and how to do it. Most teams spend weeks iterating on system prompts while leaving tool schemas in whatever state they were at initial implementation.
- **Tool count compounds token overhead fast.** A single MCP server with 20 tools at ~500-1000 tokens each adds 10-20K tokens to every call. As agents scale to hundreds of tools across multiple servers, the overhead becomes a dominant cost and latency driver — before any tool is even called.
- **Descriptions serve two audiences simultaneously.** They must be human-readable enough for developers to debug, and LLM-readable enough for the model to disambiguate between similar tools without any runtime feedback.
- **Naming carries semantic weight the model acts on.** Verb-object patterns (`get_user`, `search_documents`) shape the model's tool-selection reasoning. Names that look correct to a developer can create subtle biases that push the model toward wrong choices in edge cases.

## The Move

Three concrete changes that move tool reliability from guesswork to engineering:

- **Write descriptions for disambiguation, not just identification.** The goal is not "what does this tool do" but "when do you use this instead of the similar tool." Describe the boundary cases: "Use `get_user_by_id` when you have the internal UUID; use `get_user_by_email` when you have an email address and need to discover the ID." This framing, described by Anthropic as part of "Writing effective tools for agents," dramatically reduces mis-selection in agents with many similar tools.
- **Name parameters for the model's world, not your database's.** A parameter named `user_id` forces the model to infer whether it wants a UUID, email, or integer. A parameter named `user_uuid: string` with description "Internal user identifier (36-char UUID format, e.g. `550e8400-e29b-41d4-a716-446655440000`)" removes inference entirely. Include format constraints and examples in every parameter description.
- **Filter tool loading by relevance, not by count.** Anthropic's "Code execution with MCP" (Nov 2025) describes how loading all available tool definitions upfront causes token bloat and degraded selection. The fix is on-demand loading: instead of passing all 50 tools, load only the 3-5 relevant to the current task. This requires either a routing layer or code-execution patterns where the agent writes code to call tools rather than the orchestrator passing all definitions.
- **Return structured error responses from tools, not raw strings.** When a tool fails, the model needs enough context to decide whether to retry with modified parameters or escalate. A tool returning `"Error"` forces the model to guess; one returning `{"error": "user_not_found", "query_used": "user_uuid", "tried_value": "john@example.com", "suggestion": "try user_email lookup if you have an email address"}` gives the model a recovery path.
- **Annotate tool intent for the MCP ecosystem.** The MCP 2025 spec introduced annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`) that let the protocol and orchestrators reason about tool safety. Use them — they allow safety guards and cost estimates to operate without relying on the model's own reasoning about side effects.

## Evidence

- **Anthropic Engineering (Dec 2024):** "Writing effective tools for agents" — documents the practice of using AI agents themselves to generate and iterate on tool descriptions. Found that tool descriptions and specs loaded into context collectively steer agents toward effective tool-calling behavior; treating descriptions as prompt-engineering artifacts rather than documentation was one of the highest-leverage improvements available. — [anthropic.com/engineering/writing-tools-for-agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

- **Anthropic Engineering (Nov 2025):** "Code execution with MCP" — describes token overhead from tool definitions as a production-scale problem. Example: 40 tools with ~800-token definitions each = 32K tokens added to every call, before any tool is called. Documents the on-demand loading pattern as the mitigation. Also notes that Anthropic donated MCP to the Agentic AI Foundation in 2025, signaling MCP's industry-standard status. — [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **HN Discussion on MCP as a Standard (2025):** Thread debating whether MCP is technically justified or primarily a community coordination mechanism. Key agreement across both skeptics and proponents: MCP's discoverability advantage is real — an AI client can introspect available tools without manual configuration. Counter-argument: OpenAPI specs can provide the same discoverability if formatted for LLMs. Consensus outcome: MCP wins on ecosystem velocity; OpenAPI wins on generality. For teams building agent tooling, the practical advice from the thread was to use MCP for its tooling ecosystem but keep tool definitions high-quality regardless of protocol. — [news.ycombinator.com/item?id=46208566](https://news.ycombinator.com/item?id=46208566)

## Gotchas

- **Adding more tools makes selection worse, not better.** A 10-tool agent with clear, disambiguated descriptions outperforms a 50-tool agent with generic ones. More tools with overlap require proportionally more description work to maintain selection quality.
- **Descriptions written by developers assume shared context the model doesn't have.** "Gets user data" tells the model nothing it couldn't infer from the name. "Returns the user's display name, email, and subscription tier from the auth service" tells the model what information is available and what domain this tool operates in.
- **Schema types are constraints the model respects, not hints it can ignore.** A parameter typed as `integer` will cause the model to reject strings at inference — but only if the tool validation is strict. If your tool wrapper accepts and coerces types silently, the model's reasoning about type correctness won't match the actual runtime behavior.
- **Tool descriptions are not static.** As your agent accumulates more tools, new additions can shift the selection landscape for existing tools. Re-review descriptions whenever a new tool overlaps with an existing one's domain.
