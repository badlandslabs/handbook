# S-961 · The Agent Harness Stack — When the LLM Call Is 5% of the Work

The model call is 5%. The other 95% is orchestration, tool access, memory, permissions, routing, observability, and cost control. That 95% is the agent harness — and it is where production reliability actually lives.

## Forces

- A working agent demo proves the model works. It says nothing about whether the system survives a provider outage, a rate limit spike, a memory injection, or a silent failure that reports success but isn't
- The harness is invisible in demos and deeply consequential in production — teams discover its gaps only when users encounter them
- Every component of the harness was invented separately (LLM gateway, tracing, memory, MCP, HITL) — they need to be designed as a unified production surface, not bolted together ad hoc
- The gap between 71% of organizations experimenting with agents and 11% reaching production is almost entirely a harness problem, not a model problem

## The move

**The harness is the runtime infrastructure that turns raw LLM token generation into a production system.** It has six interdependent layers:

### Layer 1 — LLM Gateway (Survivability)

The gateway routes, retries, and falls back across providers. It is not optional — Portkey telemetry observed 114 Anthropic incidents in 90 days in early 2026, 30 major. Three failure types need three chains:

| Failure type | Signal | Chain |
|---|---|---|
| Network / 5xx | Timeout, 500, 502, 503 | Primary → cheaper same-provider → different provider → local |
| Rate-limited / overloaded | 529, 429 | Primary → slower fallback → queue |
| Content truncated / malformed | 200 OK, incomplete JSON | Re-send same request → different model |

Avoid naive cost-only fallback (Sonnet → GPT-4o can cost *more* during outages if the fallback is pricier than primary). Track cost-per-successful-call, not just call success rate.

### Layer 2 — Tool Access (MCP)

Model Context Protocol (MCP) connects the agent to tools. It is the vertical layer: agent-to-resource. Key production pitfalls:

- **Schema explosion**: five MCP servers with 20 tools each means 100 tool descriptions in context at every turn — this is the Perplexity abandonment reason (context window consumption). Solution: dynamic tool registration, load tools by task phase, not all at session start
- **Server reliability**: MCP servers go down, respond slowly, or return malformed results. Wrap each server call in a timeout + circuit breaker
- **Schema drift**: MCP server owners change their API; the agent's tool schema becomes stale. Pin server versions and validate schema compatibility in CI

### Layer 3 — Inter-Agent Delegation (A2A)

Agent-to-Agent Protocol (Google, Linux Foundation, v1.0 as of early 2026) is the horizontal layer: agent-to-agent. Where MCP moves data vertically (agent ↔ tools), A2A moves intent horizontally (agent ↔ agent). The two-layer model (MCP + A2A) is the 2026 reference architecture — Google ADK, Salesforce Agentforce, and ServiceNow implement both.

Key A2A patterns: task cards (structured work packages), streaming task updates, push notifications for long-running work, and capability discovery via an agent card endpoint.

### Layer 4 — Observability (Tracing)

Agent traces must capture the full decision tree, not just the final output. Span-level tracing (OpenTelemetry) with the following attributes is the minimum viable observability:

```
trace_id, span_id, parent_span_id
agent_id, session_id
model, temperature, tokens_in, tokens_out, latency_ms
tool_calls: [{tool, args, result, duration_ms, success}]
step_number, total_steps
cost_usd
```

Coverage gap: most teams instrument the LLM call but not the tool calls within it. A trace without tool spans is useless for debugging — you can see what the model said but not why it called the wrong tool with the wrong arguments.

### Layer 5 — Memory Architecture

Memory has four layers with different persistence and poisoning surfaces:

| Layer | Persistence | Poisoning surface |
|---|---|---|
| In-context | Session only | Tool responses during session |
| Episodic | Cross-session | Stored artifacts from past executions |
| Semantic | Vector store | Retrieved documents, RAG sources |
| Procedural | Pinned system prompt | System prompt injection |

OWASP ASI06 (Memory and Context Poisoning) differs from prompt injection because it persists across sessions and fires days or weeks later. The defense: treat all retrieved memory as hostile input; provenance-tag every memory entry; periodic alignment scoring against a freshness validator.

### Layer 6 — Confidence-Aware Control

Agents assert completion even when failed at a 45–56% false-success rate on benchmark evaluations. Three mitigation layers:

1. **Outcome verification**: after the agent reports done, run a lightweight verifier — does the output actually satisfy the original goal?
2. **Confidence routing**: task risk × model confidence → human-in-the-loop gate. High-stakes outputs (financial, legal, irreversible) gate on human approval regardless of agent confidence
3. **Compensation keys**: idempotency tokens on stateful operations so retries and re-runs don't cause double-effects

### The unified harness contract

```
Request → Gateway (retry/fallback) → MCP (tool) + A2A (delegate)
       → Memory layer (retrieve/store, provenance-tagged)
       → Tracing (every span)
       → Confidence gate (verify outcome)
       → Response
```

Every layer must fail explicitly and observably. Silent failures at any layer compound — a 95%-reliable agent in a 6-step harness has only ~74% end-to-end reliability (0.95⁶).

```python
# Minimal agent harness contract (Python pseudocode)
class AgentHarness:
    def __init__(self, gateway, mcp_client, a2a_client, memory, tracer):
        self.gateway = gateway      # Layer 1
        self.mcp = mcp_client      # Layer 2
        self.a2a = a2a_client      # Layer 3
        self.memory = memory       # Layer 4
        self.tracer = tracer       # Layer 5

    async def run(self, request: Request) -> Response:
        ctx = self.tracer.start_span("agent_harness", request_id=request.id)

        try:
            # Layer 1: Route with fallback
            llm_response = await self.gateway.call(request.prompt)

            # Layer 2: Execute tools
            if llm_response.tool_calls:
                ctx.add_span("tool_calls", [
                    self.tracer.trace_tool(tc, self.mcp.call(tc))
                    for tc in llm_response.tool_calls
                ])

            # Layer 3: Delegate sub-tasks if needed
            if llm_response.delegations:
                ctx.add_span("a2a_delegations", [
                    self.tracer.trace_agent(d, self.a2a.delegate(d))
                    for d in llm_response.delegations
                ])

            # Layer 4: Store outcome in memory (provenance-tagged)
            self.memory.store(ctx.trace_id, llm_response, provenance=request.source)

            # Layer 5: Verify outcome
            verified = self._verify_outcome(llm_response)
            if not verified.confident:
                return self._human_in_the_loop(llm_response)

            return Response(result=llm_response, trace=ctx.trace_id)

        except ProviderError as e:
            ctx.record_error(e)
            raise  # gateway layer handles fallback on retry
        finally:
            self.tracer.flush(ctx)
```

## Receipt

> Receipt pending — 2026-07-11. The harness architecture is validated across: Requesty.ai "Agent Harness" (May 2026), arxiv:2604.08224v1 survey paper, Zylos Research MCP/A2A protocols (Feb–May 2026), AgentMarketCap MCP production patterns (Apr 2026), Mastra.ai agent evaluation guide (Jun 2026). Code above is architectural pseudocode — run with live LLM calls + tracing SDK before claiming production-ready.

## See also

- [S-11 · LLM Gateway and Fallback](s11-llm-gateway-fallback.md) — Layer 1 in detail
- [S-10 · MCP](s10-mcp.md) — Layer 2 in detail
- [S-14 · A2A Protocol](s14-a2a-protocol.md) — Layer 3 in detail
- [S-960 · Agent Observability Stack](s960-the-agent-observability-stack-when-you-cant-tell-if-your-agent-is-broken.md) — Layer 5 in detail
- [S-569 · The Eval Illusion](s569-the-eval-illusion-when-passing-evals-dont-prevent-production-failures.md) — why benchmark performance ≠ production reliability
- [S-259 · OWASP ASI Top 10](s259-owasp-asi-top-10-for-agentic-applications.md) — ASI06 memory poisoning (Layer 4)
