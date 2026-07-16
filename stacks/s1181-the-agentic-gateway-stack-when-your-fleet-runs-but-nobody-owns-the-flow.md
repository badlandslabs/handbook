# S-1181 · The Agentic Gateway Stack — When Your Fleet Runs But Nobody Owns the Flow

Your agent fleet is live. Agents across 8 teams, calling external MCP servers, routing through different providers, spinning up on-demand. Then the monthly bill arrives: $200K, no attribution. One agent is hammering the API. Another is calling a third-party agent you don't control. A third just became non-compliant under EU AI Act Article 9 because nobody applied a data residency policy to its traffic. The agent is running fine. Nobody is governing the flow.

S-1041 (Agent Shadow IT) gives you a registry: you know what agents exist. This entry gives you a gateway: you own what agents do.

## Forces

- **Individual agent policies don't aggregate.** Every agent team sets its own rate limits, tool permissions, and cost budgets. At fleet scale, these decisions compound into an organization-level失控 — overspend, data egress, compliance violations that no single team owns.
- **Routing and governance are different problems.** S-1039 (Specialist Router) routes *which model* handles a request. An agentic gateway routes *which agent*, *which policy*, *which data boundary*, and *which cost center* — at the organizational level, before the request even reaches a model.
- **Kill switches must be global and instant.** When S-1060 documents an agent running itself off a cliff, the recovery mechanism is per-agent. A gateway-level kill switch stops the entire fleet from hitting a bad endpoint in one call, without redeploying anything.
- **96% of enterprises use AI agents; few have a control plane.** IBM IBV data shows enterprise adoption is nearly universal — but the governance layer (fleet-wide policy enforcement, unified audit, kill switches) lags by 2–3 years.

## The move

**The agentic gateway is the organizational control plane: a reverse-proxy and policy enforcement layer that sits in front of every agent request and applies routing, cost, security, and compliance rules at runtime — without modifying the agent itself.**

### Layer 1 — Fleet Registry Integration (what exists)

```
Request → Gateway
  ↓
  Lookup: Which agent? Which tenant? Which policy?
  ↓ Match against S-1041 agent registry
  ↓ Unknown agent → QUARANTINE + alert
```

The gateway reads from the agent registry (S-1041) on every request. Unknown agents or agents with expired registrations are quarantined before any LLM call fires. This closes the shadow IT loop: S-1041 discovers; the gateway enforces.

### Layer 2 — Policy Enforcement (what's allowed)

- **Tool allowlist/denylist per agent:** The gateway intercepts MCP tool calls and enforces tool-level permissions at the network boundary — not inside the agent prompt. An agent can *want* to call the `delete_all_users` tool; the gateway returns a 403 before the tool ever executes.
- **Data residency routing:** Requests tagged with EU Personal Data → route to EU-resident endpoints. The agent never sees the routing logic; the gateway enforces it transparently.
- **Capability-gated execution:** Agents that claim capabilities above their registered tier (e.g., a `read_only` agent attempting a write operation) are blocked at the gateway, with the violation logged for audit.

```python
# Gateway policy config (example)
policies = [
    Policy(agent="support-agent-v2",
           allowed_tools=["search_kb", "update_ticket", "send_email"],
           denied_tools=["delete_*", "exec_*", "write_*"],
           data_residency="EU",
           rate_limit=RateLimit(requests_per_minute=60, burst=10),
           cost_ceiling_usd=5000.00,
           kill_switch=KillSwitch(tag="eu-ai-act-comply-v2")),
]
```

### Layer 3 — Semantic Traffic Routing (where it goes)

The gateway routes based on the *intent and context* of the request, not just the URL:

| Signal | Routing Decision |
|---|---|
| Request contains PII | → PII-compliant endpoint |
| Request tagged `internal_only` | → On-premise agent cluster |
| Request from `premium_tier` tenant | → Priority queue + Opus-class model |
| Request from `free_tier` tenant | → Cost-optimized pool (Haiku-class) |
| Anomaly detected (burst pattern) | → Circuit breaker + alert |

This is the extension of S-1039 (Specialist Router) to the fleet level: not routing *within* an agent, but routing *across* the entire agent estate based on tenant, cost center, and risk tier.

### Layer 4 — Fleet-Wide Kill Switches (stop everything fast)

```python
# Global kill switch — fires in <100ms, no redeploy needed
kill_switches = [
    KillSwitch(
        tag="toxicity-breach",
        trigger=Trigger(type="content_moderation", threshold=0.9),
        action=Action(abort=True) + Alert(severity="critical", on_call=True)
    ),
    KillSwitch(
        tag="budget-breach",
        trigger=Trigger(type="cost_center", threshold_usd=5000),
        action=Action(queue=True) + Alert(severity="high", finance_team=True)
    ),
    KillSwitch(
        tag="regulatory-hold",
        trigger=Trigger(type="policy_tag", value="EU-RESTRICTED"),
        action=Action(queue=True) + HumanReview(deadline_minutes=30)
    ),
]
```

Kill switches fire at the gateway layer — they don't require code changes, agent redeploys, or config pushes. A regulatory change or security incident triggers a kill switch in one API call.

### Layer 5 — Cost Attribution and FinOps (who pays)

The gateway tags every request with the cost center, tenant, and agent identity at the span level — the same layer as S-1168 (Append-Only Cost Ledger), but injected at the gateway rather than retrofitted per-agent:

```python
# Span-level attribution injected by gateway
span = {
    "agent_id": "support-agent-v2",
    "tenant_id": "acme-corp-premium",
    "cost_center": "support-ops",
    "routing_policy": "eu-compliant",
    "tokens_in": token_count("input"),
    "tokens_out": token_count("output"),
    "model": "claude-sonnet-4-20250514",
    "endpoint": "mcp://hubspot.internal",
    "policy_version": "v2.3.1",
}
```

S-1168 captures the cost ledger; the gateway generates the data that populates it.

## Tradeoffs

- **Single point of failure risk.** The gateway must be highly available — multi-AZ, with a fallback that passes traffic through when the gateway is down (with alerts). A crashing gateway stops the fleet.
- **Policy consistency is hard.** Agents written before the gateway existed may have conflicting assumptions about tool access. A phased rollout with shadow mode (pass through + log, then enforce) prevents breakage.
- **Latency overhead.** A synchronous gateway adds 5–20ms per request. For latency-critical agents, use async header injection and non-blocking policy checks.
- **Not a security substitute.** The gateway enforces at the network boundary; it cannot prevent prompt injection or agent jailbreaks that originate from within the LLM itself. Defense-in-depth with S-010 (Prompt Injection Defense-in-Depth) is still required.

## Receipt

> Verified 2026-07-16 — Synthesized from: Drata agentic control plane guide (IBM IBV data: 96% enterprise AI adoption); GatewayStack OSS (davidcrowe/GatewayStack, 6 stars, modular policy + identity + routing layers); Axiom Studio unified AI gateway (fleet registry, kill switches, FinOps, RBAC, E2E tracing); Agentic Academy gateway patterns (4-pattern progression: proxy → token-aware → semantic → A2A federation); Explore Agentic registry vs gateway distinction (registry=catalog plane, gateway=data plane — not interchangeable); Knowlee fleet management (6 requirements for agent fleet operators, May 2026); TrueFoundry agent gateway (MCP gateway + data residency enforcement); TM Dev Lab production MCP gateway architecture (federated registries, enterprise-grade).

## See also

- [S-1039 · The Specialist Router Stack](s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — model-level routing; the gateway extends this to fleet-wide traffic routing
- [S-1041 · The Agent Shadow IT Stack](s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — agent registry/discovery; the gateway enforces policies against that registry at runtime
- [S-1168 · The Append-Only Cost Ledger](s1168-the-append-only-cost-ledger-when-you-cant-tell-who-spent-what-in-your-agent-fleet.md) — cost attribution; the gateway is the source of span-level attribution data
- [S-11 · LLM Gateway and Fallback](s11-llm-gateway-fallback.md) — provider-level fallback; the agentic gateway extends this to the entire agent fleet topology
