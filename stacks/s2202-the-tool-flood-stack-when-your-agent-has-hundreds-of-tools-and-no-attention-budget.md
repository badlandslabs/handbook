# S-2202 · The Tool Flood Stack

When your agent can call a hundred tools but only needs three, and you have no idea which three it will pick — or whether it will pick the wrong one, call all of them, or freeze trying to decide.

## Forces

- **The MCP Cambrian explosion.** Since Anthropic open-sourced the Model Context Protocol in November 2024, thousands of MCP servers have been published — GitHub MCP Registry alone lists 203, with the top servers (Markitdown, Netdata, Context7, Chrome DevTools, Playwright) each installed tens to hundreds of thousands of times. The ecosystem is rich; the agent's ability to navigate it is not.
- **Context window is not a blank check.** Loading hundreds of tool definitions upfront — each with name, description, parameters, and examples — consumes tokens on every call. Anthropic's own analysis (November 2025) shows this is the primary driver of agent cost and latency as deployments scale.
- **Tool description quality is agent命运的.** The HN community has converged on a counterintuitive finding: agents perform better when tool descriptions include *when not to use* the tool, not just what it does. The agent's tool selector is a blind auction — it picks based on description and schema, with no feedback loop until it gets the result.
- **Browser-as-tool is the new universal interface.** Three independent projects (Browser Use, Agent Browser Protocol, Frigade, peerd) all converged on the same insight: the browser is the tool that subsumes all other tools. But raw browser automation has its own failure modes — stale state after actions, race conditions with modals, authentication complexity.

## The Move

The move is **tool curation with on-demand loading** — not giving agents fewer tools, but giving them a smarter interface to the full catalog.

- **Write tool descriptions for the selector, not humans.** Include when-not-to-use triggers. Specify input/output shapes precisely. Agents pick tools before they see the result, so the description is the entire decision surface.
- **Load tools on demand, not upfront.** Anthropic's recommended pattern: the agent writes code that calls the MCP server directly, rather than having the MCP client pass all tool definitions into context. This shifts tool selection from "pick from a menu" to "write a function call" — a task the LLM already excels at.
- **Treat the browser as a universal MCP server.** Instead of building a custom API integration for every web app, reverse-engineer the app's own API calls from inside an authenticated browser session. Frigade's approach: watch the app call its own APIs, auto-generate a "recipe" (tool definition + auth + schema), and publish it to the agent. The app becomes the tool without any custom integration.
- **Freeze the browser state after every action.** Agent Browser Protocol (ABP) freezes JavaScript execution and rendering immediately after each action, then sends the agent a fresh screenshot + structured state summary. This eliminates the stale-state failure mode that makes browser automation unreliable — the agent always reasons on what actually happened, not what it expects to have happened.
- **Scope tool registries with governance.** The MCP Gateway Registry (Apache-2.0, enterprise-focused) wraps the MCP ecosystem with OAuth authentication, audit logging, and role-based access. In production, tool flooding is a security surface — agents calling unauthorized tools, tools with excessive permissions, tools that exfiltrate data. Gate the catalog the same way you gate the code.

## Evidence

- **Anthropic engineering post (Nov 2025):** Documented the token-consumption problem with tool definitions at scale and proposed code-execution-as-tool-loading as the solution. Found that direct tool calls consume context for each definition and result; agents scale better by writing code that calls MCP servers on their behalf. — [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Frigade Show HN (96 points, 40 comments):** A browser-based agent that runs inside authenticated web apps, observes API calls, and auto-generates reusable agent tools ("recipes"). Bypasses the API-integration problem entirely — the app's own client-to-API traffic becomes the tool definition. — [news.ycombinator.com/item?id=48847834](https://news.ycombinator.com/item?id=48847834)
- **Agent Browser Protocol Show HN (155 points):** Chromium fork specifically for AI agent automation. Achieves 90.5% on Online Mind2Web by freezing state after each action and returning a fresh screenshot + structured event summary to the agent. Addresses the stale-state race condition endemic to CDP/Playwright-based browser agents. — [github.com/theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol)
- **GitHub MCP Registry (launched September 2025):** Centralized registry for MCP servers, with 203 servers indexed at launch and top servers showing 35K–171K installs. Signals that the tool ecosystem has reached sufficient density that discovery is now the bottleneck, not availability. — [github.blog/changelog/2025-09-16-github-mcp-registry](https://github.blog/changelog/2025-09-16-github-mcp-registry)
- **Ask HN community discussion (38 points):** Practitioners identified that the biggest win for tool description quality is specificity about when NOT to use the tool — agents pick confidently from an overconfident description and fail silently. Tool descriptions for agents need to be adversarial-tested, not just descriptive. — [news.ycombinator.com/item?id=47127532](https://news.ycombinator.com/item?id=47127532)

## Gotchas

- **Tool description drift.** As MCP servers evolve, their schemas change. Agents cached a tool's parameter shape at session start will call it incorrectly after a schema update. Add schema version checking to the tool registry.
- **The browser is a footgun without sandboxing.** Browser-based agents can execute JavaScript, navigate to arbitrary URLs, and interact with authenticated sessions. ABP's state-freeze is a reliability improvement, not a security boundary. Isolate browser sessions from sensitive credentials at the infrastructure level.
- **Tool flooding enables prompt injection at scale.** A malicious tool in the registry — or a compromised MCP server — can serve a tool definition that instructs the agent to exfiltrate context. The MCP Gateway Registry's audit logging is a minimum; static analysis of tool definitions before registration is the next layer.
- **On-demand loading trades latency for tokens.** Code-execution tool loading (Anthropic's pattern) reduces token consumption but adds a round-trip latency per tool invocation. For agents that need 3 tools in rapid sequence, this can be slower than having all definitions pre-loaded. Profile before committing.
