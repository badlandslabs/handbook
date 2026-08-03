# S-2089 · The Tool Surface Stack — When Your Agent Can't Decide What to Reach For

Your agent has access to 12 MCP servers, 400+ tools, and the full weight of your infrastructure. It chooses none of them correctly. It hallucinates an API response instead. It picks a tool that technically fits but functionally breaks. It calls the wrong parameters and corrupts your data. That's not a model quality problem. That's a tool design problem — and it has a known fix.

## Forces

- **More tools means more token overhead.** Each tool definition burns context before the prompt even starts. One developer reported MCP tools consuming 833,000 tokens — 41.6% of a 2M context window. The agent spends its context budget on tool menus, not reasoning.
- **Selection noise scales with tool count.** Action selection is part of LLM inference. Give the model 50 tools and it picks the marginally-wrong one more often than it picks correctly. Performance degrades in a non-obvious way — it doesn't fail loudly, it just drifts.
- **MCP surfaces a new security attack surface.** Traditional "model asks you to run" had a human in the loop. MCP lets the model discover and call tools autonomously. An over-privileged MCP server means an agent can read any file, edit code, or push to production — and a malicious tool description can embed hidden payloads that the client trusts.
- **The execution gap kills agents in production.** MCP standardizes the control plane (how agents discover and invoke tools) but provides no execution layer. When a real user asks for something outside a pre-defined tool — normalize dates across three CSVs, compute a weighted average, write a report — the agent stalls. Copilots work because they never reach this edge. Autonomous agents hit it constantly.
- **Tool descriptions are the API contract with a non-deterministic client.** Traditional APIs are read by developers who understand context. Tool APIs are read by language models that must infer intent, deduce parameters, and generate calls from natural language. If a human engineer can't definitively say which tool to use in a situation, the agent cannot be expected to do better.

## The move

### 1. Curbate tool exposure — show only what's needed per task

Never expose the full tool inventory upfront. Implement tool routing that shows the agent only the minimal set relevant to the current goal. This reduces token overhead, cuts selection noise, and makes debugging tractable.

The "essential trinity" consensus from r/ClaudeAI, r/cursor, and r/mcp: Context7 (real-time library docs), Sequential Thinking (step-by-step reasoning), and Filesystem — cover 95% of general use cases. Add domain tools (GitHub, Snowflake, Slack) only when the agent enters that context.

### 2. One tool, one responsibility — no action parameters

Each tool should represent a single, unambiguous operation. Multi-action tools that dispatch via an `action` parameter force the model to figure out which mode to invoke before solving the actual task. Split them. A human engineer who can't say which tool applies in a given situation is a sign the boundary is wrong.

Every tool description must answer four questions in the schema itself: What does it do? When should it be used? What inputs does it accept? What does it return? Don't rely on the system prompt to compensate for vague descriptions.

### 3. Execute code inside the agent, not through tool calls

Per Anthropic's Nov 2025 engineering post, the recommended pattern for agents at scale is to load MCP servers as code APIs — not as discrete tool calls — and process data inside a code execution environment before returning results to the model. This can reduce context overhead by up to 98.7% compared to passing intermediate results through the context window.

The pattern: agent writes code (Python, JavaScript) that calls MCP tools internally, runs the code in a sandbox, and returns only the final processed result. This fills the execution gap — the agent can handle novel, multi-step data tasks without stalling.

### 4. Sandbox aggressively — treat MCP as untrusted input

MCP servers are a primary attack surface. The MCP specification explicitly notes that tool behavior descriptions must be treated as untrusted unless sourced from verified servers. Malicious tool descriptions can embed hidden payloads.

Safeguards: read-only mounts for sensitive directories, network isolation for untrusted code execution, fresh containers or disposable VMs for god-mode tasks, permission annotations ("read-only" vs "destructive") requiring user confirmation, and internal-first policy (Block, with thousands of daily MCP agent users, requires all MCP servers used internally to be authored by their own engineers).

### 5. Use a tool registry with discovery, not a flat list

As MCP server counts grow, a registry layer lets agents query what tools exist and what they do, rather than receiving all definitions at once. This maps to Anthropic's code-execution pattern: the agent asks the registry "what can access my Snowflake instance?" rather than being handed all 400 tools.

## Evidence

- **Enterprise deployment (Block/Goose):** Block's open-source MCP-compatible agent Goose serves thousands of daily users company-wide. Most employees report saving 50–75% of their time on common tasks; work that took days is completed in hours. Their most-used MCPs: Snowflake (data queries), GitHub/Jira (dev workflows), Slack/Google Drive (coordination). All internal servers are internally authored for security. — [goose-docs.ai](https://goose-docs.ai/blog/2025/04/21/mcp-in-enterprise/)
- **Token efficiency benchmark (Anthropic):** Anthropic's engineering team demonstrated that presenting MCP servers as code APIs rather than direct tool calls reduces context overhead by up to 98.7%. Loading all tool definitions upfront causes the majority of context to be consumed by tool metadata — not the task itself. — [anthropic.com/engineering](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Security taxonomy (Palo Alto Networks / QCode.cc):** MCP shifts the trust model from "human approves" to "model executes autonomously." Over-privileged MCP servers allow agents to access files, edit code, or push to production without human review. The MCP spec explicitly marks tool descriptions as untrusted input. — [qcode.cc](https://qcode.cc/en/mcp-security-sandboxing-guide) and [live.paloaltonetworks.com](https://live.paloaltonetworks.com/t5/community-blogs/mcp-security-exposed-what-you-need-to-know-now/ba-p/1227143)
- **Tool selection anti-pattern (AgentPatterns.tech):** Empirical observation across multiple agent deployments: action selection degrades predictably with tool count. Above ~15 tools, selection noise dominates — agents pick formally-correct but contextually-wrong tools more often than they pick correctly. — [agentpatterns.tech](https://www.agentpatterns.tech/en/anti-patterns/too-many-tools)
- **Community consensus (Reddit / awesome-mcp-servers):** Developer analysis of 1,000+ Reddit comments across r/ClaudeAI, r/cursor, and r/mcp identifies a clear "essential trinity" of MCP servers (Context7, Sequential Thinking, Filesystem) plus domain-specific additions. One developer reported 833,000 tokens consumed by MCP tool definitions in a single 2M context session. — [hireblackout/awesome-mcp-servers](https://github.com/hireblackout/awesome-mcp-servers)
- **Execution gap case (Blaxel.ai):** An agent that queries a database, summarizes results, and sends a Slack notification works in demos. A real user asking to normalize date formats across three CSVs, compute a weighted average, and merge the output into a report stalls — no predefined tool matches. This gap between MCP's control plane and real execution is the primary failure mode for enterprise agent deployments. — [blaxel.ai](https://blaxel.ai/blog/code-execution-with-mcp)

## Gotchas

- **Vague descriptions break even strong models.** No amount of prompt engineering fixes a tool description that doesn't clearly state what the tool does, when to use it, what it accepts, and what it returns. Fix the schema, not the prompt.
- **Tool proliferation is a silent tax.** 50 tools don't cost 5x more than 10 — they cost 10x more in context, latency, and selection error. Monitor token consumption per session and cap tool definitions actively.
- **Code execution sandboxes add latency.** The execution-gap pattern (agent writes code that calls tools internally) is powerful but introduces async overhead. Profile before committing; for latency-sensitive paths, pre-built tools remain faster.
- **MCP security is not opt-in — it's opt-out.** Every MCP server in your chain is a potential payload vector. Default-deny permissions, read-only annotations, and internal-first server authoring are not paranoid — they're the baseline for production.
- **Sequential Thinking tools can double your token consumption.** Each reasoning step is a separate LLM call. Use them selectively for genuinely complex multi-step tasks, not for one-hop lookups.
