# S-1373 · The Context-Window Toolshed Stack — When Your Agent Has Tools but Can't Afford to Use Them

You gave your agent 40 MCP tools. It now has file read, database query, browser automation, web search, Slack, GitHub, Figma, and a dozen internal APIs. Theoretically it's powerful. Practically, it's slower and dumber than before — every tool definition chews context, every result floods the model, and the agent spends more tokens on tool overhead than on reasoning. The tools are there, but using them costs more than the agent can afford. This is the toolshed paradox, and it hits the moment you scale beyond a handful of MCP servers.

## Forces

- **MCP ecosystem exploded.** Thousands of MCP servers exist for everything from Google Drive to Postgres to browser automation. Connecting them is solved. The unsolved part: managing what gets loaded into context and when.
- **Every tool definition is a tax on your context window.** Direct tool calling requires loading all tool schemas upfront. A 50-tool MCP server can add 8–15K tokens of overhead before a single call executes.
- **Large tool results are worse than definitions.** A database query returning 500 rows, a file listing 200 files, a web page scrape — these can dwarf the agent's actual reasoning in a single round-trip.
- **The wrong toolset dilutes the agent.** Agents given too many tools spread attention thin and make irrelevant calls. The "capability" of a large tool registry often looks like a capability tax on the model's actual task.

## The Move

Adopt the **context-budgeted toolshed** — not "give the agent everything," but deliberate, layered tool provisioning with code-execution as the primary aggregation mechanism.

- **Use MCP as the universal tool interface.** Anthropic's engineering blog (Nov 2025) established MCP as the de-facto standard for connecting agents to external systems. One MCP client unlocks the entire ecosystem without per-tool custom integration. (https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Give agents code execution, not direct tool calls.** Anthropic's recommended pattern: instead of the agent calling tools directly (each round-trip flooding context with definitions and results), the agent writes code that calls tools. The code executes, returns only the filtered result, and the agent continues reasoning with that distilled output. This eliminates the two heaviest context consumers: bulk tool schemas and large result payloads.
- **Use browser automation for web interaction.** The Agent Browser Protocol (ABP), a forked Chromium for AI agents, freezes JavaScript execution between each agent action, capturing deterministic state before proceeding. Achieved 90.5% on Online Mind2Web (85.51% on hard tasks) using Opus 4.6. The core insight: most browser-agent failures come from stale state, not model misunderstanding — freezing the browser at each step solves the root cause. (https://news.ycombinator.com/item?id=47336171)
- **Auto-generate tools from authenticated sessions.** A newer pattern from Frigade: a browser-based agent watches an authenticated web app call its own APIs, then auto-generates tool definitions ("recipes") from those observed calls. An MCP server that self-updates as the host app changes, without any source code access required. (https://news.ycombinator.com/item?id=48847834)
- **Restrict tools to the task's actual surface area.** Julien Chaumond (co-founder, HuggingFace) demonstrated that a production-grade MCP agent is "literally just a while loop" on top of an MCP client. The practical implication: the tool selection is where the engineering lives, not the agent loop itself. Give agents only the tools relevant to their immediate goal. (https://huggingface.co/blog/tiny-agents)
- **Sandbox all code execution.** Production stacks (OpenAI Agents SDK + E2B, Anthropic's MCP) route code execution through ephemeral sandboxed environments. The agent writes and executes code inside the sandbox, which then calls tools on the agent's behalf — never the agent directly. (https://e2b.dev/docs/agents/openai-agents-sdk)

## Evidence

- **Anthropic Engineering Blog:** Code execution with MCP — proposes writing code to call tools instead of direct tool calls to address context bloat with large tool registries and result sets. 3,000+ community MCP servers as of Nov 2025. — https://www.anthropic.com/engineering/code-execution-with-mcp
- **Hacker News (Show HN):** Agent Browser Protocol — forked Chromium that freezes browser state at each agent step, achieving 90.5% on Online Mind2Web. 155 points, 55 comments. — https://news.ycombinator.com/item?id=47336171
- **Hacker News (Show HN):** Frigade — browser-based agent that reverse-engineers authenticated web app APIs into auto-generated LLM tools. 96 points, 40 comments. — https://news.ycombinator.com/item?id=48847834
- **HuggingFace Blog:** Tiny Agents — MCP-powered agent in 50 lines of code, demonstrating that MCP standardizes tool access so the agent loop itself is trivial. — https://huggingface.co/blog/tiny-agents
- **Cleanlab Survey (2025):** 1,837 engineering/AI leaders surveyed; only 95 had agents in production. Of those, 70% of regulated enterprises rebuild their AI stack every 3 months or faster. — https://cleanlab.ai/ai-agents-in-production-2025

## Gotchas

- **Don't load all MCP servers at startup.** The "plug in everything" instinct creates the exact context bloat the code-execution pattern solves. Load only what the current task needs.
- **Browser automation tools are fragile without state freezing.** Agents that read a page, perform an action, then re-read expecting the same page structure fail constantly in dynamic SPAs. Freezing the execution state between steps is not optional for reliable browser agents — it's the difference between 40% and 90% task completion.
- **Auto-generated tools need schema validation.** When agents reverse-engineer API calls from observed traffic (Frigade pattern), the generated schemas may not match what the model needs for structured reasoning. Treat auto-generated descriptions as a starting point, not a finished contract.
- **Sandbox escape is a real risk.** Code execution tools that let agents run arbitrary Python or JavaScript in unsandboxed environments can exfiltrate data or escalate privileges. E2B, Anthropic's sandboxed execution, and similar isolation layers exist for this reason.
