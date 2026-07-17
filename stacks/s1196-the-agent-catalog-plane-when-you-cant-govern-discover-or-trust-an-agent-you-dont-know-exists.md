# [S-1196] · The Agent Catalog Plane — When You Can't Govern, Discover, or Trust an Agent You Don't Know Exists

You have agents in production. Eight teams are running them. The compliance team asks: which agents touch customer PII? Nobody knows. The security team asks: which agents call external third-party agents? Nobody knows. The finance team asks: which agents were deployed in the last 30 days? Nobody knows. The agents are running fine. Nobody owns the catalog.

The agent catalog plane is the discovery and metadata layer that sits *outside* the execution path — answering "what exists, who owns it, what can it do, and which version is live." Without it, governance is reactive (you find out about an agent when it breaks or breaches), routing is manual (agents can't discover peers), and compliance is impossible (you can't audit what you haven't registered).

## Forces

- **Enterprise AI sprawl outpaces governance velocity.** 96% of organizations have agent deployments they don't know about (Bigeye, 2026). The catalog-plane gap isn't a documentation problem — it's a structural one. Teams deploy agents faster than any central team can track them. The answer isn't a slower deployment process; it's a catalog plane that makes registration automatic and discovery self-service.
- **The governance sequence is Inventory → Registry → Catalog.** You can't govern what you haven't inventoried. You can't surface for discovery what you haven't governed. Most organizations try to build the gateway first and discover they have no agents registered in it. The catalog plane is the foundation — it must come first.
- **The registry is not in the call path.** This is the key architectural distinction. The catalog plane is a metadata service — it answers questions about agents, it doesn't route requests between them. The agentic gateway (S-1181) is the data plane; the catalog plane is the control plane. Confusing them produces either a bottleneck (everything routes through the registry) or a gap (governance without discovery).
- **Agent capability declaration is the hardest part.** Saying "this agent can do X" sounds simple. In practice, it requires the agent to expose a structured capability manifest — the tools it uses, the data it accesses, the events it publishes and subscribes to, the autonomy level it operates at, and the approval workflow required before it goes live. Without this, the catalog is a list of names with no actionable content.

## The move

The catalog plane has three distinct layers. Most teams conflate them; building them in sequence prevents rework.

### Layer 1: Agent Inventory — What exists?

The compliance artifact. Answers: which agents are deployed, when, and where. Every agent gets a unique identifier at deployment time — not a human-chosen name, but a stable UUID generated from a manifest hash. This means the inventory is tamper-evident: if an agent's UUID doesn't match a known manifest, it's a shadow deployment.

```yaml
# agent-inventory.yaml (version-controlled, CI-generated)
agents:
  - id: agent-4f3a9c2b        # UUID from manifest hash
    name: invoice-processor
    team: finance-ops
    deployed_at: "2026-06-12"
    environment: production
    manifest_ref: "sha256:a3f9b1..."  # points to versioned manifest
    status: active
```

### Layer 2: Agent Registry — Who owns it and what can it do?

The governance artifact. Answers: ownership, capability declaration, authorization scope, autonomy level, and escalation policy. This is what the security and AI governance teams consume.

```yaml
# agent-registry.yaml
agent_id: agent-4f3a9c2b
owner:
  team: finance-ops
  oncall: finance-ops-oncall@company.com
  sla_responder: "15min"

capabilities:
  tools:
    - name: fetch_invoice
      mcp_server: finance-mcp-v2
      data_access: [customer_pii, invoice_records]
    - name: post_to_erp
      mcp_server: erp-mcp
      data_access: [erp_write]
  events_published: [invoice.processed, invoice.failed]
  events_subscribed: [payment.received]

autonomy_level: 2   # 0=human-in-loop, 3=fully-autonomous
  # Level 0: Every action requires human approval
  # Level 1: Routine actions autonomous; exceptions escalate
  # Level 2: Autonomous within defined scope; boundary crossings escalate
  # Level 3: Fully autonomous; monitored via telemetry

escalation_policy:
  boundary_crossings:
    - trigger: data_access == [pii_write]
      action: HITL_PAUSE
      approver: data-steward@company.com
    - trigger: cost_estimate > 500
      action: HITL_PAUSE
      approver: finance-ops-oncall@company.com
```

### Layer 3: Agent Catalog — Discovery surface for developers and peer agents

The developer-facing artifact. Answers: how do I find and use this agent? What interface does it expose? What inputs does it accept? This is what feeds A2A peer discovery (S-1040) and the agentic gateway routing layer (S-1181). It's also what MCP gateway implementations consume to populate their tool allow-lists.

```yaml
# agent-catalog-entry (published to catalog plane)
agent_id: agent-4f3a9c2b
display_name: "Invoice Processor"
description: "Extracts invoice data from PDF attachments, validates against ERP records, and posts to the accounting system."
version: "2.3.1"

interface:
  protocol: a2a-v1
  input_schema:
    type: object
    required: [invoice_attachment_url]
    properties:
      invoice_attachment_url: { type: string, format: uri }
      force_reprocess: { type: boolean, default: false }
  output_schema:
    type: object
    properties:
      erp_transaction_id: { type: string }
      status: { enum: [success, failed, needs_review] }

tags: [finance, document-processing, erp-integration]
replaces: agent-4f3a9c2b      # previous version, for deprecation tracking
health_endpoint: /agents/agent-4f3a9c2b/health
```

### The automation that makes it work

The catalog plane dies without automation. Three integration points keep it alive:

```python
# 1. CI/CD hook: auto-register on deployment
def on_agent_deploy(manifest: dict, env: str) -> str:
    agent_id = hash_manifest(manifest)   # tamper-evident UUID
    capabilities = extract_capabilities(manifest)
    autonomy_level = classify_autonomy(capabilities)

    registry.update({
        "agent_id": agent_id,
        "manifest_ref": store_manifest(manifest),
        "environment": env,
        "capabilities": capabilities,
        "autonomy_level": autonomy_level,
    })
    catalog.publish(agent_id)            # make discoverable
    return agent_id                      # agent uses this as its stable ID

# 2. Gateway integration: catalog feeds routing decisions
def route_to_agent(intent: AgentIntent, catalog: Catalog) -> str | None:
    candidates = catalog.find(
        tags__contains=intent.required_tag,
        autonomy_level__gte=intent.min_autonomy,
        status="active",
    )
    if not candidates:
        raise UnroutableIntent(f"No agent found for {intent.required_tag}")
    return candidates[0].agent_id

# 3. Compliance audit: registry answers "which agents access PII?"
def audit_pii_access(registry: Registry) -> list[Agent]:
    return registry.find(data_access__contains="customer_pii")
```

## Receipt

> Receipt pending — 2026-07-16. Pattern extracted from: Bigeye "Agent registry vs. catalog vs. inventory" (June 2026); ExploreAgentic Agent Registry Field Guide (May 2026, AWS Bedrock AgentCore registry preview April 2026); Gravitee State of AI Agent Security 2026 (14.4% orgs have full MCP security approval). Code examples are structurally faithful to AWS AgentCore registry API shapes and A2A agent card discovery format.

## See also

- [S-878 · The Agent Fleet Manifest Stack](s878-the-agent-fleet-manifest-stack-when-your-agents-are-ad-hoc-and-your-fleet-is-a-riot.md) — GitOps for the AI workforce; catalog plane is the discovery layer that fleet manifest populates
- [S-1181 · The Agentic Gateway Stack](s1181-the-agentic-gateway-stack-when-your-fleet-runs-but-nobody-owns-the-flow.md) — gateway is the data-plane enforcement; registry is the control-plane source of truth it reads from
- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — A2A peer discovery; agent cards in the catalog enable discovery without hard-coded agent URLs
