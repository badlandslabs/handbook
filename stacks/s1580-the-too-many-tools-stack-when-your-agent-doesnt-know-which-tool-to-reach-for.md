# S-1580 · The Too-Many-Tools Stack — When Giving Your Agent More Tools Makes It Worse

You have a production agent. You keep adding capabilities — MCP servers, function calls, API integrations. The tool count climbs. Performance drops. Nobody can explain why.

## Forces

- **MCP made it trivial to add tools** — one config line gets you thousands of potential tools, so teams add them freely without counting the cost
- **More tools should mean more capability** — that's how software works, so the assumption is that agents scale the same way
- **The model's context is a zero-sum budget** — every tool definition you send consumes the tokens the model needs for reasoning
- **Selection accuracy degrades non-linearly** — adding the 30th tool doesn't just add a small risk of mis-selection; it degrades the model's ability to correctly pick *any* tool
- **GitHub Copilot hit this exact wall with 40 tools** — and found that cutting to 13 improved performance across benchmarks

## The Move

**Narrow the tool palette first. Add tools only when you can measure the improvement.**

1. **Start with 5–10 focused tools maximum.** Each tool does one thing with a clear name (`get_customer_by_id`, not `query` or `fetch_data`). More tools are a code smell, not a feature.

2. **Use runtime tool routing, not hardcoded tool lists.** Embed tool descriptions into a retrieval index and let the agent query for the relevant ones at task time. GitHub Copilot calls this "embedding-guided tool routing" — they reduced their default toolset from 40 to 13 by routing contextually.

3. **Cluster related tools under a single interface.** When you have 15 search tools, don't expose all 15. Bundle them into one `search` tool with parameters that route internally. Copilot's "adaptive tool clustering" groups tools by workflow stage.

4. **Treat tool poisoning as a supply-chain risk.** The MCP ecosystem makes it trivially easy to import a compromised tool server. A malicious or even buggy MCP tool description can redirect your agent silently. Microsoft's security team documented this: 30+ MCP CVEs filed in H1 2026. Review tool descriptions the way you'd review a dependency update.

5. **Instrument tool selection explicitly.** Every tool call should emit a trace with: tool name, parameters, result status, and latency. If you can't see which tool was picked and why, you can't debug why the agent failed.

6. **Measure task success rate per tool, not just per task.** If `search_internal_kb` fails 40% of the time, no amount of adding other tools fixes it — you fixed the wrong problem.

## Evidence

- **Engineering blog:** GitHub Copilot reduced their default toolset from ~40 to 13 core tools after discovering performance degraded across SWE-Lancer and SWE-bench benchmarks. They built embedding-guided tool routing and adaptive tool clustering as the fix. — [GitHub Blog, "How we're making GitHub Copilot smarter with fewer tools"](https://github.blog/ai-and-ml/github-copilot/how-were-making-github-copilot-smarter-with-fewer-tools/), November 2025

- **Engineering blog:** Microsoft Incident Response documented how MCP tool descriptions represent an unsanitized attack surface — a malicious or compromised MCP server can embed arbitrary instructions in tool descriptions that models obey invisibly. Even conservative models complied with poisoned descriptions in ~34% of test cases. — [Microsoft Security Blog, "Securing AI agents: When AI tools move from reading to acting"](https://www.microsoft.com/en-us/security/blog/2026/06/30/securing-ai-agents-ai-tools-move-from-reading-acting/), June 2026

- **HN discussion:** Practitioners report that models "struggle when you give them too many tools to call" and are "poor at assessing the correct tool to use when given tools with overlapping functionality or similar function name/args." — [Hacker News, "Building Effective AI Agents" thread](https://news.ycombinator.com/item?id=44315404), June 2025

- **Pattern catalog:** The Agent Patterns Catalog formally describes the Tool/Agent Registry pattern — maintain a queryable catalogue with metadata (capability, cost, latency, quality) the agent can use to pick the right tool, rather than hardcoding a flat list. — [Agent Patterns Catalog](https://www.agentpatternscatalog.org/patterns/tool-agent-registry/)

## Gotchas

- **MCP makes it feel free to add tools** — the friction is low, but the cost in context budget and selection accuracy is real. Every new MCP server is a potential security and performance liability.
- **Parallel tool calling sounds great but compounds the problem** — if the agent can call 5 tools at once, and each has a 6% failure rate, a 3-tool parallel call has a ~17% chance of at least one failure per step. Thread that through a 10-step task and failures become near-certain.
- **Tool descriptions are the trust boundary** — you trust what the tool does. If a tool description changes (dependency update, compromised server), your agent's behavior changes silently. Pin tool versions and log description hashes.
- **Lazy loading tools at call time is cheaper than loading all at startup** — if you must have many tools, query the registry at task time rather than dumping all definitions in the system prompt on every request.
