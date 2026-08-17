# S-2764 · The Tool Overflow Stack — When Your Agent Has 100 Tools and Calls None of Them Well

You connected your agent to 12 MCP servers. Your team is proud. The agent can browse the web, run code, query your database, call Slack, search your docs, and read GitHub issues. Six months later, the agent ignores half your tools, calls the wrong ones, runs up your context bill with tool definitions, and nobody can reproduce why it worked last Tuesday. Tool abundance is not agent capability. This is the tool overflow problem — and it is the most common failure mode in MCP-connected production systems.

## Forces

- **Tool count scales faster than signal.** Every MCP server you add adds more tool definitions to the system prompt, bloat that doesn't improve behavior. Context space is finite and expensive.
- **The agent decides what to call — and it decides poorly.** LLMs perform worse at tool selection as the tool list grows. They default to familiar tools or hallucinate approaches that don't require any tool at all.
- **Tool definitions accumulate but never get retired.** Nobody has a process for removing stale, redundant, or harmful tools. The list only grows.
- **More tools means more failure surface.** Every tool call is an API call to an external server, a potential timeout, a potential auth failure, and a potential security vector. The blast radius grows with the count.

## The move

**Layer three practices around every MCP deployment:**

1. **Tool RAG — retrieve the relevant subset, don't dump the full list.** Rather than passing all 100+ tools to the model at once, use semantic retrieval to fetch the top-N tools relevant to the current task. ApX documented this approach at scale: chunk tool descriptions, embed them, retrieve the top-5 at query time. Result: the model only sees what is actually relevant, context stays bounded, and tool selection accuracy improves because the signal-to-noise ratio is higher.

2. **Expose MCP servers as code APIs, not individual tool calls.** Anthropic's November 2025 engineering post showed the pattern: instead of the agent calling `search_database(query)` directly, it writes code that calls the MCP server — `server.search(query)` — and processes the result in-code. This bundles multiple operations into a single round-trip, reduces context overhead, and gives the agent a more programmable interface. The MCP server becomes a library, not a menu.

3. **Enforce a tool manifest with ownership and expiration.** Each tool needs a code owner, a use-count threshold, and a review cadence. GitHub runs millions of MCP tool calls per week with a 95%+ success rate — not by adding more tools, but by aggressively optimizing the ones they have. Their documented solution: 49% context reduction through optimization, not addition. If a tool hasn't been called in 90 days, it should be audited or removed.

4. **Dynamic tool filtering by permission scope.** GitHub solved security and context bloat simultaneously by filtering tools based on the authenticated user's permissions. The agent only sees tools it is allowed to call. This reduces the tool list to a relevant subset AND closes an attack surface. Stateless architecture with Redis-backed session storage keeps this fast at scale.

5. **Measure tool-level precision, not just task success.** Track: calls per task, tools used vs. tools available, call-to-success ratio per tool, and average tools-per-successful-task. If the average successful task uses 2 tools but your agent has 80 available, you have a 97.5% tool overhead problem.

## Evidence

- **Engineering blog (Anthropic, Nov 2025):** Direct tool calls consume context for each definition and result. Agents scale better by writing code to call tools instead. Code-as-API pattern enables on-demand tool loading and context-efficient data processing. — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Case study (ApX, Jan 2026):** Tool RAG approach — embedding tool descriptions, retrieving top-N relevant tools at query time — enables scaling MCP to 100+ tools without context bloat. Separate retrieval step from execution step. — [ApX Blog](https://apxml.com/posts/scaling-mcp-with-tool-rag)
- **Engineering talk (GitHub, 2026):** Scaled MCP server to 7 million tool calls/week. Key interventions: 49% context reduction through optimization, OAuth 2.1 with PKCE, dynamic tool filtering by permission scope, Redis-backed stateless sessions. Achieved 95%+ tool call success rate. — [ZenML LLMOps Database / YouTube](https://www.zenml.io/llmops-database/building-and-scaling-a-production-mcp-server-for-developer-tooling)

## Gotchas

- **Adding a tool feels like progress but often isn't.** Teams add MCP servers to solve specific problems, but never revisit whether the tool is actually being called correctly. A tool that exists but is never used is a liability, not an asset.
- **Tool RAG retrieval quality depends on the tool descriptions.** If your tool names and descriptions are vague or generic (e.g., "search" instead of "search_github_issues_by_label"), the retrieval step will return irrelevant tools and the problem persists in a different layer.
- **Context optimization is a one-time gain that degrades.** GitHub's 49% context reduction was a snapshot. As new tools are added, the optimization erodes. You need a continuous process, not a one-time project.
- **The code-as-API pattern adds complexity.** Writing MCP code that the agent can call requires your MCP server to have a clean, well-documented interface. If your MCP server is itself a mess of internal logic, you've just wrapped the mess in another layer.
