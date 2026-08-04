# S-2137 · The Tool Cardinality Stack

You have five tools and the agent uses them well. You add ten more. Still fine. You hit 50 and the agent starts hallucinating tool calls. You hit 100 and Perplexity's CTO publicly abandoned the approach. Tool cardinality — how many tools an agent can reliably use — is not a scale problem. It is a fundamental design boundary that most teams discover too late.

## Forces

- **Context is finite and expensive.** Every tool schema, description, and output passes through the context window. Five tools = ~15K tokens overhead. Perplexity measured tool schemas consuming up to 72% of available context at scale — leaving almost nothing for actual reasoning.
- **Tool breadth and tool depth trade off.** More tools means broader capability coverage. Fewer tools means the agent masters each one. Teams optimize for breadth first and pay for it in reliability.
- **The execution gap.** MCP standardizes *how* agents call tools but not *what happens* when no tool fits the task. Real user requests — normalize three inconsistent CSVs, compute a weighted average, merge into a report — fall outside every predefined tool. The agent stalls.
- **Security surface grows with every tool.** Each tool is a data exfiltration vector. The easier it is to write an MCP server, the easier it is to ship one with a credential-leakage loophole.
- **The "write your own" backlash.** Hacker News debate (145 points, 117 comments, ~Feb 2026) argued modern LLMs write better task-specific glue code than MCP servers provide — making the overhead unjustifiable.

## The Move

### 1. Categorize tools by execution mode, not capability

Separate tools into two classes before adding another:

- **Routed tools** (MCP-pattern): defined schema → model emits call → server executes → result returned. Use when the action is well-defined, deterministic, and the schema is stable. File read/write, API calls, database queries, Slack posts.
- **Sandbox tools** (code-execution-pattern): agent writes code that calls routed tools or does ad-hoc computation. Use when the task has combinatorial variety — data transforms, multi-file operations, dynamic queries that can't be pre-tooled.

Anthropic's engineering blog (Nov 2025) frames this explicitly: agents scale better by writing code to call tools instead of calling tools directly. The agent becomes a *programmer* of its own toolset rather than a *consumer* of a fixed one.

### 2. Cap routed tool count at the session budget

Practical rule from production deployments: keep routed tool definitions under 20K tokens (~10–15 tools for a typical MCP setup). Beyond that:

- Implement tool discovery at call time (Anthropic's approach: agent writes code that fetches only the relevant tool schemas when needed)
- Use a tool router / intent classifier that filters the active tool set before the model sees it
- Group tools into capability modules and load only the relevant module per task type

### 3. Give every agent one universal fallback tool

A sandboxed code executor (Python, JavaScript, or a lightweight sandbox like e2b) is the tool that fills the execution gap. It is:

- The tool you reach for when no predefined tool matches
- A natural retry surface — if a routed tool fails, the agent can try the equivalent operation in code
- A defense against dynamic/unusual inputs that would break a rigid schema

The Blaxel.ai blog (Apr 2026) documents the failure mode this solves: demos work because the user's request matches a tool. Production fails when the user's request is a composition no tool anticipated.

### 4. Instrument every tool with structured failure signals

Agent failure modes (from vectara/awesome-agent-failures, 194 stars, Aug 2025) cluster around three tool-specific problems:

- **Tool hallucination**: the tool returns a plausible-looking but incorrect result, and the agent acts on it
- **Permission loops**: the tool requests auth mid-task and the agent cannot recover
- **Schema drift**: the underlying API changes but the tool definition doesn't

Countermeasures: structured error schemas (not just strings), idempotency checks, explicit permission escalation states, and tool-level regression tests that run against live APIs.

### 5. Govern MCP servers as infrastructure, not code

Production MCP deployment (agentmarketcap.ai, Fordelstudios, Apr 2026) surfaces three engineering requirements that tutorials skip:

- **Transport selection**: SSE conflicts with load balancer timeouts at scale. Use Streamable HTTP for production deployments.
- **Auth delegation**: each server handling OAuth independently creates auth storms. Use a gateway that federates credentials.
- **Observability**: MCP has no native trace format. Instrument at the protocol layer — every `tools/call` should emit a structured event.

## Evidence

- **Engineering blog:** Anthropic's "Code execution with MCP" documents the token consumption problem and the code-writing pattern at scale — [https://www.anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **HN discussion:** "Principles for production AI agents" thread (128 pts, Jul–Aug 2025) surfaces evaluation and reliability as the primary constraint once tools go to production — [https://news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **HN discussion:** "MCP is a fad" (145 pts, ~Feb 2026) captures the counterargument — agents self-write glue code, context overhead makes MCP unjustified, process-per-server multiplies resource cost — [https://news.ycombinator.com/item?id=46552254](https://news.ycombinator.com/item?id=46552254)
- **Community resource:** vectara/awesome-agent-failures documents tool hallucination, response hallucination, permission loops, and schema drift with real case references — [https://github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **Industry analysis:** AgentMarketCap's MCP production reliability post (Apr 2026) documents the three production failures (context bloat, auth friction, stateful transport) and the five engineering patterns that fix them — [https://agentmarketcap.ai/blog/2026/04/11/mcp-production-reliability-patterns-2026](https://agentmarketcap.ai/blog/2026/04/11/mcp-production-reliability-patterns-2026)
- **Technical walkthrough:** Stochastic Sandbox's "MCP, Tool Use, and Function Calling: How Agents Actually Work in 2026" covers the full mechanism with code examples — [https://stochasticsandbox.com/posts/agents-rundown-2026-03-25/](https://stochasticsandbox.com/posts/agents-rundown-2026-03-25/)

## Gotchas

- **Adding tools feels like progress; it often isn't.** Each new routed tool is a new failure mode, a new schema to keep in sync, and a new token cost. The team that hits 80 tools and wonders why the agent got worse did not run out of capability. They ran out of context.
- **Browser automation is not a tool problem — it is a determinism problem.** Browser demos work on happy paths. Production fails when pop-ups appear, load times vary, or UI elements change. Agents that learned steps deterministically (Simon Willison's "Cyberdesk" pattern) fail gracefully; agents that rely on the model to navigate dynamically fail loudly.
- **MCP's ease of setup is also its security liability.** The community built thousands of MCP servers in months. The ones that shipped to production with credential-handling bugs outnumber the ones that didn't by an unknown factor. Treat every MCP server as untrusted until audited.
- **The "Perplexity abandoned MCP" signal is real but nuanced.** They didn't abandon tool integration — they abandoned the upfront schema-loading pattern at their scale. Smaller teams can still use MCP effectively; they just shouldn't follow the "load everything" pattern.
