# S-2720 · The Tool Hierarchy Stack — When Adding the 31st Tool Breaks Everything

[You added one more tool to your agent. Just one. A read-only lookup for part numbers. Then your success rate dropped 40 points overnight and nobody can figure out why. This is the tool explosion problem: agent tool-call accuracy degrades non-linearly, and the breakpoint is earlier than you think.]

## Forces

- **Adding tools feels free.** In software, more options are usually good. With agents, each tool definition competes for context space and model attention — adding the 31st tool degrades accuracy before you've even hit 30.
- **The 1:1 tool-to-capability instinct is wrong.** Teams build one tool per capability, then discover that 50 tools perform worse than 5. The model isn't selecting from a menu — it's reasoning over a single prompt that grows with every addition.
- **Tool descriptions pollute context non-linearly.** A simple single-parameter tool generates ~96 tokens in the tool schema. A complex 28-parameter tool generates ~1,633. 37 tools means 6,000+ tokens of schema before the user's query even enters the context.
- **The protocol wars are over — MCP won.** The Model Context Protocol crossed 97 million monthly SDK downloads in March 2026, with over 13,000 public servers. OpenAI deprecated its proprietary Assistants API in favor of MCP. Google, Microsoft, LangGraph, and CrewAI all support it natively. But MCP's success created its own problem: teams now have easy tool integration and no governance structure for it.
- **YC's 350 tools are a warning, not a target.** Y Combinator built 350+ tools internally in under two years — but they sit behind a routing layer. The agents never see all 350 at once.

## The move

The production pattern isn't "fewer tools" — it's **hierarchical routing with scoped tool sets**.

- **Keep individual tool sets to 1–5 tools.** The Berkeley Function Calling Leaderboard shows individual tool accuracy up to 96%. Real-world multi-tool scenarios drop below 15%. Cap each agent session at 3–5 tools max.
- **Use a router agent to select tool sets, not individual tools.** The router classifies the user's intent, then routes to a specialist agent that has exactly the tools it needs for that domain. YC's system routes finance queries to the finance tool set, legal queries to the legal tool set — none of the agents ever see all 350.
- **Define tools with dense, specific descriptions.** Vague tool names and thin descriptions push models toward the wrong call. Each tool definition needs: what it does, when to use it, what inputs to pass, and what the output looks like. This is the interface contract.
- **Implement Tool-RAG before you hit 30 tools.** Retrieve relevant tool definitions at runtime based on the user's query, rather than dumping the full tool manifest into every prompt. OpenAI introduced namespace-based tool search; Anthropic provides BM25 retrieval over tool descriptions.
- **Give agents the minimum viable tool set for the task.** If an agent only needs to read a database, give it one read-only tool. Resist the instinct to give each agent all the tools it *might* need. Scope creep is the failure mode.
- **Treat tool security as non-negotiable from day one.** A production survey found only 8.5% of public MCP servers implement OAuth; 53% rely on static API keys. Each tool is a potential privilege escalation path. Authenticate both the agent and the human behind it.

## Evidence

- **arXiv Survey:** Tool-calling performance degrades significantly beyond small tool sets; MCP ecosystem has grown to 13,000+ public servers (arXiv:2503.23278v2, April 2025) — [https://arxiv.org/html/2503.23278v2](https://arxiv.org/html/2503.23278v2)
- **Benchmark Data:** GPT-4o scores 28% on the NESTFUL benchmark (chained API calls with multiple tools); Berkeley Function Calling Leaderboard shows up to 96% accuracy on individual tool calls (Tian Pan, April 2026) — [https://tianpan.co/blog/2026-04-13-tool-explosion-problem-agent-tool-selection-at-scale](https://tianpan.co/blog/2026-04-13-tool-explosion-problem-agent-tool-selection-at-scale)
- **HN Discussion:** OpenAI deprecated the Assistants API in favor of MCP (March 2025 HN thread, 389 points); single chat-completion-API-with-structured-outputs remains preferred by developers who want control over state management — [https://news.ycombinator.com/item?id=43334644](https://news.ycombinator.com/item?id=43334644)
- **Primary Source:** YC built 350+ tools over 18 months but routes them through a hierarchical skill system — finance queries hit the finance tool set, legal queries hit legal. The agents never see the full registry. The "key unlock" was granting agents direct Postgres access. (YC Lightcone Podcast, May 2026) — [https://www.youtube.com/watch?v=B246K_G7mHU](https://www.youtube.com/watch?v=B246K_G7mHU)
- **Production MCP Security:** 53% of public MCP servers use static API keys; only 8.5% implement OAuth. Security audit of remote MCP deployments documented one-click account takeover vulnerabilities from mishandled OAuth consent flows (metacto, 2026) — [https://www.metacto.com/blogs/building-mcp-servers-production-ai-agents](https://www.metacto.com/blogs/building-mcp-servers-production-ai-agents)
- **Browser Tools:** Claude Computer Use leads on task success; OpenAI Operator leads on consumer UX; Browser Use (open-source) leads on cost and developer control. All three still fail regularly on multi-tab and OAuth flows. Claude Computer Use is no longer beta as of early 2026. (Web3AIBlog, May 2026) — [https://www.web3aiblog.com/blog/browser-agents-battle-operator-vs-claude-computer-use-vs-browser-use-may-2026](https://www.web3aiblog.com/blog/browser-agents-battle-operator-vs-claude-computer-use-vs-browser-use-may-2026)

## Gotchas

- **Tool descriptions eat context before the query arrives.** Run the math: count all the tokens in your tool schemas. At 37 tools you're already over 6,000 tokens of overhead before the user says anything.
- **Context pollution from complex parameter schemas is invisible.** A 28-parameter tool definition doesn't feel heavier than a 3-parameter one in your code, but it generates 17x more schema tokens. Measure actual prompt lengths, not just tool counts.
- **MCP tool discovery is dynamic — that's both a feature and a trap.** Agents can discover capabilities at runtime, but that means a tool added to a server becomes available immediately. If you haven't gated it, it's accessible.
- **Function calling schemas are provider-specific.** OpenAI's tool schema format differs from Anthropic's. MCP's provider-agnostic approach solves this at the protocol level, but if you're using function calling directly, schema migration is a real cost when switching models.
- **Browser use looks ready until it isn't.** The 2026 browser agent landscape (Claude Computer Use, OpenAI Operator, Browser Use) is genuinely more capable than 2024 — but multi-tab coordination and OAuth flows remain open failure modes. Don't deploy browser tools on flows that require session continuity without guardrails.
