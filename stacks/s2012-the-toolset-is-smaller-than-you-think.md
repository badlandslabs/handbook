# S-2012 · The Toolset Is Smaller Than You Think

When you sit down to give an agent "a full toolkit," the space of possible tools feels vast — every API, every service, every capability you could wire in. In practice, production agentic systems keep converging on the same half-dozen tool categories, and the hard part is not finding tools but deciding which ones to withhold.

## Forces

- **The M×N integration problem makes every new tool expensive.** Without a standard protocol, each new model requires a new adapter for each tool. The combinatorial cost blocks expansion.
- **More tools degrade agent focus and reliability.** Each additional tool is a distraction path the agent might wander down, increasing the chance of calling the wrong tool or mis-describing a task to fit a tool that almost fits.
- **Security surfaces expand with every tool.** Prompt injection risk, excessive agency, and unauthorized data access all scale with the number of tools and their privilege levels.
- **The tool categories that actually matter are surprisingly few.** Teams spend cycles building custom integrations for tools that the agent will never meaningfully use, while underinvesting in the core few that drive 90% of value.
- **Tool description quality dominates tool selection.** An agent with 3 well-described tools outperforms one with 20 poorly-described ones — the bottleneck is semantic clarity, not volume.

## The move

The move: treat your agent's toolset as a constrained interface, not a feature list. Default to the six proven categories. Add tools only when you have a specific, measurable failure to solve.

**The six categories that production agents actually use:**

- **Web search** — live fact retrieval, documentation lookup, current data. Read-only. Low risk. High value for any research-oriented agent.
- **Code interpreter / execution** — sandboxed runtime for Python, JavaScript, or shell commands. Lets the agent validate logic, process data, run tests, and compute results rather than estimate them. This is the highest-leverage single tool for coding and data agents.
- **File read/write** — structured access to project files, documents, or data exports. Typically scoped to specific directories or file types to limit blast radius.
- **Retrieval / RAG** — vector or keyword search over internal knowledge bases, documentation, or domain-specific corpora. The memory layer for agents that need company-specific context.
- **Browser / computer use** — screen-level automation for web apps, desktop GUIs, or enterprise tools that lack APIs. Claude's computer use tool, OpenAI's computer use API, and Playwright-based agents all fall here. Highest capability ceiling, highest risk.
- **Business tool integrations** — email, calendar, CRM, Slack, Jira, GitHub. These appear in operation-coordinator agents and customer-facing support agents. Typically require OAuth and scoped permissions.

**The standard protocol that is making this converge:**

- **MCP (Model Context Protocol)** — Anthropic introduced it November 2024, donated to Linux Foundation's Agentic AI Foundation December 2025. OpenAI, Google, Microsoft (VS Code Copilot), and most major frameworks have adopted it. It solves the M×N problem by defining one client-server protocol: implement once per model, implement once per tool, get universal compatibility. The shift from bespoke per-tool adapters to MCP is the clearest infrastructure pattern from 2025 production deployments.

**What to withhold:**

- Any tool that can modify production state without a human-in-the-loop gate
- Tools that ingest external content (emails, web pages, PDFs) without prompt injection defenses — these are the primary attack surface
- Tools that expose more data than the agent's task requires (least-privilege scoping)
- Tools that return unstructured text large enough to overflow context windows without summarization

## Evidence

- **Engineering blog (primary):** Anthropic's "Advanced Tool Use" (Nov 2025) introduces Tool Search (discover tools on-demand without consuming context), Programmatic Tool Calling (invoke via code execution to reduce context overhead), and Tool Use Examples. Documents that Claude for Excel uses Programmatic Tool Calling to handle thousands of rows without context overflow. The blog explicitly frames the future as agents working across "hundreds or thousands of tools" — the constraint problem, not the availability problem. — [Anthropic Engineering](https://www.anthropic.com/engineering/advanced-tool-use)

- **Engineering blog (primary):** OpenAI's "New Tools for Building Agents" (March 2025) announces the Responses API, Agents SDK, web search, file search/RAG, and computer use. HN discussion (389 points, 157 comments) surfaces the community consensus: "I haven't really found any agent framework worth using," and most serious production teams build custom orchestration rather than adopt a full framework. The tool categories in the announcement match the six-category model. — [OpenAI](https://openai.com/index/new-tools-for-building-agents/) + [HN Discussion](https://news.ycombinator.com/item?id=43334644)

- **Industry analysis (cross-referenced):** Neo4j's "Agent Tools" guide catalogs the six tool categories (web search, retrieval, computation, file, computer use, business/productivity) and assigns security risk levels to each. The Digital Consulting Team's production deployment guide (May 2026) confirms MCP is "becoming the default integration layer" and states that "tool design dominates agent quality." Axioma AI's framework evaluation (40+ client projects) identifies reliability, ergonomics, and observability as the key evaluation dimensions — all downstream of tool design decisions. — [Neo4j](https://neo4j.com/blog/agentic-ai/agent-tools) + [Digital Consulting Team](https://digital-consulting-team.com/en/blog/ai-agents-in-production-mcp-tool-use-and-orchestration-en-2) + [Axioma AI](https://blog.axioma-ai.com/top-tier-ai-agent-frameworks-f84d40cfd4c7)

## Gotchas

- **MCP tool definitions still consume tokens at session start.** Loading a full MCP server with 50 tools can eat 10K+ tokens before the first user message. Anthropic's Tool Search addresses this by deferring discovery to runtime — but most MCP implementations don't use it yet.
- **Computer use tools have the highest failure rate of any category.** Screenshots are lossy, UI elements shift, and agents get stuck in click loops. Browser-based agents need fallback strategies: if XPath breaks, try finding the button by label text, or escalate to human.
- **Tool descriptions are the most underinvested part of most agent systems.** Teams spend weeks on orchestration logic and spend five minutes writing the tool's description string. The description is what the model uses to decide whether to call the tool and how to format the call — it deserves as much engineering attention as the tool itself.
- **The "everything and the kitchen sink" toolset is a false optimization.** Adding tools that the agent will use <5% of the time creates confusion surface that outweighs their occasional utility. Measure tool utilization rates in production and retire the long tail.
- **Prompt injection defenses on content-ingesting tools are non-negotiable.** The OWASP LLM Top 10 (2025) ranks prompt injection and excessive agency as the top two risks for agentic systems. Any tool that reads external content — email, web pages, uploaded files — is a potential injection vector.
