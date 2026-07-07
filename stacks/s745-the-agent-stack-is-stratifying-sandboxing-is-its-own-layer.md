# S-745 · The Agent Stack Is Stratifying: Sandboxing Is Its Own Layer

When a coding agent writes a shell command and executes it, the OS grants whatever permissions the host process already has. That's not a configuration problem — it's an architectural one. The sandbox is not the same as the orchestrator, not the same as the model, and not the same as the tool layer. Teams that treated it as an afterthought discovered that the hard way, through credential exfiltration, runaway loops, and remote code execution chains. The agent stack is stratifying into six layers, and sandboxing is the one most teams still get wrong by omission.

## Forces

- **The monolithic trap**: Early agent stacks bundled everything — orchestration, tool execution, sandboxing, and context management — into a single deployment. When one layer fails or is compromised, the blast radius is the whole system — [Philipp D. Dubach, February 2026](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **The 37% multi-model reality**: More than a third of enterprises now run five or more AI models in production. When your orchestration layer routes between Claude, GPT-4o, and a local code model, you need each execution environment isolated, not shared — [Philipp D. Dubach, February 2026](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **The prompt-becomes-shell vulnerability**: Microsoft published research on May 7, 2026 documenting prompt injection chains achieving remote code execution across multiple agent frameworks. The attack surface is not the prompt — it's the tool execution path that the prompt controls — [TURION.AI / Microsoft Security, May 2026](https://turion.ai/blog/agent-sandboxing-firecracker-gvisor-microvm-architecture)
- **Specialized sandboxes vs. Docker**: Docker containers share the kernel with the host. A coding agent that escapes its container has host-level access. MicroVMs (Firecracker) provide hardware-level isolation with sub-100ms startup, purpose-built for ephemeral agent workloads — [TURION.AI, May 2026](https://turion.ai/blog/agent-sandboxing-firecracker-gvisor-microvm-architecture)

## The move

The agent stack separates into six layers with different defensibility profiles:

- **Orchestration layer**: LangGraph, CrewAI, Temporal — defines workflow, state, and routing. Most teams get this right or switch quickly.
- **Model layer**: API gateway, model routing, prompt management. Now commoditized — wins at the routing and cost level, not the model level.
- **Tool / MCP layer**: Model Context Protocol servers, REST integrations, function calling schemas. Rapidly standardizing.
- **Sandbox / execution layer**: Firecracker microVMs, gVisor, E2B, Modal, Shuru. This is the new distinct layer. Isolation is the product.
- **Context / memory layer**: Vector DBs, semantic memory, session stores. The highest lock-in and hardest-to-rebuild zone.
- **Observability layer**: LangSmith, Phoenix, Opik, distributed tracing. Most teams have logging but only 52% have evals — [RaftLabs, November 2025](https://www.raftlabs.com/blog/multi-agent-systems-guide)

**Pick sandboxing as an independent service, not a feature flag.** E2B handles ephemeral Linux sandboxes for coding agents. Modal provides serverless Python execution with automatic scaling. Firecracker is the open-source foundation both build on. For production, the choice is between managed (E2B, Modal) and self-hosted (Firecracker wrappers).

**Network egress is the control plane.** Every sandbox escape or data exfiltration needs an outbound channel. Block non-allowlisted outbound connections at the sandbox network layer, not at the application layer.

**Startup latency and cost at scale are non-trivial.** Firecracker cold-starts in ~125ms but E2B warm pools add ~2s overhead per first execution. Budget for warm pool sizing in production load testing.

## Evidence

- **HN show post — Opensoul agentic marketing stack**: 6-agent hierarchy (Director → Strategist → Creative → Producer → Growth Marketer → Analyst) using Paperclip orchestration, running on scheduled heartbeats with autonomous task delegation. Demonstrates that multi-agent production systems are shipping, not just prototyped — [Hacker News, June 2025](https://news.ycombinator.com/item?id=47336615)
- **Philipp Dubach — agent stack stratification**: 37% of enterprises using 5+ AI models in production; Gartner predicts 40% of enterprise apps will feature AI agents by 2026, but 40% of agentic AI projects will be canceled by end of 2027 due to unclear business value. Argues the defensible asset is the organizational world model, not the model itself — [philippdubach.com, February 2026](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **TURION.AI — sandbox benchmarks**: gVisor adds 2–5% CPU overhead vs. native. Firecracker cold-starts in ~125ms. Kata Containers (VM-level isolation) adds 30–50% memory overhead but is appropriate for highest-risk workloads. E2B and Modal are managed abstractions over these primitives — [TURION.AI, May 2026](https://turion.ai/blog/agent-sandboxing-firecracker-gvisor-microvm-architecture)

## Gotchas

- **Don't treat Docker as a sandbox for agents that execute code.** It was designed for application isolation, not execution isolation. A code-generating agent running inside a Docker container shares the host kernel — a container escape gives full host access.
- **Indirect prompt injection bypasses the model.** An attacker embeds instructions in data the agent processes (email, Slack message, scraped web page). Those instructions never appear in the prompt itself — they arrive via tool results. Sanitize all external data at the tool layer, not the prompt layer.
- **Multi-agent orchestration amplifies the blast radius of a single compromised sandbox.** If your analyst agent has egress access and your sandbox is compromised, the agent can exfiltrate the data it can see — which in a multi-agent system includes outputs from other agents in the shared context.
- **Warm pool sizing is load testing, not configuration.** Teams that deploy E2B or Modal without profiling their warm pool under concurrent load discover cold-start queues under production traffic — adding seconds of latency at the worst moment.
