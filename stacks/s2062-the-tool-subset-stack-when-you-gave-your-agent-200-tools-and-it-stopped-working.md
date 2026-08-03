# S-2062 · The Tool Subset Stack — When You Gave Your Agent 200 Tools and It Stopped Working

You gave your agent access to everything: the full MCP registry, every internal API, every filesystem path, every search endpoint. You thought more tools meant more capability. The agent started picking wrong tools, ignoring the right ones, hallucinating API parameters, and burning through tokens at 10x the budget. The agent with 200 tools was less useful than the one with 5.

More tools create a selection problem the agent has to solve before it can solve your problem. Curation is the real engineering work.

## Forces

- **Token cost is proportional to tool definition size, not usage.** Every tool registered with an MCP client loads its schema into context at session start. A 50-tool MCP server adds ~50–150K tokens before any real work begins — multiplied by every model call in multi-step agents.
- **Anthropic measured the waste.** Direct tool calls pass full JSON Schema definitions and intermediate results through the context window. Their analysis showed token reduction from 150,000 to 2,000 (98.7%) by shifting from direct tool calls to code-execution-style tool invocation via MCP — for the same tool set.
- **Over-tooling degrades agent accuracy.** Developers on HN and Reddit r/LocalLLaMA independently report that adding tools beyond ~15–20 causes the agent to mis-select, parameter-hallucinate, or loop on tool selection. The agent's working memory gets consumed by tool diversity rather than task logic.
- **The MCP ecosystem has no quality gate.** Thousands of MCP servers exist. Most were built as demos or for a single use case. Exposing the full registry to an agent is the equivalent of giving a new hire the entire company's codebase and asking them to find the bug.
- **Tool descriptions are the interface, not the code.** Frigade's approach to auto-generating agent tools from reverse-engineered web apps surfaced a key insight: a recipe (tool spec) needs endpoint + auth method + response schema + input schema + human-readable description. Generic wrappers that skip the schema details leave the agent guessing.

## The move

**Curate a narrow, well-described tool surface. Then present tools on-demand, not all at once.**

- **Start with a tiered tool taxonomy, not a flat list.** Separate tools into tiers by cost and risk: read-only (search, filesystem read) at the top, low-stakes writes (Slack, CRM) in the middle, irreversible writes (database writes, financial transactions) at the bottom with human-in-the-loop gates. Most agents only need the first two tiers for 80% of tasks.
- **Write tool schemas like API docs, not feature lists.** Each tool definition should include: name, purpose (1 sentence), input schema (strict types, not freeform), output schema (what the agent gets back), and error behavior (what happens on failure). Frigade calls these "recipes" — the same concept, made explicit.
- **Present MCP servers as a filesystem, not a tool list.** Anthropic's recommended pattern: mount MCP server tool definitions as files the agent can read on demand, rather than loading all definitions into context upfront. The agent navigates to the tool it needs, reads its definition, then calls it. Token cost drops dramatically because the agent only loads the tools it touches.
- **Use MCP for standardization, not volume.** The value of MCP is that you write one integration and connect to any compliant server. It is not a reason to connect more servers. Pick 3–5 high-quality MCP servers per workflow and own the schemas.
- **Sandbox filesystem access, don't copy into it.** Tilde.run's approach — FUSE-mounting a versioned filesystem into the sandbox rather than copying data in — gives agents a safe workspace without data duplication and enables transactional rollback. This pattern scales to large datasets where copy-in/copy-out breaks.
- **Version your tool schemas.** When a backend API changes its response shape and you don't update the tool schema, the agent gets a silent failure. Tag tool versions, invalidate stale definitions, and treat tool schema changes with the same discipline as API versioning.
- **Measure tool usage, not just task success.** Track which tools are actually called, which fail, which are never used, and which cause parameter mismatches. A tool that is never called is a tool that should be removed.

## Evidence

- **Anthropic Engineering Blog (Nov 2025):** Code execution with MCP — measuring 98.7% token reduction by shifting from direct tool calls to on-demand code-based tool invocation. Cloudflare published similar findings ("Code Mode"). Both found that the bottleneck was tool definition overhead, not tool execution. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **HN Show HN · Frigade (96 points, Jul 2026):** Built a browser-based agent that reverse-engineers authenticated web apps into auto-generated MCP "recipes" — each recipe includes endpoint, auth method, response/input schema, and description. Their insight: the hard part is not connecting tools, it is writing the schema well enough for the agent to use it correctly. Live demos for Jira, Spotify, Hacker News, Airbnb. — [URL](https://news.ycombinator.com/item?id=48847834)
- **HN Show HN · Tilde.run (205 points, Apr 2026):** Agent sandbox with transactional, versioned filesystem via lakeFS. FUSE-mounted filesystem (not copied) into sandbox environment. Enables agents to work with large data directly without moving tokens through context. Solves both the isolation problem and the state management problem for sandboxed tool execution. — [URL](https://news.ycombinator.com/item?id=48037724)
- **HN Discussion · OpenAI Agents SDK thread (389 points, Mar 2025):** Developer consensus on HN that "most agent frameworks abstract a set of design patterns that are not common yet." Direct objection to framework-level tool bundling — preference for explicit, owned tool definitions over vendor-managed state machines with implicit tool sets. — [URL](https://news.ycombinator.com/item?id=43334644)
- **r/LocalLLaMA discussion on MCP vs CLI tools (May 2026):** Community members report that CLI-based tool access avoids MCP's token overhead entirely for local models with smaller context windows. "Command Line Interface. It just works and no token bloat." Trade-off: less structured, requires better prompting. — [URL](https://www.reddit.com/r/LocalLLaMA/comments/1r3p394/)

## Gotchas

- **Adding tools is easy; removing them is hard.** Once a tool is registered in an MCP client, it accumulates use cases and workflow dependencies. Teams add tools during sprints and never audit the registry. Schedule quarterly tool inventory: which tools are called, which fail silently, which have never been used.
- **MCP tool poisoning is a real supply chain risk.** The OWASP Top 10 for Agentic AI (Dec 2025) flags ASI02 (Tool Misuse) and ASI04 (Agentic Supply Chain Vulnerabilities). Malicious or poorly-maintained MCP servers can be poisoned to return misleading data. Don't connect to MCP servers you don't own and audit.
- **Tool schema drift is invisible.** When a backend API changes response format and the MCP server schema doesn't update, the agent silently receives malformed data. The failure appears as agent confusion, not an error. Add schema validation as a layer between the MCP server and the agent.
- **Authentication is the hardest part of every tool.** Frigade's post explicitly calls out the challenge: modern web apps use complex auth patterns (refresh tokens, OAuth flows, cookie-based sessions). Any tool given to an agent needs auth that's been tested end-to-end — the agent cannot recover from a 401 any better than a human can.
- **Agents with no tools outperform agents with too many on simple tasks.** The sweet spot is not a fixed number — it is the minimum set that covers the task. For a research agent: web search + filesystem read. For a coding agent: shell + filesystem + git. For a workflow automation agent: the specific API calls the workflow needs, nothing else.
