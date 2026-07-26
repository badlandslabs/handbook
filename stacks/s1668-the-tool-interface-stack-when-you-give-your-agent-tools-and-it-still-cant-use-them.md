# S-1668 · The Tool Interface Stack — When You Give Your Agent Tools and It Still Can't Use Them

You wired up an MCP server. You exposed 40 tools. The agent has everything it needs — except it keeps calling the wrong tool, calling tools at the wrong step, or burning half its context window on tool definitions before it even starts working. The problem isn't the tools. It's the interface between the agent and the tools.

## Forces

- **Tool definitions are expensive.** Every tool description, schema, and result payload competes for the same finite context window as your actual task. With 40 tools at ~500 tokens each, you've already spent 20K tokens before the agent does anything useful (Anthropic, "Code execution with MCP," Nov 2025).
- **Tool selection degrades with scale.** Agent performance on tool selection holds up at 10–20 tools but drops sharply above 100, even with high-quality descriptions (Anthropic, internal eval data cited in production agents writeup, 2025).
- **Interface design is the contract.** A tool's description, parameters, and output schema are the agent's only signal for knowing when to call it, with what arguments, and what to do with the result. Hand-crafted descriptions vary wildly in quality; auto-generated ones from observed API behavior are consistently more reliable (Frigade HN Show HN, 96 points, 2025).
- **Lazy loading vs. eager loading.** Most MCP clients load all tool definitions into context upfront. This was acceptable at 10 tools; at 100+ tools it becomes the primary bottleneck.

## The Move

Three-layer architecture: expose, describe, route.

**Layer 1 — On-demand tool exposure (not all-at-once loading):**
- Use MCP's capability announcement pattern: agent first queries what tools are available, then loads only the ones it plans to use.
- Anthropic measured **98.7% token reduction** by deferring tool definition loading instead of passing all definitions at every step (Anthropic, "Code execution with MCP," Nov 2025).
- For dynamic tool registries, surface a lightweight capability index first — the agent reads descriptions and requests specific tool manifests on demand.

**Layer 2 — High-signal tool interface design:**
- Every tool gets a `purpose` field: one sentence stating the action, the object, and the expected effect. Not "searches documents" but "finds the most recent customer support ticket matching a ticket ID."
- Use observed behavior to generate schemas, not assumptions. Frigade demonstrated auto-generating MCP recipes by watching a browser app make API calls — capturing the endpoint, auth flow, response schema, and input schema from live traffic rather than reverse-engineering from docs (HN Show HN, pancomplex, 2025).
- Browser-use (106K GitHub stars, MIT license) uses a task description model: user says "apply to these 50 jobs on LinkedIn" and the agent figures out which web interaction tools to use — because the tool interface is task-goal framing, not a fixed list of URL/click operations (browser-use GitHub README, 2025).

**Layer 3 — Tool routing at scale:**
- Below 20 tools: let the LLM select from inline descriptions — quality descriptions are sufficient.
- 20–100 tools: embed tool descriptions in a lightweight retrieval index. Agent queries the index, gets top-K candidates, then decides.
- Above 100 tools: add a dedicated tool-routing model or classification step before the main agent loop. Anthropic's production agent work found that even frontier models degrade on selection accuracy above 100 tools without a retrieval scaffold.

## Evidence

- **Anthropic engineering blog (Nov 2025):** Code execution with MCP — quantified token overhead of naive tool loading, demonstrated 98.7% token reduction via on-demand loading, coined the "capability announcement" pattern for tool exposure. — https://www.anthropic.com/engineering/code-execution-with-mcp
- **GitHub browser-use repo (MIT, Magnus Müller & Gregor Žunič, 2024–2025):** 106K stars, 11K forks. Task-framing tool interface: describe goal → agent selects web interaction primitives. Primary use cases: form filling, data extraction, QA automation. — https://github.com/browser-use/browser-use
- **HN Show HN, Frigade (2025, 96 pts):** Auto-generated MCP recipes from observed browser API calls. Captures endpoint + auth + schemas from live traffic, produces LLM-callable tools without manual schema writing. — https://news.ycombinator.com/item?id=48847834
- **Anthropic Applied AI team (YouTube, 2025):** Production deployment data showing tool selection accuracy degrades above 100 tools; routing scaffolding becomes necessary at scale. — https://www.zenml.io/llmops-database/building-production-ai-agents-lessons-from-claude-code-and-enterprise-deployments

## Gotchas

- **Overly verbose tool descriptions.** Each tool description competes for context budget. If your `purpose` field is three sentences, you've defeated the efficiency gain from lazy loading.
- **Static schemas vs. live schemas.** Hand-written OpenAPI specs go stale when the underlying API changes. Auto-generation from observed behavior (Frigade's approach) or schema introspection (if the API supports it) keeps schemas in sync.
- **Tool result passthrough.** Don't dump full tool responses into the agent context. Summarize or truncate results — the agent needs the signal, not the entire payload. Anthropic's MCP code execution article specifically calls out intermediate result passing as a token overhead multiplier.
- **Auth is part of the tool interface.** Browser-based tools especially need auth lifecycle handling (token refresh, cookie persistence). Frigade bakes this into recipes; most hand-crafted tool definitions forget it entirely.
