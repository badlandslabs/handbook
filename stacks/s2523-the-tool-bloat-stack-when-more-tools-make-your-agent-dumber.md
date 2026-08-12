# S-2523 · The Tool Bloat Stack — When More Tools Make Your Agent Dumber

Your agent has 47 MCP tools. It should be capable. Instead it's slower than the agent with 3, and it hallucinates function calls to tools it doesn't have. Adding tools broke your agent. This is the tool bloat problem: the gap between "what an agent can theoretically do" and "what it can actually reason about."

## Forces

- **Capability temptation beats capability discipline.** Every team starts with "give the agent access to everything" — it's the obvious move. The cost is invisible until production.
- **Context is the bottleneck, not intelligence.** Anthropic's own engineering blog documents that loading all tool definitions upfront is the primary driver of token overhead in MCP-based agents — and that overhead directly degrades planning quality.
- **Tool proliferation is cheap; tool comprehension is expensive.** Publishing an MCP server takes hours. Getting an agent to reliably select the right tool from a large set takes systematic design.
- **Remote MCP servers multiply blast radius.** MCP Manager data shows company-operated MCP servers grew 232% from August 2025 to February 2026. More servers means more tools, means more definitions loaded per request.
- **The 97M/month SDK downloads metric hides the coordination problem.** MCP adoption is real — but adoption of *tool discipline practices* has not kept pace.

## The move

Curate tool sets strategically, not comprehensively. The goal is not maximum capability — it is minimum viable capability with maximum reliability.

- **Segment tools by phase, not by function.** Don't give the agent all 47 tools at once. Partition tools into task-phase sets (discovery tools, execution tools, validation tools) and load only the relevant partition per step.
- **Use lazy loading with semantic routing.** Anthropic's recommended approach: keep a tool manifest, run a lightweight LLM call to identify which 2-3 tools are relevant to the current subtask, then load only those tool definitions. This cuts token overhead by ~60–80% for large tool sets (benchmarked in their engineering blog).
- **Enforce a tool cap per agent tier.** Set explicit limits: tier-1 agents get ≤5 tools, tier-2 gets ≤15, tier-3 (supervisor) gets ≤30. Above the cap requires explicit justification and review.
- **Name tools for disambiguation, not description.** A tool named `gdrive.getDocument` forces the model to read the description. A tool named `fetch_file_from_drive` or `read_google_doc(doc_id)` is self-describing. Invest in naming as a design decision.
- **Instrument tool call success rates per tool.** Track which tools get called with wrong arguments, hallucinated, or skipped. Tools with <80% call accuracy are either poorly named, poorly scoped, or poorly described — fix or remove them.
- **Implement tool grouping at the MCP server level.** Group related tools under a single parent call. Instead of 8 individual database tools, expose one `database.query()` tool that accepts a structured sub-command. Reduces the agent's combinatorial surface.

## Evidence

- **Engineering blog:** Anthropic documented the token consumption problem with MCP at scale — tool definitions and intermediate results consuming context — and recommended lazy loading with routing as the primary mitigation. Their code execution blog benchmarks show significant token savings when routing reduces the active tool set. — [Anthropic Engineering: Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Adoption data:** MCP SDK downloads grew from ~100K/month at launch (November 2024) to 97M+/month by December 2025, with 13,230+ public MCP servers. Company-operated servers grew 232% over 6 months — tool proliferation is accelerating. — [OpenClaw: MCP Examples](https://openclaw.direct/mcp-guide/model-context-protocol-examples)
- **Production deployment guide:** The 2026 production deployment guide documents the supervisor-worker pattern — subdividing tools across specialized sub-agents — as the recommended approach to managing tool complexity in multi-agent systems. — [Dev Note: AI Agents in Production](https://devstarsj.github.io/2026/03/17/ai-agents-production-deployment-guide-2026/)

## Gotchas

- **Loading tools lazily adds latency.** The routing LLM call itself costs time and tokens. Benchmark the overhead against the savings before committing.
- **Tool grouping can hide failures.** If `database.query()` swallows errors silently, you lose visibility into which sub-operation failed. Surface error context at the group level.
- **Context-window limits create a false ceiling.** Teams often assume "we have plenty of context" and skip tool curation, then hit wall at 128K tokens. By then the tool set is entrenched and hard to refactor.
- **Notion, Figma, and Block all expose MCP servers for their platforms** — the tool proliferation isn't hypothetical. Production agents are already integrating across these. The discipline problem is here now.
