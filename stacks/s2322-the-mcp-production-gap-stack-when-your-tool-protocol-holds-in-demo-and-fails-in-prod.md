# S-2322 · The MCP Production Gap Stack — When Your Tool Protocol Holds in Demo and Fails in Prod

MCP connects agents to tools, APIs, and data sources. It has 16k+ active servers, 97M+ monthly SDK downloads, and every major IDE and LLM provider has added support. It works beautifully in demos. Then real users arrive, tokens expire mid-session, API calls fail silently, and the agent starts hallucinating tool responses because its connection to reality has quietly severed.

## Forces

- **MCP standardizes discovery and invocation, not operation.** The protocol says how an agent finds and calls a tool. It says nothing about how long a tool call should wait, what to do when auth expires, or how to propagate identity across nested tool calls.
- **The demo-to-production gap is wider than expected.** Teams building MCP integrations test in controlled environments. Production throws concurrent users, long-running sessions, token expiry under load, and observability blind spots — none of which appear in a single-agent demo loop.
- **Three protocol primitives are still missing.** Academic analysis of enterprise MCP deployments identifies: identity propagation, adaptive tool budgeting, and structured error semantics as unresolved gaps that teams must solve themselves at the application layer.
- **Silent failures are worse than loud ones.** When an MCP tool call fails and the agent hallucinates a response, there is no error log that flags "agent disconnected from real data." The user just gets a wrong answer that looks confident.

## The Move

A production MCP stack that actually works requires hardening beyond what the protocol specifies:

- **Token lifecycle management.** Implement proactive token refresh — do not wait for expiry. Track token TTL, refresh before the window closes, and design for graceful degradation when auth fails rather than silent hallucination.
- **Tool call budgets, not just timeouts.** Assign a time/token budget per tool invocation. Agents that spend too many tokens on a single tool call degrade overall task quality. The protocol does not enforce this; your orchestration layer must.
- **Structured error responses from every MCP server.** Map every error condition to a machine-readable error category (auth failure, rate limit, data unavailable, timeout, etc.). Agents need structured semantics to recover — a generic 500 error teaches them nothing.
- **Observability at the tool call layer.** Instrument every MCP tool invocation: latency, success/failure, auth state, token consumption. Without this, you cannot tell whether a 48-hour silent failure is a model problem or a tool problem.
- **Identity propagation through nested tool calls.** When an agent uses a tool to retrieve data, and that data feeds into another tool call, identity context must flow through. Without it, cross-system operations lose the "who is this for" context and produce authorization or scoping errors.

## Evidence

- **Production incident report:** One team observed 60+ API calls fail silently over 48 hours due to monitoring gaps — auth tokens expired mid-session, tools returned no data, and agents hallucinated responses rather than surfacing errors. — [Paperclipped: MCP Servers in Production: Lessons Learned After 6 Months](https://www.paperclipped.de/en/blog/mcp-server-production-deployment-lessons/), March 2026
- **Academic analysis:** ArXiv study of enterprise MCP deployments identified three missing protocol-level primitives: identity propagation, adaptive tool budgeting, and structured error semantics. CABP, ATBA, and SERF are proposed as reference implementations. — [arXiv:2603.13417 — Bridging Protocol and Production: Design Patterns for Deploying AI Agents with MCP](https://arxiv.org/html/2603.13417v1), March 2026
- **Adoption scale and roadmap shift:** MCP has 16k+ active servers, 97M+ monthly SDK downloads, and all major cloud providers (Azure, AWS) have rolled out MCP workflow services. The 2026 roadmap reorganized around working groups rather than release milestones, reflecting that the protocol is maturing from experiment to infrastructure. — [MCP Blog: The 2026 Roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)

## Gotchas

- **OAuth tokens expire mid-session in long-running agent tasks.** Design for token refresh from day one, not as a patch after the first user reports a broken session.
- **Scope mismatches bite when agents escalate from read to write.** A token valid for data retrieval fails silently when the agent tries to write — the error semantics at the protocol boundary are too coarse to distinguish the cause.
- **MCP tool availability is not the same as MCP tool reliability.** A server that responds in demo may have entirely different latency and error characteristics under concurrent production load.
- **The protocol does not tell you when to give up on a tool call.** Without application-layer budgets, agents retry indefinitely or give up too quickly — neither is calibrated to the actual failure mode.
