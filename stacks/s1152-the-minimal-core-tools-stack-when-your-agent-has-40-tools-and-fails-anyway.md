# S-1152 · The Minimal Core Tools Stack — When Your Agent Has 40 Tools and Fails Anyway

The MCP ecosystem lets you wire up 200+ tools in an afternoon. Your agent can query your database, post to Slack, browse the web, send emails, run Python, check GitHub, read Google Drive, call your CRM, query your vector store, execute shell commands, and 193 more things. Then it sits there failing on basic tasks. The problem is not the number of tools. The problem is that you gave an agent tools without understanding what makes a tool actually work for an agent versus a developer.

## Forces

- **Tool proliferation is the path of least resistance.** It's easy to connect more tools. It's hard to design tools that agents can reliably use. Teams default to quantity because quantity is measurable and feels like progress.
- **The tool contract is different from the API contract.** Traditional APIs assume a deterministic caller who follows the docs. Agentic tools assume a non-deterministic caller that might hallucinate, misinterpret, retry, or give up. Writing tools for agents requires a fundamentally different design philosophy.
- **Every tool you add costs the agent attention budget.** A 5-server MCP setup with 40 tools can consume 72,000+ tokens in tool definitions alone (Anthropic, Sep 2025). The model has less room to reason about the actual task, and more surface area for tool-selection errors.
- **Real production agents converge on the same 4 tools.** Not because those are the only things that matter, but because those four tools are the ones that are well-designed enough for agents to use reliably.

## The Move

The insight from production deployments: most agents succeed with a minimal core tool set, and the ones that fail have either too many tools or poorly designed ones. The move is to design your tool surface deliberately — few tools, high signal, built for non-deterministic callers.

**The four tools that ship in production:**

- **Web search** — real-time information retrieval. Tavily ($25M raised) and similar AI-native search APIs are specifically designed to return structured, source-attributed results that survive token-limited contexts. Traditional Google search API returns SEO-optimized HTML; Tavily returns LLM-ready summaries with citations. The difference is whether the agent can actually use the result.

- **Read/write files** — the universal interface for structured data. Agents that can read and write files (JSON, CSV, markdown) can interoperate with every other system without custom integrations. The pattern that works: return structured data through the file tool, let the agent process it in subsequent steps.

- **Bash / code execution** — the tool that closes the loop. After the agent reasons, it needs to act. Bash with a sandbox (as in SWE-agent's SWE-ReX, which powers Ramp's SWE-bench) lets agents run tests, execute scripts, and verify their own output. SWE-agent solves this with three focused tools — `view_file`, `edit_file`, `run_tests` — and scores >74% on SWE-bench verified with a 100-line Python implementation.

- **Search (codebase or document)** — the tool for working with large information spaces. Full-text or semantic search over your codebase, documentation, or data corpus gives the agent working memory beyond its context window. LlamaIndex and Qdrant are the common stack components.

**Beyond the four, route by delegation, not expansion:**

When a task genuinely needs a specialized tool (Salesforce API, Stripe integration, custom DB), the right pattern is not to add it to your agent's tool surface directly. Route it: have the agent write a plan, delegate the specialized task to a downstream system, and receive structured results. Anthropic calls this the **orchestrator-evaluator** pattern. The agent orchestrates; the specialized system acts.

**Tool design principles that matter:**

1. **Self-descriptive schemas.** Tools for agents need flat, well-named parameters with concrete examples in descriptions. `search(query: str, limit: int = 5)` is nearly useless to an agent. `search(query: str, limit: int = 5)` with a description explaining when to use `limit=5` vs `limit=20` and what the output schema looks like is actionable.

2. **Structured output, always.** Never return raw HTML or unstructured text. Return JSON with a defined schema. AlterLab's HN agent example demonstrates the principle: the agent never sees an HTML tag. It asks for a list of posts, gets a JSON array. The infrastructure handles extraction; the agent operates on structured data.

3. **Graceful degradation.** Tools for agents must handle partial success. The agent calls `run_tests` and 3 of 10 tests fail — that's an actionable result, not an error. The tool should return structured results that let the agent decide whether to iterate.

4. **Let the agent write the tools.** Anthropic's Sep 2025 post describes using Claude to optimize its own tool definitions. The agent identifies failure patterns in tool usage, rewrites the tool schema and description, and re-tests. This self-improvement loop produces better tools than hand-written documentation.

## Evidence

- **Anthropic Engineering:** "The tools that are most 'ergonomic' for agents also end up being surprisingly intuitive to humans" — and their recommended starting point is **few, well-designed tools**, not large tool surfaces. Their "Building Effective AI Agents" (Dec 2024) states teams using "simple, composable patterns rather than complex frameworks" consistently outperform those using elaborate tool stacks. — https://www.anthropic.com/engineering/building-effective-agents

- **Anthropic Engineering:** "Agents are only as effective as the tools we give them" — detailed workflow for building tools that agents can actually use, including self-improving tool definitions where the agent rewrites its own tool schemas. A 5-server MCP setup with 40 tools can consume 72K+ tokens in definitions alone. — https://www.anthropic.com/engineering/writing-tools-for-agents

- **SWE-agent / Princeton NLP:** Mini-SWE-agent achieves >74% on SWE-bench verified with 3 focused tools (`view_file`, `edit_file`, `run_tests`) in 100 lines of Python. Powers Ramp's production SWE-bench evaluation. The README explicitly states the design philosophy: "radically simple, no huge configs, no giant monorepo." — https://github.com/SWE-agent/mini-swe-agent

- **AlterLab HN Agent:** "Never feed raw HTML into your LLM context window. It destroys your token budget and degrades model reasoning. Define strict JSON schemas for your tool calls. Force the infrastructure to handle the extraction." Production pattern from an agent that queries HN data. — https://alterlab.io/blog/how-to-give-your-ai-agent-access-to-hacker-news-data

- **Hacker News Discussion (543 points):** Community consensus in the thread on Anthropic's agent post: direct API usage beats framework abstractions for tool calling, and agents need "guardrails" to prevent infinite loops — the failure mode of giving agents too much autonomy with too many tools. — https://news.ycombinator.com/item?id=44301809

## Gotchas

- **Adding a tool feels like progress; it isn't.** Connecting a new MCP tool produces a visible artifact. Designing a tool so the agent can reliably use it requires iteration, testing, and often rewriting the schema. Teams optimize for the visible artifact.
- **Raw output from legacy APIs is poison to agents.** Returning unparsed HTML, API response bodies, or log files directly into the context window degrades agent reasoning. Always add an extraction layer between external systems and your agent.
- **The sandbox is not optional for code execution.** Agents that can run shell commands without sandboxing will eventually run destructive commands. SWE-ReX, Claude Code, and Jules all use sandboxed execution for a reason.
- **Tool count and tool quality are inversely correlated in practice.** The more tools you add, the less attention the model has for each one. Teams with 40+ tools almost always have shallow tool definitions. Teams with 4 tools have deep ones.
