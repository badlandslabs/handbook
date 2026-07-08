# S-671 · A2A Agent Card Registries: Capability-Based Discovery in Production Agent Fleets

[A2A v1.0 shipped April 2026 under the Linux Foundation's Agentic AI Foundation. Every A2A agent is supposed to publish its capabilities as an Agent Card. The spec is clean. The production problem: your fleet of 40 agents needs to find the right specialist at runtime, the Agent Card schema is flexible enough that every team fills it differently, the well-known URI discovery path only works inside your own domain, and stale cards send tasks to agents that are down, overloaded, or running a different version. This is the discovery problem A2A creates — not the protocol itself.]

## Forces

- **A2A solved the communication layer; discovery is still your problem.** S-14 covers the protocol basics; S-197 covers the MCP+A2A topology. Neither covers how agents actually find each other in a live fleet — at what layer the registry lives, who owns it, how it stays accurate.
- **The Agent Card is self-reported, not verified.** An agent declares `{"capabilities": ["code-review", "git-ops"]}` in its Card. Nobody checks this at publish time. The card can be stale, aspirational, or wrong — and the routing agent trusts it anyway.
- **Well-known URI discovery stops at domain boundaries.** `/.well-known/agent-card.json` works within your own infrastructure. Cross-organization A2A (partner ecosystems, enterprise federations) requires a curated registry with authentication, governance, and lifecycle tracking — none of which the spec defines.
- **Agent health != Card freshness.** An agent can publish a valid Card and go offline 30 seconds later. Without registry health signals, routing agents send tasks to dead agents and must detect and retry — adding latency and failure surface.
- **Version skew compounds discovery errors.** Two versions of the same agent publish Cards with identical identities but different capability scopes. The routing layer has no signal to route to the right version for a given task.

## The move

### The three discovery patterns

A2A defines three mechanisms for finding agents — from simplest to most production-grade:

**1. Well-Known URI (intra-org, zero infrastructure)**

The agent exposes its Card at `https://{agent-host}/.well-known/agent-card.json` per RFC 8615. Any A2A client in the same trust domain fetches it with a single GET.

```
```python
import httpx

async def discover_agent(base_url: str) -> dict | None:
    """Fetch Agent Card from well-known URI."""
    card_url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(card_url)
        resp.raise_for_status()
        return resp.json()
```
`

Use this for: internal services, sidecar agents, anything behind your own API gateway. Do NOT use this for cross-org discovery — it has no authentication, no rate limiting, and no way to revoke.

**2. Curated Registry (enterprise, cross-team)**

A centralized agent catalog (e.g., an internal MCP registry or a purpose-built agent registry service) that teams register with. The registry enforces a Card schema, validates capability claims, tracks version and health, and provides search/filter by capability, owner, SLA tier, and cost class.

```
```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class AgentCard:
    name: str
    version: str
    url: str                      # A2A endpoint
    capabilities: list[str]      # e.g. ["code-review", "git-ops", "pr-draft"]
    authentication: Literal["api-key", "oauth2", "mtls"] | None
    max_concurrent_tasks: int | None
    avg_latency_ms: int | None
    owner: str                    # team or service account
    deprecation_date: str | None

class AgentRegistry:
    """Centralized A2A capability registry with health tracking."""
    def __init__(self):
        self._cards: dict[str, AgentCard] = {}
        self._health: dict[str, bool] = {}

    def register(self, card: AgentCard) -> None:
        # Validate required fields, check for duplicate capabilities
        self._cards[card.name] = card
        self._health[card.name] = True

    def find(self, capability: str) -> list[AgentCard]:
        """Find agents matching a capability."""
        return [c for c in self._cards.values()
                if capability in c.capabilities
                and self._health.get(c.name, False)]

    def mark_unhealthy(self, agent_name: str) -> None:
        self._health[agent_name] = False

    def get_card(self, agent_name: str) -> AgentCard | None:
        return self._cards.get(agent_name)
```
`

**3. Skill-Filtered Discovery (routing layer)**

The A2A spec supports discovery filters: agents send a task description and the registry returns agents whose Cards match. Production routers add version pinning, cost-class preferences, and load-based filtering on top.

```
```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class DiscoveryFilter:
    required_skills: list[str]
    min_version: Optional[str] = None
    max_cost_tier: Optional[str] = None  # "free", "standard", "premium"

async def route_to_agent(
    filter: DiscoveryFilter,
    registry: "AgentRegistry"
) -> AgentCard | None:
    """Route task to best-matching agent from registry."""
    candidates = registry.find(filter.required_skills[0])
    for skill in filter.required_skills[1:]:
        candidates = [c for c in candidates if skill in c.capabilities]

    # Filter by version constraint
    if filter.min_version:
        candidates = [c for c in candidates
                      if c.version >= filter.min_version]

    # Filter by health
    candidates = [c for c in candidates
                  if registry._health.get(c.name, False)]

    # Filter by deprecation
    candidates = [c for c in candidates
                  if c.deprecation_date is None]

    if not candidates:
        return None

    # Sort by: health > version (prefer newer) > latency
    return min(candidates, key=lambda c: (
        -registry._health.get(c.name, False),
        -_parse_version(c.version),
        c.avg_latency_ms or 99999
    ))
```
`

### Keeping the registry alive

The hardest operational problem: cards go stale. Three practices prevent it:

- **Health heartbeat**: agents POST their Card to the registry every N seconds. The registry marks an agent `UNHEALTHY` after 2–3 missed heartbeats and removes it from routing. On recovery, the agent re-registers.
- **Card versioning**: every Card carries a semantic version. The routing agent caches Cards locally and re-fetches if the version in cache differs from the Card fetched at connection time. If the version bumped, re-validate capabilities.
- **Capability claim audit**: periodically (weekly or on model update), run a capability audit — invoke each agent's `skills/list` endpoint and compare against what its Card claims. Flag discrepancies.

### Cross-org discovery

For federated enterprise environments (partner ecosystems, multi-subsidiary deployments), well-known URIs don't reach across domains. The pattern: each organization maintains its own internal registry and exposes a **federation endpoint** — an authenticated A2A endpoint that returns the organization's public Card catalog. The federation aggregator queries all partner endpoints and caches the merged catalog locally.

```
```python
async def federated_discovery(
    my_registry: AgentRegistry,
    partner_endpoints: list[str],
    capability: str
) -> list[AgentCard]:
    """Merge local + partner agent catalogs for cross-org discovery."""
    all_cards = list(my_registry._cards.values())

    async with httpx.AsyncClient(timeout=10.0) as client:
        for endpoint in partner_endpoints:
            try:
                resp = await client.get(
                    f"{endpoint}/.well-known/agent-card.json"
                )
                resp.raise_for_status()
                data = resp.json()
                # data may be a single card or a catalog array
                cards = data if isinstance(data, list) else [data]
                all_cards.extend([
                    AgentCard(**c) for c in cards
                ])
            except httpx.HTTPError:
                # Log, continue, do not fail the federation query
                pass

    return [c for c in all_cards if capability in c.capabilities]
```
`

## Tradeoffs

- **Registry becomes a single point of failure.** If the registry goes down, no agent can discover peers. Run it in HA/replicated mode. Design the routing layer to fall back to well-known URI discovery if the registry is unreachable.
- **Schema flexibility vs. interoperability.** The A2A Card schema lets agents declare arbitrary capabilities. This flexibility enables rich discovery — but also enables meaningless Cards ("AI-powered magic"). Enforce a controlled vocabulary for capability strings in your internal registry.
- **Card freshness vs. discovery latency.** Aggressive heartbeat intervals keep Cards fresh but add network chatter. Conservative intervals reduce overhead but let stale entries persist. Target: heartbeat ≤ 10% of expected agent restarts.

## What this connects to

- [S-14 · A2A Protocol](s14-a2a-protocol.md) — protocol basics (transport, task lifecycle, JSON-RPC)
- [S-197 · MCP + A2A Two-Layer Orchestration](s197-mcp-a2a-two-layer-orchestration.md) — topology of the two-layer model
- [S-661 · Agent Protocol Abstraction](s661-agent-protocol-abstraction-layer.md) — cross-framework fleet governance (related but addresses the policy plane, not discovery)
- [S-246 · Production Eval Pipeline](s246-production-eval-pipeline-the-four-stage-loop.md) — eval pipeline for capability claim auditing
