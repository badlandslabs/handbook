# S-2032 · The Tool Granularity Stack — When Your Agent Can Do Anything But Completes Nothing

You've built an agent with 12 tools. It can search the web, query your database, send Slack messages, create GitHub issues, run code, browse the browser, and more. The demos look great. In production, it loops, picks the wrong tool, fails silently on half the requests, and your token bill is 4× the estimate. The problem isn't tool count — it's tool design. The right tools, with the right boundaries, beat a large undifferentiated toolpile.

## Forces

- **More tools = more choices = more wrong choices.** With N tools, the agent must correctly identify which one applies. With 12 tools, it misroutes ~15-25% of the time. Cross that with a 10-step workflow and you have ~20% end-to-end success.
- **Broad tools hide failure.** A `do_everything` tool that internally branches on context looks powerful but returns a convincing-looking output while silently skipping work.
- **The 95% reliability cliff.** Step reliability compounds: 95% × 95% × 95%... hits 60% at 10 steps, 46% at 15. Every tool call is a coin flip on whether the full pipeline survives.
- **Security and capability are in tension.** Real tools (GitHub, Slack, Stripe, production DB) do real damage. Sandboxed proxies lose the value. You need both — with explicit guardrails.
- **MCP changed the economics.** Before Model Context Protocol, every new tool meant a new custom integration. Now it's a plug-and-play server. Teams went from 3-day integrations to 11-minute deployments. This changed what "reasonable tool count" means.

## The move

**Design tools like APIs, not prompts.** Each tool has one job, a strict input schema, a predictable output schema, and no internal branching.

**Give agents 2-5 tools, never 12.** Narrow tools with specific preconditions beat broad tools with vague ones. One engineer reported: narrow roles with 2 tools + specific backstory consistently beat 6 tools + broad goals — fewer wrong-tool calls, fewer loops, better output.

**Validate before you execute.** Run tool output through a schema validator before the next step. On validation failure, re-invoke the model with the schema definition explicitly in context — not just referenced. This single-retry pattern catches the most common silent failure mode at the lowest cost.

**Set iteration caps per agent.** CrewAI's default `max_iter=25` is a budget burner. Set it to 5-8 per agent. One bad run with unbounded iterations can cost 5-10× the normal token budget.

**Use Pydantic output models.** Force structured output schemas at every tool boundary. This avoids fragile string parsing, enables programmatic validation, and turns silent malformation into a catchable exception rather than a downstream crash.

**Pick your browser tool by production context:**

- **Claude Computer Use** — best for full desktop control (terminal, file manager, IDE). Screenshot → decide → act loop. Highest task success. Requires sandboxing and least-privilege scoping.
- **OpenAI Operator / ChatGPT agent mode** — consumer-grade browser automation. Built-in safety guardrails. Moved from $200/month standalone to included in ChatGPT Plus. Score: 32.6% on OSWorld (real-world desktop tasks).
- **Stagehand** — production browser automation in your own code. 14,000+ GitHub stars. 3× more resilient than Selenium. Built on Playwright.
- **browser-use** (open-source) — model-agnostic Python library. 60,000+ GitHub stars. Cheapest option. Good for developers who want full control.

**Use MCP for business/production tool integration.** Model Context Protocol is the dominant standard by mid-2026 (97M monthly SDK downloads, 200+ community servers, adopted by OpenAI, Anthropic, Google). Key integrations: GitHub (issues, PRs, repos), PostgreSQL (read queries), Slack (notifications, channel lookups), Stripe (payment events, refunds), Notion (pages, databases). Each is a separate MCP server with its own auth scope — agents get exactly what they need, nothing more.

**Guard every destructive tool with a policy layer.** Unguarded agents will create real GitHub issues, post to real Slack channels, and run real database writes. Implement an authorization layer between the model decision and the tool execution that enforces scope and blocks high-impact actions without explicit workflow-level approval.

## Evidence

- **Engineering blog:** Anthropic's "Building Effective AI Agents" (Dec 2024, canonical) defines agents as "augmented LLMs running in a loop" and recommends starting with the simplest tool set that solves the problem, adding complexity only when evidence demands it — [Anthropic Engineering](https://www.anthropic.com/engineering/building-effective-agents)
- **arXiv paper:** "A Practical Guide for Designing, Developing, and Deploying Production-Grade Agentic AI Workflows" (Dec 2025) catalogs tool categories and stresses that "tool schema design directly determines reliability" — [arXiv:2512.08769](https://arxiv.org/pdf/2512.08769)
- **Company engineering post:** Neo4j's tool taxonomy (Web Search, Retrieval, Computation, File, Computer-use, Business/Productivity) — each category has distinct security implications and failure modes requiring different handling — [Neo4j Blog](https://neo4j.com/blog/agentic-ai/agent-tools/)
- **Case study:** Markaicode's MCP integration guide (March 2026) documents GitHub + PostgreSQL + Slack integration via MCP, with per-server authentication scoping and explicit permission boundaries — [markaicode.com](https://markaicode.com/mcp-tool-integration-agent/)
- **Benchmark analysis:** Browser agent comparison (May 2026) finds Browser Use leads WebVoyager at 89.1%, Claude Computer Use leads on task success, Operator scored 32.6% on OSWorld (real desktop tasks) — [Web3AIBlog](https://www.web3aiblog.com/blog/browser-agents-battle-operator-vs-claude-computer-use-vs-browser-use-may-2026)
- **Production post:** Pento CTO's "A Year of MCP" (Dec 2025) reports MCP adoption timeline: Anthropic released it Nov 2024, OpenAI adopted it Mar 2025, 97M monthly SDK downloads by end of 2025, deployment time dropped from 3 days to 11 minutes — [Pento Blog](https://www.pento.ai/blog/a-year-of-mcp-2025-review)
- **HN thread:** "Building Effective AI Agents" HN discussion (June 2025, 543 points, 88 comments) surfaced production failure modes including silent tool call failures, unbounded loops, and budget overruns from excessive iteration — [Hacker News](https://news.ycombinator.com/item?id=44301809)
- **Enterprise post:** AgileSoftLabs "CrewAI in Production 2026" (June 2026) reports 3-agent pipeline at 100 runs/day costs ~$900/month; `output_pydantic` as a top reliability fix; iteration cap as the #1 cost control — [AgileSoftLabs](https://www.agilesoftlabs.com/blog/2026/06/crewai-in-production-2026-real-lessons)

## Gotchas

- **Silent tool call failures are your worst enemy.** They produce plausible-looking outputs while skipping actual work. An agent that writes a convincing summary without executing the tool is worse than one that crashes — because the crash gets noticed. Always validate output schema at every tool boundary.
- **`output_json` / unstructured output invites silent failure.** Without a Pydantic model or JSON Schema forcing structure, malformed outputs pass validation and break downstream consumers in ways that are hard to trace.
- **Browser agents are not production-ready for unattended use in 2026.** OSWorld scores of 32-87% (benchmark-dependent) mean 13-68% failure rates on real tasks. Use for exploratory automation with human oversight; do not use for fully autonomous production workflows without guardrails.
- **MCP server descriptions are a supply-chain attack surface.** Microsoft's June 2026 advisory: poisoned MCP tool descriptions can make AI agents leak data. Validate MCP server manifests and scope permissions to minimum necessary.
- **CrewAI `max_iter` default of 25 is a trap.** Set it explicitly per agent. Budget-conscious teams set 3-5. Complex multi-step tasks may need 8-10, but 25 is only appropriate for R&D exploration, not production.
