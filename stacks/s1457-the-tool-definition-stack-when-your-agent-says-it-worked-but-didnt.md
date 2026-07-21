# S-1457 · The Tool Definition Stack — When Your Agent Says It Worked But Didn't

You gave your agent a browser, a code executor, and a search tool. The demo worked. The agent returned a confident, well-formatted response. The tool never fired. This is the tool definition failure mode — the most common and least-detected class of agent bug in production, and most teams have no idea it is happening to them.

## Forces

- **Tools look like plumbing, but they are the reasoning boundary.** The model's world is bounded by what it can call. A misdescribed tool is a wall the agent walks into confidently.
- **Step reliability compounds.** A 95% reliable tool × 10 steps = 60% task reliability. Most teams benchmark individual tool accuracy (often 97–99%) and miss that compound failure is inevitable at scale.
- **Silent failures look identical to success.** An agent that returns a polished summary after a failed tool call is worse than one that crashes — the crash gets noticed and fixed.
- **The MCP ecosystem solved integration but multiplied the blast radius.** 13,000+ MCP servers means agents can reach everything. Teams gave agents everything. Now they are debugging which of seventeen tool integrations is silently failing.
- **Browser automation exposes the deepest race condition.** The web is async and event-driven; agents are synchronous and step-based. Most browser-agent failures are not model failures — they are stale-state failures.

## The move

**Design tools as a contract, not a wrapper.** The tool definition is the agent's model of reality. Bad definitions create agents that fail confidently.

**1. Write tool descriptions that encode the output shape, not just the purpose.**
Instead of "search the web for information," write: "returns a JSON array of up to 10 results, each with {title, url, snippet}. Returns empty array on no results. Never returns raw HTML."
The agent reasons from the description. If the description says "returns results," it assumes success.

**2. Make failure modes explicit in the tool schema.**
If a tool can fail silently (network timeout, auth expiry, partial write), encode the failure response in the schema. The model should receive `{"error": "auth_expired", "retry": false}` — not a 200 with missing data.

**3. Validate arguments before the call, not after.**
Agent-generated arguments are the primary failure mode. A `search` tool that expects `{"query": "string", "limit": "integer ≤ 10"}` should validate before executing, not return a 400 from the downstream API and hope the agent retries correctly.

**4. Instrument the tool call boundary, not just the tool.**
The critical observability point is: tool called → tool returned → agent read result. Most agent observability stops at "tool called." You need all three.

**5. Give the browser agent a synchronized state channel, not a screenshot pipeline.**
Async web pages + sync agents = stale state. ABP (Agent Browser Protocol) freezes JavaScript execution and rendering after each action, returning a deterministic state snapshot. For non-forked approaches: use CDP pause-on-events before capture, or accept that screenshots-after-actions will be wrong 20–30% of the time.

**6. Sandbox code execution by default, always.**
Agents writing code is not optional in most production stacks. E2B, Modal, Google Vertex Code Execution, and similar services provide isolated containers. The question is not whether to sandbox — it is whether the sandbox startup time is acceptable for your latency budget.

## Evidence

- **HN Show HN:** The Agent Browser Protocol project (155 points, 55 comments) identified the core failure mode: "Most browser-agent failures aren't about the model misunderstanding the page — the model is reasoning from stale state." They built a Chromium fork that freezes JS execution between agent actions and browser capture, achieving 90.53% on the Online Mind2Web benchmark with 2× lower token usage vs Playwright MCP. — [HN Thread](https://news.ycombinator.com/item?id=47336171) | [Repo](https://github.com/theredsix/agent-browser-protocol)
- **Engineering post:** AgentMarketCap documented "silent tool call failures" as the #1 production issue in 2026: "Your agent pipeline returned HTTP 200. Every status check is green. And yet a CRM record was never updated." Compounding math: 95% single-tool reliability × 10 steps = 46% task reliability for a 15-step workflow. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/11/function-calling-reliability-production-agents-2026)
- **DEV Community:** The four-layer eval framework for tool-using agents distinguishes tool selection accuracy (what most benchmarks measure) from argument correctness, execution correctness, and recovery correctness. "Tool selection passes at 1.0 accuracy when the right function name shows up in the trace, completely blind to whether the arguments were garbage." — [DEV Community](https://dev.to/nikhil_pareek_13/tool-call-accuracy-is-lying-to-you-a-four-layer-eval-stack-for-agents-523p)
- **MCP ecosystem data:** 13,230+ public MCP servers as of March 2026, 97M+ monthly SDK downloads. Fleet management commands (list instances, check health) account for the majority of MCP tool calls in production. Multi-server orchestration (GitHub + Slack + Linear chained) is the real value unlock — and the real blast radius. — [OpenClaw](https://openclaw.direct/mcp-guide/model-context-protocol-examples)

## Gotchas

- **"Tool accuracy" benchmarks are measuring the wrong thing.** Tool selection accuracy (did the agent pick the right function?) is not the same as task completion accuracy. A model can have 99% tool selection and 40% task completion.
- **HTTP 200 is not success.** Many tool failures return 200 with partial or missing data. Check the schema of the response body, not the HTTP status code.
- **Retries without input change are loops.** If a tool call fails and the agent retries with the same arguments, the retry will fail again. The agent needs to either mutate the input or stop. Most retry policies do not enforce this.
- **MCP servers multiply your blast radius without multiplying your observability.** Each MCP server is a new failure mode. Adding a GitHub MCP integration means your agent can now fail because of rate limits, token expiry, webhook timing, and repo state — none of which your agent's error handling likely covers.
- **Tool descriptions drift from tool behavior.** When a backend API changes its response schema, the tool description becomes a lie. Without schema-version tracking, the agent operates on a stale model of reality with no indication that anything is wrong.
