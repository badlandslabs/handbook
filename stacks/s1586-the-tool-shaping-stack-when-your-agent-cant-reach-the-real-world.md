# S-1586 · The Tool Shaping Stack — When Your Agent Can't Reach the Real World

Your agent is smart. It reasons well, plans well, and decides correctly. But it has no way to act on any of it. The tools you gave it are wrong — too narrow, too broad, or shaped in a way that doesn't match how the world actually works. This is the tool shaping stack — how to give agents capabilities that transfer to real environments.

## Forces

- **Reach vs. risk** — a tool powerful enough to solve complex tasks is powerful enough to cause catastrophic damage; every capability is also a blast radius
- **Interface fidelity** — browser agents fail not because the LLM misunderstands the page, but because the model reasons from stale state between observation and action (modal appeared after screenshot, autocomplete covered the target element)
- **The sandbox paradox** — code execution is the most valuable tool for an agent; it's also the most dangerous; Docker containers and WASM sandboxes reduce the risk but add latency and complexity that degrades agent performance
- **MCP as the lingua franca, not a solution** — MCP (Model Context Protocol, from Anthropic, November 2024) standardized tool interfaces across AI vendors; by mid-2026 every major AI provider ships production MCP surfaces, but the protocol handles *how* tools communicate, not *what* tools should exist or how they should be secured
- **Tool proliferation is the path of least resistance** — agents accumulate tools over time; the HN-MCP server (a single tool for searching Hacker News) exists, and so does every other domain-specific thing, leading to bloated tool sets that confuse the agent's routing

## The move

**Design tools around the agent's failure modes, not just its happy paths.**

- **Browser tools: freeze state, don't capture it.** The Agent Browser Protocol (ABP) freezes JavaScript execution and rendering after every action, capturing a coherent DOM snapshot instead of a stale one. Browser4 (an open-source browser engine built on native CDP) redesigned its architecture around agent-first concurrency. Browser Use (106K GitHub stars, #1 on Odysseys leaderboard at 87.4% average) uses Playwright under the hood but adds structured element extraction — numbered interactive elements that reduce token volume vs. full-page screenshots. WebMCP (shipped in Chrome 146, February 2026) promises 89% token efficiency over screenshot-based approaches by exposing a structured browser interface. Choose your abstraction level based on your latency budget, not your model's capability ceiling.

- **Code execution: constrain before you ship.** The Amla Sandbox (WASM-based, ~11MB binary) uses capability-based security — the agent can only call tools explicitly provided by the host, with no ambient authority. Compare to Docker-based sandboxes (agentvm's full Linux VM approach, 173MB) or bare subprocess execution. The AWS Kiro incident (December 2025: an AI coding assistant with operator-level access deleted a production Cost Explorer environment, causing a 13-hour outage) crystallizes what happens when code execution tools lack hard constraints. Every code execution tool needs: explicit capability grants, not ambient access; confirmation gates for destructive operations; hard resource limits (CPU time, memory, network egress); and execution audit trails.

- **MCP servers: scope tightly, secure loudly.** MCP standardized the tool interface, but production deployments require more. Cisco's Catalyst Center integration with ServiceNow via MCP shows enterprise-grade patterns: authentication (OAuth 2.0), rate limiting, authorization layers, and monitoring. Manufact (YC S25, formerly mcp-use) positions itself as "Vercel for MCP" — a cloud platform for shipping, iterating, testing, and monitoring MCPs in production with per-tool analytics. The NSA published MCP security design considerations (May 2026) flagging CVE-2025-49596 in MCP-Inspector as a cautionary tale — a toolchain component that accepted unverified inputs, enabling RCE. The lesson: every MCP server is a network-exposed service with LLM-granted capabilities.

- **The minimum viable tool set.** For most agents: (1) a web search/browse tool — real-time information the model's training cutoff can't provide; (2) a code execution sandbox — for tasks the model needs to verify through running code; (3) a file system tool — scoped to a working directory, not the whole filesystem; (4) a structured data retrieval tool — database query or API call for domain-specific data. Every additional tool beyond these four should justify its existence with a concrete use case, not "it might be useful someday."

- **Tool descriptions are prompts.** The model's ability to route to the correct tool depends entirely on the description, parameters, and return type specification. Under-specified tools get called with wrong parameters; over-specified tools create bloated context. Keep descriptions to one or two sentences of behavioral intent, not implementation details.

## Evidence

- **GitHub / Benchmark:** Browser Use — 106K stars, #1 on Odysseys leaderboard (87.4% average on 200 long-horizon web tasks), open-source benchmark repo at github.com/browser-use/benchmark — [https://github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **HN / Architecture:** Agent Browser Protocol (ABP) — freezes JS execution and rendering after each action to solve stale-state failures; 155 HN points — [https://news.ycombinator.com/item?id=47336171](https://news.ycombinator.com/item?id=47336171)
- **HN / Show HN:** Amla Sandbox — WASM bash shell sandbox for AI agents, capability-based security model, 146 HN points — [https://news.ycombinator.com/item?id=46824877](https://news.ycombinator.com/item?id=46824877)
- **Blog / Incident:** AWS Kiro production deletion — December 2025, agent with operator-level access deleted Cost Explorer production environment, 13-hour outage; Docker's post-mortem analysis of the incident — [https://www.docker.com/blog/coding-agent-horror-stories-the-agent-that-deleted-production/](https://www.docker.com/blog/coding-agent-horror-stories-the-agent-that-deleted-production/)
- **Product / MCP Cloud:** Manufact (YC S25) — MCP deployment cloud platform, "Vercel for MCP"; open-source SDKs at github.com/mcp-use/mcp-use — [https://news.ycombinator.com/item?id=48762862](https://news.ycombinator.com/item?id=48762862)
- **Government / Security:** NSA MCP Security Design Considerations (May 2026) — CVE-2025-49596, MCP-Inspector RCE, enterprise security guidance — [https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf](https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf)
- **Enterprise / Case study:** Microsoft mcp-for-beginners case studies — Azure AI Travel Agents multi-agent architecture, GitHub MCP Registry — [https://github.com/microsoft/mcp-for-beginners/blob/main/09-CaseStudy/README.md](https://github.com/microsoft/mcp-for-beginners/blob/main/09-CaseStudy/README.md)
- **Research:** Zylos 2026 browser automation landscape — Playwright 78.6K stars, 45.1% QA adoption, WebMCP in Chrome 146, Google Mariner 83.5% WebVoyager success rate — [https://zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape](https://zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape)

## Gotchas

- **Screenshot-based browser tools are expensive and brittle.** A 1920×1080 screenshot at reasonable compression still costs 30–50K tokens; extract structured elements instead. WebMCP in Chrome 146 addresses this natively, but most production systems still use Playwright screenshots.
- **Code execution sandboxes add latency that breaks agent loops.** WASM sandboxes (Amla: ~11MB, fast startup) beat Docker containers (agentvm: 173MB, slower) for multi-step tasks where the agent needs rapid feedback. But WASM's syscall surface is small — if your agent needs `curl`, `git`, or `pip`, you need a larger sandbox.
- **MCP server proliferation creates routing confusion.** Agents with 20+ tools make worse routing decisions than agents with 4. Group related tools under a single MCP server with a descriptive name, and let the agent discover sub-tools through the server's interface.
- **Tool descriptions rot.** When an upstream API changes, the tool description and parameter schema often don't. Add a tool self-test to your CI pipeline: call the tool with minimal valid input and verify the schema still matches the response.
- **Remote MCP servers are network-exposed services.** A tool that can query your database or send emails is a network service. Treat it like one: TLS, authentication, rate limiting, and input validation are not optional.
