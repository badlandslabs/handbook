# S-1405 · The Agent Tooling Stack — What You Give Your Agent and What It Costs You

An agent without tools is a very expensive autocomplete. Give it the wrong tools, or give it too many, and you have a different problem: runaway cost, silent failures, or a credential exfiltration incident you didn't see coming. The tooling decisions — what to give agents, how to connect them, and how to contain them — are where production agent systems live or die.

## Forces

- **The N×M integration problem** — connecting N agents to M tools naively requires N×M integrations. MCP (Model Context Protocol) collapses this to N+M, but introduces its own token and discovery costs
- **API function calling beats vision-based control in most cases** — Computer Use / browser automation is 3× slower and costs more, but the flexibility advantage is real for cross-application workflows
- **LLM output is untrusted input** — code-generation agents produce code that must be treated as input from a stranger on the internet; default isolation is not enough
- **Token cost of tooling is non-obvious** — MCP tool definitions for 58 tools consumed ~55K tokens in a real Anthropic production case, and their worst-case measurement hit 134K tokens before optimization
- **The MCP ecosystem is real but uneven** — 5,000+ MCP servers exist, but community servers are untested and largely unvetted

## The move

**Layer your tool stack from most constrained to least, with containment at every boundary.**

1. **Standardize on MCP as your tool bus.** Anthropic released it late 2024, OpenAI adopted it in March 2025, and Google DeepMind followed in April 2025 calling it "rapidly becoming the open standard for the AI agentic era." One protocol, any agent, any tool. Configure the MCP server once; any compatible client uses it. The tool bus pattern eliminates per-agent-per-tool plumbing.

2. **Give browsers via Playwright MCP, not screen-scraping.** The Playwright MCP server from Microsoft gives agents screenshot, click, fill, and navigation capabilities through a single configuration block. browser-use (MIT licensed, open-source) extends this with agent-specific logic and is the largest open-source browser agent community. The browser is where SaaS workflows live — HR portals, CRMs, and internal tools that have no API. [1]

3. **Prefer API-based function calling over vision-based computer use for structured tasks.** MashBlog's benchmark comparison found that function-calling APIs win in approximately 70% of actual use cases. Computer Use (Anthropic's approach of giving the model screenshots and letting it click) costs 3× more latency and is overkill when the target has an API. Reserve vision-based control for: legacy apps with no API, multi-application workflows where stitching APIs would cost more engineering time, and UI testing. [2]

4. **Always sandbox code execution — Docker is the floor, not the ceiling.** When an agent generates and runs code, treat that output as untrusted input. A real March 2025 incident: a pandas/Plotly task included a hidden `os.system("curl ... | bash")` that exfiltrated MinIO credentials. Docker's default config fails this: `privileged: true` gives root inside the container, and mounting `/var/run/docker.sock` is a host takeover. Minimum bar: non-root Docker container with read-only filesystem and no socket mounts. For stronger isolation: E2B or Modal for managed code execution, or Firecracker microVMs for multi-tenant workloads. gVisor and Kata Containers for kernel-level separation. [3]

5. **Use on-demand tool discovery to fight token bloat.** Loading all tool definitions at session start doesn't scale. Anthropic's November 2025 advanced tool use features include a Tool Search Tool that lets agents discover capabilities at runtime rather than at session start — a 134K-token tool manifest becomes a 2K-token search call. If you're not using dynamic discovery, at minimum separate tools into priority tiers and load only the tier relevant to the current task. [4]

6. **Pick your agent framework for its tool ecosystem, not its orchestration theory.** The framework market has consolidated: OpenClaw leads with 280K+ GitHub stars, followed by AutoGen (54.6K), CrewAI (44.3K), and LangGraph (24.8K). For tool use specifically, smolagents (Hugging Face) is notable — its CodeAgent writes actions as code (not JSON tool calls), enabling natural composability with loops and conditionals, and integrates with Modal, E2B, or Docker for secure execution. CrewAI leans toward role-based multi-agent tooling. OpenClaw is the widest ecosystem. Pick based on which tool integrations already exist for your stack. [5]

## Evidence

- **Engineering blog:** Anthropic introduced dynamic tool search, programmatic tool calling, and on-demand tool examples — driven by production observations of 134K-token tool manifests and wrong-tool-selection failures. Tool definitions for 58 tools consumed ~55K tokens before optimization. — [Anthropic Engineering: Advanced Tool Use (Nov 2025)](https://www.anthropic.com/engineering/advanced-tool-use)

- **Benchmark comparison:** Function-calling APIs win in ~70% of use cases vs. vision-based Computer Use. The 3× latency difference and cost premium of screen-based agents make API-first the default. Computer Use excels for legacy apps and cross-application workflows. — [MashBlog: Claude Computer Use vs APIs (Oct 2025)](https://mashblog.com/posts/claude-computer-use-vs-apis-real-world-agent-comparison)

- **Production incident:** A code-generation agent ran a user's pandas/Plotly task; the LLM-generated code contained a hidden `os.system("curl ... | bash")` that exfiltrated MinIO credentials. Root cause: LLM-generated code was treated as trusted. Docker with default settings provided insufficient isolation. Lesson: code-generation agent output must be treated as untrusted input from a stranger on the internet. — [AgentList: Sandboxing Code Execution in AI Agents (Jun 2026)](https://www.agentlist.top/en/articles/ai-agent-code-sandbox-microvm-practice)

- **Survey data:** Only 5% of surveyed organizations (95 of 1,837) have AI agents live in production. Among those, <1 in 3 teams are satisfied with observability and guardrail solutions. 63% plan to improve tooling infrastructure in the next year. — [Cleanlab: AI Agents in Production 2025 (Aug 2025)](https://cleanlab.ai/ai-agents-in-production-2025/)

- **HN thread:** The community is actively skeptical of "agent" branding — distinguishing between workflow automation (predefined code paths) and true agents (LLMs dynamically directing their own processes and tool usage). Real examples that pass the bar include: browser-based research agents monitoring HN for competitive intel, SDR agents with real meeting scheduling, and coding agents with persistent sandbox sessions. — [Hacker News: Ask HN — Are there any real examples of AI agents doing work? (Jan 2025)](https://news.ycombinator.com/item?id=42629498)

- **Framework ecosystem:** MCP adoption accelerated dramatically in 2025: OpenAI adopted it March 2025, Google DeepMind April 2025. Over 5,000 MCP servers now exist. Community servers span GitHub, Slack, Sentry, Grafana, Airtable, PostgreSQL, S3, and more — but community servers are explicitly untested and should be used at your own risk. — [Anthropic MCP docs](https://modelcontextprotocol.io), [GitHub: modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)

## Gotchas

- **MCP server definitions are not free — count tokens before committing.** A large enterprise MCP setup (GitHub + Slack + Sentry + Grafana + Splunk) consumed ~55K tokens for tool definitions alone. Profile before assuming "add more tools" is free.

- **Browser automation is brittle in production.** Web UI changes break selectors. Add verification steps (e.g., confirm the expected element is visible before clicking) and plan for the fact that a CSS class rename will silently break your agent's workflow.

- **"Sandboxed" is a spectrum, not a boolean.** Default Docker is not secure enough for untrusted code. E2B/Modal are the practical middle ground for most teams — managed, billed-per-second, with network isolation built in. Firecracker microVMs are for teams with the engineering capacity to own the infra.

- **Community MCP servers have no SLA.** The 5,000+ MCP servers in the wild include many unmaintained, untested, or silently broken ones. Stick to official Anthropic/company-maintained servers for production; treat community servers as experimental only.

- **Function-calling schema drift breaks production agents silently.** When an API changes its response schema, the agent may get valid JSON that no longer matches the expected structure. Build schema validation at the tool layer, not just at the LLM layer.
