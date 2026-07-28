# S-1752 · The Tool Selection Stack — Knowing What to Give Your Agent

You have 47 tools registered. The agent uses 3 reliably, hallucinates calls to 11 others, and ignores the rest. You spent three weeks building integrations nobody uses. The dominant mistake in agent tool design is not under-equipping agents — it is over-equipping them with poorly-scoped, poorly-documented, poorly-prioritized tools.

## Forces

- **Tool inflation is the path of least resistance.** It feels productive to add another tool integration. Each new tool expands capability in theory. In practice, each additional tool degrades selection quality, increases hallucination risk, and makes observability harder.
- **LLMs degrade gracefully in capability, not in tool selection.** A model with too many tools doesn't fail loudly — it picks wrong ones, picks plausible-but-wrong ones, or picks nothing at all. This failure mode is silent and semantic, not syntactic.
- **MCP changed the cost of adding tools.** The Model Context Protocol's SDK hit 97M+ monthly downloads in just over a year (Anthropic, December 2025), making tool integration cheaper than ever. This lowered the barrier to the exact mistake this stack addresses.
- **What you give the agent is not what it uses.** Anthropic's analysis of production agents found that even with dozens of tools available, successful agents used a small, reliable subset — and the teams that understood *which* subset actually got used built better systems.

## The move

**Constrain the agent's tool surface deliberately, not by accident.**

- **Default to 3–8 tools per agent.** Anthropic's production survey found that simple chains handle 80% of production use cases; teams that started with fewer tools and expanded only when forced had lower failure rates and shorter debugging cycles. An agent with 3 tools you understand completely beats one with 30 tools you're guessing about.
- **Write tool descriptions as if the agent is a junior engineer who has never seen your codebase.** Every tool name, parameter description, and return format should be self-contained. Vague descriptions ("fetches data") produce vague behavior. Specific, action-oriented descriptions ("returns the 10 most recent Jira tickets assigned to the current user, with status and priority") produce precise behavior.
- **Prefer MCP servers for shared tooling.** MCP has become the de facto standard for agent-tool communication, with the protocol donated to the Agentic AI Foundation in late 2025. Use it. A well-maintained MCP server with clear schema beats a hand-rolled tool integration with ambiguous error handling every time.
- **Use Anthropic's advanced tool use features for dynamic discovery at scale.** Released November 2025, these features let Claude dynamically discover, learn, and execute tools from large catalogs — addressing the "thousands of tools" scenario without pre-loading every definition. If your system needs >20 tools per agent, use dynamic discovery rather than static registration.
- **Measure tool selection accuracy, not tool coverage.** Track what percentage of tool calls the agent makes are correct and necessary. A 95% selection accuracy on 5 tools is more valuable than 60% accuracy on 30 tools.
- **Audit tool usage monthly in production.** Pull real traces. Identify tools that the agent never selects, selects incorrectly, or selects when a simpler approach would suffice. Prune ruthlessly. The best tool catalog is the smallest one that reliably solves the problem.

## Evidence

- **Engineering blog:** Anthropic's analysis of production LLM agents found "the most successful implementations use simple, composable patterns rather than complex frameworks." After working with dozens of teams, they found that starting with simple prompts and expanding only when measurement demanded it consistently outperformed ambitious tool catalogs — [URL](https://www.anthropic.com/engineering/building-effective-agents)
- **Engineering blog:** Anthropic introduced advanced tool use (November 2025) specifically to address tool catalog scalability — Claude can now dynamically discover, learn, and execute tools without stuffing every definition into context — enabling agents to work across "hundreds or thousands of tools" without degradation — [URL](https://www.anthropic.com/engineering/advanced-tool-use)
- **Company engineering post:** Block built Goose, an autonomous agent using MCP to connect to Snowflake, Jira, Slack, Google Drive, and internal task-specific APIs. The integration enabled employees to cut up to 75% of time spent on daily engineering tasks — [URL](https://block.github.io/goose/blog/2025/04/21/mcp-in-enterprise/)
- **Y Combinator:** "Show HN: Mcp-Agent" (80 points, January 2025) introduced a framework specifically for building agents with MCP — highlighting the pattern of standardizing tool communication rather than hand-rolling each integration — [URL](https://news.ycombinator.com/item?id=42867050)
- **MCP ecosystem scale:** MCP SDK downloads grew from 100K to 97M+ per month in just over a year, with 13,000+ public MCP servers. The protocol was donated to the Agentic AI Foundation in December 2025 — [URL](https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation)
- **Production case:** A Singapore Series-A SaaS company running LangGraph with MCP for customer support (2.3M requests/month) cut monthly AI costs from $4,200 to $680 (84%) and reduced failed requests by 97% after consolidating fragmented tool integrations through a unified MCP gateway — [URL](https://www.holysheep.ai/articles/en-langgraph-vs-crewaimcpxieyiluodishengchannajiaqian-2026-04-10-0039.html)

## Gotchas

- **Don't equate "tool exists" with "tool is useful."** The MCP ecosystem now has 13,000+ public servers. The question is never "can we add this?" — it's "does this tool reliably improve the agent's output on its actual task?" A tool that adds 5% capability but increases failure surface by 20% is a net negative.
- **Tool descriptions degrade silently in production.** A description that seemed clear during development becomes misleading when the agent encounters edge cases. Re-read tool descriptions through the lens of "what would an agent confused by this do?" — then fix the description, not the agent.
- **LLM function calling is not the same as MCP.** Function calling (per-model tool selection) decides *what* needs doing. MCP provides *how to do it* reliably. They compose — OpenAI's function calling can dispatch to an MCP server — but conflating them leads to over-engineered architectures.
- **The 80/20 of tool design is tool naming and parameter schemas.** Spend 80% of your tool design budget on clear names, unambiguous parameter types, and explicit error return formats. The actual function logic is usually trivial; the ambiguity lives in the contract.
