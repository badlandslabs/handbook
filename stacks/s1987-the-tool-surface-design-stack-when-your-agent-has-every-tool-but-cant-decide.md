# S-1987 · The Tool Surface Design Stack

When your agent has access to every API, tool, and capability under the sun — but still fails because it can't figure out which one to use, or picks the wrong one and cascades into bad output.

## Forces

- **Tool proliferation vs. selection quality.** More tools give agents more reach, but every additional tool increases the chance of mis-selection and burns context budget. Teams routinely over-instrument agents in the belief that more capability = better outcomes.
- **Breadth vs. coherence.** An agent with 47 tools needs a much longer system prompt just to describe them all. At some point, the tool list becomes noise the model learns to ignore — or worse, tries to use everything at once.
- **The MCP revolution made this acute.** MCP (Model Context Protocol) made it trivially easy to connect agents to external tools — 97M+ monthly SDK downloads in under a year, 13,230+ public servers. The plumbing got cheap; the design problem got expensive.
- **Browser agents created a new tool category.** Vision-capable browser automation (Claude Computer Use, OpenAI Operator, Browser Use) shifted what "a tool" means — from function calls to full UI interaction. This creates a decision layer most teams haven't thought through: when do you reach for an API vs. a browser?

## The Move

Design tool surfaces deliberately — not by what tools exist, but by what tasks the agent must reliably complete. The core practice is **tool bundling**: group related capabilities into coherent, named tools rather than exposing every API endpoint. Then scope tool descriptions to include what the tool *cannot* do, not just what it can.

Concrete moves:

- **Start with 3–5 tools maximum.** Add tools only when you observe a specific capability gap in production traces, not in anticipation of future needs. Browser Use (YC W25) found their community's most reliable agents used a tight, task-matched toolset; sprawl correlated with failure.
- **Bundle rather than expose.** Instead of `GET_customer_by_email`, `POST_ticket`, `GET_ticket_history`, `PATCH_ticket_status` — expose one tool: `update_customer_record(type, record_id, changes)`. Bundling reduces selection overhead and makes the agent's job tractable.
- **Use MCP as the integration layer.** MCP standardizes tool interfaces (tools, resources, prompts, samplers) so each new tool implements the server once. This shifts effort from wiring to designing — which is where it should be. Early adopters like Block (Square), Sourcegraph, and Notion use MCP to connect agents to internal systems without N×M custom integrations.
- **Browser automation is a last resort, not a first.** When an API or webhook exists, use it. Browser automation (Claude Computer Use, Browser Use, OpenAI Operator) is for portals with no API, legacy tools with broken automation, or tasks where the site itself is the interface. All three browser agent families still fail regularly on CAPTCHAs, multi-tab flows, and OAuth — they should be scoped to bounded, recoverable workflows.
- **Tool descriptions must include failure modes.** Include what the tool can't do, its rate limits, and the shape of error responses. An agent that knows `web_search` returns stale results handles them differently than one that treats it as ground truth.
- **Add a "do nothing" tool.** Explicitly allow the agent to decline to act. Many failure modes (selection paralysis, low-confidence choices) are better handled by a deferral than a bad call.

## Evidence

- **MCP growth and enterprise adoption:** Anthropic donated MCP to the Linux Foundation's Agentic AI Foundation. Downloads grew from ~100K to 97M+ per month in roughly one year, with 13,230+ public servers. Block, Sourcegraph, and Notion are documented early production adopters. — [Anthropic MCP announcement, Dec 2025](https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation); [OpenClaw MCP guide](https://openclaw.direct/mcp-guide/model-context-protocol-examples)
- **Browser agent landscape:** Browser Use (YC W25) crossed 79,000 GitHub stars in ~3 months. Three-tier comparison: Claude Computer Use leads on task success rate, OpenAI Operator has the most polished consumer UX, Browser Use is cheapest and most controllable for developers. All three still fail on CAPTCHAs, multi-tab flows, and OAuth. — [TechCrunch: Browser Use raises $17M](https://techcrunch.com/2025/03/23/browser-use-the-tool-making-it-easier-for-ai-agents-to-navigate-websites-raises-17m/); [Web3AI Blog: Browser Agents Battle May 2026](https://www.web3aiblog.com/blog/browser-agents-battle-operator-vs-claude-computer-use-vs-browser-use-may-2026)
- **MCP production failure patterns:** Study of 385 MCP repositories found 30,795 closed issues across five distinct fault categories. Common incidents: 60+ API calls failed silently over 48 hours because monitoring was built for request-response patterns, not streaming tool-call loops; OAuth tokens expired mid-session causing agents to silently hallucinate instead of querying the connected database. — [Paperclipped: MCP Server Production Lessons](https://www.paperclipped.de/en/blog/mcp-server-production-deployment-lessons)
- **Six-category tool taxonomy:** Neo4j's agent guide identifies six tool types teams actually use: web search (read-only, low risk), retrieval (RAG/vector search, low-medium), computation (code interpreters, medium), file I/O, API calls, and browser/UI automation. The guide notes that "without tools, an agent is a fluent writer with no hands." — [Neo4j: Agent Tools](https://neo4j.com/blog/agentic-ai/agent-tools/)

## Gotchas

- **Don't use browser automation when an API exists.** Every team wastes cycles building a browser agent to scrape a site that has a perfectly good REST API. Browser automation's comparative advantage is legacy portals and sites with no programmatic interface — not as a default approach.
- **Token budget is a hard constraint on tool count.** Every tool definition in the system prompt consumes context. A 200-tool agent with 500-token descriptions per tool has already burned ~100K tokens before the first user message. Budget the tool surface against your model's context and actual task requirements.
- **MCP auth is harder than it looks.** OAuth tokens expiring mid-session is a documented production failure pattern. Plan for token refresh, long-running operation timeouts, and session resumption. The local-first design most MCP servers ship with breaks immediately under multi-user production load.
- **More tools = more attack surface.** Every tool is a potential injection vector. The Confused Deputy attack (where a malicious server tricks the agent into calling unintended tools) is a real risk in MCP deployments. Minimum-privilege scoping matters from day one, not after a security incident.
