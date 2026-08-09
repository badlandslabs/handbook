# S-2395 · The Tool Routing Stack — When Fifty Tools Become One More Problem Than Solution

You built a capable agent. Then you added tools: email, calendar, CRM, search, code execution, a dozen MCP servers. Now it has 60 tools and two things go wrong simultaneously — it picks the wrong one, and the token bill for loading all those definitions on every turn rivals your actual API costs. The tool selection problem isn't about descriptions or hallucinations. It's a retrieval and routing architecture problem that emerges at a specific scale, and most teams discover it only after they've already shipped.

## Forces

- **Tool selection accuracy degrades on a cliff, not a slope.** Research from the Berkeley Function Calling Leaderboard (109 models tested, V4 with holistic agentic evaluation) shows that accuracy holds at 90–95% for 5–10 tools but drops to 40–60% at 500+ tools. The transition between 20 and 200 tools is where most production systems live — and that's precisely where the accuracy curve steepens.
- **Dumping all tools into context causes two simultaneous failures.** Every tool definition carries a name, description, parameter schema, and usage hints. With 58 tool definitions, this overhead reaches ~55,000 tokens per turn (per internal testing reported across multiple practitioner reports). The model degrades on selection because it's reasoning over noise, and the cost compounds on every single call.
- **Tool selection is brittle to description phrasing, independent of model capability.** Changing "Retrieve current weather" to "Get current weather" can shift selection probabilities enough to alter routing decisions. LLMs lack true understanding of tool capabilities — they pattern-match descriptions against queries, which makes routing fragile to surface-level edits.
- **MCP schema drift is structural, not accidental.** MCP servers evolve independently from workflow agents. When a server changes a tool's response schema, agents silently start failing because they expected the old shape. This isn't an edge case — it's the default state for any production system with external dependencies.

## The move

**A two-stage routing architecture: semantic retrieval to narrow, then LLM to pick.**

- **Stage 1 — Embed and retrieve relevant tools.** Register each tool with an embedding of its name, description, and parameter schema. At runtime, embed the user query and do cosine-similarity retrieval against the tool corpus. Return the top-K most semantically similar tools. Bloomberg's production implementation reduced unnecessary tool calls by 70% using this approach.
- **Stage 2 — LLM selects from the narrowed set.** After retrieval, the LLM picks from 5–15 tools rather than the full catalog. At this scale, in-context selection accuracy returns to 85–90%. The routing layer handles the 50-tool problem; the LLM handles the 5-tool decision.
- **Filter on tool metadata, not just semantic similarity.** Weight retrieval by tool reliability scores, latency estimates, and cost — not just semantic match. A semantically close tool that's frequently unavailable or slow should rank lower than a slightly less precise but more reliable alternative.
- **Schema registry with automated validation.** Maintain a snapshot of every tool's current parameter schema and response shape. On every schema change detected (via MCP server version pings or scheduled diffing), run a validation suite that exercises the tool with known inputs and flags shape mismatches before they silently corrupt agent reasoning.
- **Graceful degradation when retrieval returns nothing.** When semantic retrieval surfaces no strong candidates, fall back to a minimal "capability not found" response rather than letting the LLM hallucinate a tool. Do not fall back to dumping the full catalog — that's the problem you're solving.
- **Monitor per-tool selection accuracy, not just call success.** Track how often each tool is selected, what the retrieval rank was when it was selected, and whether the call ultimately succeeded. Tools that are frequently retrieved but never selected may have description mismatches. Tools that are selected frequently but fail may have schema drift.

## Evidence

- **Research benchmark:** The Berkeley Function Calling Leaderboard V4 evaluates 109 models across tool use accuracy, native function calling support, multi-turn interactions, and holistic agentic evaluation. Their data confirms selection accuracy degrades sharply beyond 20–50 tools — [BFCL Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html), [BFCL Blog](https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html)
- **Production cost data:** Tool definitions cost 200–500 tokens each. At 500 tools, that's 200K+ tokens per request (~3–5s inference, ~$45K/month). Optimizing to 10 tools reduces inference to ~400ms and cost to ~$900/month — [ML & AI in Action: Tool Selection Optimization for LLM Agents at Scale](https://ajing.github.io/posts/2026-01-10-tool-selection-optimization-llm-agents-at-scale/)
- **Enterprise case study:** Bloomberg's agent team achieved a 70% reduction in unnecessary tool calls through routing optimization — cited in [ML & AI in Action](https://ajing.github.io/posts/2026-01-10-tool-selection-optimization-llm-agents-at-scale/) and corroborated by multiple practitioner reports on tool catalog management
- **Failure taxonomy:** Production tool call failures break into three categories: infrastructure failures (1–5%, retryable), schema/interface failures (semi-transient, require schema remediation), and semantic failures (agent picked wrong tool or misinterpreted result — requires task decomposition or human escalation). Only the first category benefits from naive retry loops — [AgentMarketCap: Agent Tool Call Failures in Production 2026](https://agentmarketcap.ai/blog/2026/04/10/agent-tool-call-retry-failure-mode-handling-production-2026)

## Gotchas

- **Description sensitivity will bite you in production.** The same tool with a renamed description can shift routing behavior. Treat tool descriptions as code — version them, review them, and run selection accuracy regressions when you change them.
- **Semantic similarity ≠ tool correctness.** A retrieved tool can be semantically plausible for the query but operationally wrong (e.g., "send email" and "send invoice" both look correct for "please notify the customer"). Use retrieval as a narrowing step, not a final decision.
- **Schema drift monitoring is easy to skip and expensive to discover.** The moment an MCP server pushes a breaking change, every agent that calls it starts producing garbage — silently, with no error signal. Implement snapshot-diffing in CI and runtime validation in the tool wrapper layer.
