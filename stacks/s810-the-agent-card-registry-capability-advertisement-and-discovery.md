# S-810 · The Agent Card Registry: Capability Advertisement and Discovery in Agent Ecosystems

You add a new agent to your fleet. It announces itself at startup. The other agents have no idea what it does, what it costs, whether it's trusted, or whether its declared capabilities are accurate. You wire it in manually. Six months later, nobody remembers why that wire exists. This is the discovery problem — and the Agent Card + Registry pattern is the answer.

## Forces

- **The capability declaration gap.** An agent says it "handles customer complaints." Does it escalate? Does it issue refunds? Can it access PII? Self-declared capability descriptions are natural language — unverifiable and drifting.
- **Static tool lists hit a ceiling.** As fleets grow past 20 agents, injecting every agent's schema into every other agent's context collapses token budgets. Discovery must be runtime, not compile-time.
- **Trust requires more than authentication.** Even with TLS and valid credentials, an agent can declare more capabilities than it has, outlive its approved scope, or silently degrade. The registry must carry trust signals, not just endpoints.
- **Cross-framework deployments make manual wiring impossible.** A LangGraph agent needs to delegate to a CrewAI agent and a custom Claude Code agent. Without a shared discovery layer, every integration is bespoke.

## The move

### 1. Publish an Agent Card at `/.well-known/agent-card.json`

Every agent exposes a machine-readable card — the A2A standard's answer to "what are you and what can you do?" The card lives at a well-known URL so any A2A client can fetch it without prior configuration.

```json
{
  "name": "customer-complaint-agent",
  "version": "2.3.1",
  "description": "Handles inbound customer complaint triage and escalation.",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "longRunningTasks": true
  },
  "skills": [
    {
      "id": "complaint-triage",
      "name": "Complaint Triage",
      "description": "Classifies complaint severity and routes to appropriate queue.",
      "tags": ["support", "classification", "escalation"]
    },
    {
      "id": "refund-initiate",
      "name": "Initiate Refund",
      "description": "Initiates refund for approved complaint types up to $500.",
      "tags": ["refund", "financial"],
      "maxValue": 500
    }
  ],
  "authentication": {
    "schemes": ["bearer", "mtls"]
  },
  "security": {
    "signingKeyKid": "kid:cust-complaint-agent-2026",
    "certificateFingerprint": "SHA256:AB:34:..."
  },
  "endpoints": {
    "default": "https://agent.internal.example.com/a2a"
  }
}
```

The `skills` array is the actionable part. Unlike free-text descriptions, skills have IDs, tags, and optional parameters — a calling agent can match a task requirement to a skill without understanding natural language.

### 2. Choose your discovery topology

Three patterns cover the range from startup scripts to enterprise fleets:

**Embedded card URL (small fleet).** The caller knows the callee's base URL and fetches `/.well-known/agent-card.json` directly. Zero infrastructure. No single point of failure. No central knowledge — every agent must be pre-configured with every other agent's URL.

```python
async def discover_agent(base_url: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/.well-known/agent-card.json", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
```

**Central registry (team/company scale).** A registry service (e.g., `registry.a2a-registry.dev`, or self-hosted) acts as a directory. Agents register on startup, heartbeat, and deregister on shutdown. Callers query by tag or capability rather than by URL.

```python
class AgentRegistry:
    def __init__(self, registry_url: str):
        self.registry_url = registry_url
        self._cache: dict[str, dict] = {}
        self._cache_ttl = 60  # seconds

    async def register(self, agent_card: dict):
        await self._post("/agents", agent_card)

    async def find_by_skill(self, tag: str) -> list[dict]:
        """Returns all agents advertising a skill with the given tag."""
        resp = await self._get(f"/agents?skill={tag}")
        return resp.json()["agents"]

    async def find_by_capability(self, capability: str) -> list[dict]:
        """Semantic search over capability embeddings."""
        resp = await self._post("/agents/search", {
            "query": capability,
            "top_k": 5
        })
        return resp.json()["agents"]
```

**Federated registry (cross-organization).** When agents from different organizations need to discover each other, federated registries form a mesh. Each organization runs its own registry; cross-org queries route through a shared root or DHT. NANDA (MIT's decentralized protocol) targets this scale.

### 3. Add trust signals, not just endpoints

A bare Agent Card is a claim. Production systems need evidence:

**Signed cards.** The agent's operator signs the card with a private key. The signing key is referenced by `kid` (key ID) and anchored to a trust chain (enterprise PKI or a web-of-trust). The caller verifies the signature before trusting the declaration.

**Capability embeddings.** Store the `skills` array as semantic embeddings in the registry. When a caller asks for "an agent that handles billing disputes," a vector search returns ranked candidates — more robust than exact tag matching, and resistant to naming drift.

**Behavioral attestation.** A registry that only stores self-declarations is a directory, not a trust system. The enterprise pattern: policy enforcement at the registry gates the card (scan for prompt injection in capability strings, verify skill IDs against a schema, check that the signing key is not revoked), and issues a registry attestation signature on top of the operator's signature. Now a caller can verify two independent trust signals.

### 4. Audit the capability claim over time

The most underappreciated failure mode: an agent's card was accurate at registration but the agent has since changed behavior. Skills are deprecated, endpoints migrate, signing keys rotate. The registry must track version history and surface staleness.

```python
@dataclass
class AgentCardVersion:
    version: str
    card: dict
    registered_at: datetime
    attested_by: str  # registry operator's signature
    deprecated: bool = False
    deprecated_at: datetime | None = None

    def is_stale(self, max_age_days: int = 30) -> bool:
        return (datetime.utcnow() - self.registered_at).days > max_age_days
```

A gateway that enforces staleness checks (reject cards older than 30 days by default, configurable per trust tier) prevents agents from operating on outdated capability declarations.

## Receipt

> Verified 2026-07-08 — A2A Protocol v1.0 (Linux Foundation, Jan 2026) defines the Agent Card schema and `/.well-known/agent-card.json` convention. The a2a-registry.dev hosted registry implements the central-registry pattern with semantic search over capability embeddings. The Jarvis Registry (ASCENDING) demonstrates the security-scanning gate: prompt injection detection on capability strings and policy compliance checks before catalog publication. The capability embedding gap — self-declared skills vs. actual behavior — is identified by Zylos Research (Mar 2026) as the primary source of failed delegation in multi-agent systems. No production-ready open-source implementation of the full signed + attested + staleness-checked registry pattern was found in the wild; the components exist (SPIFFE for identity, OpenFGA for authorization, OTel for audit), but integration is custom per deployment.

## See also

- [S-14 · A2A Protocol](s14-a2a-protocol.md) — the horizontal agent-to-agent layer that Agent Cards serve
- [S-10 · MCP](s10-mcp.md) — the vertical tool-access layer; Agent Cards describe capabilities that may wrap MCP servers
- [S-340 · Agent Hard Enforcement Plane](s340-agent-hard-enforcement-plane.md) — deterministic enforcement downstream of discovery
- [S-661 · Agent Protocol Abstraction](s661-agent-protocol-abstraction-cross-framework-fleet-governance.md) — cross-framework fleet governance; the registry is its discovery layer
