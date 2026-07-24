# S-1523 · The Agent Fleet Registry Stack — When You Have 47 Agents and No Idea What They're Doing

You approved three agents for production. Your identity logs show 47 MCP client connections, 12 third-party AI tools, and agents running across sales, legal review, HR, and operations — each touching different data categories, each making hundreds of decisions per day. Nobody approved them. Nobody knows what they do. Your EU AI Act submission is in 20 days. This is the agent fleet registry problem: you cannot govern what you cannot see, and the agent ecosystem is growing faster than any manual inventory process can track.

## Forces

- **Agent proliferation outpaces manual governance.** Enterprise teams deploy agents independently — a CRM integration here, a legal review pipeline there, an MCP server per tool. Each deployment is justified locally and invisible globally. No single team owns the full picture, so no single team can produce one.
- **Static registration gates create shadow IT.** When registering an agent takes two weeks of security review, teams deploy without registering. Rigid governance processes don't reduce agent risk — they redistribute it into the ungoverned perimeter. S-1041 (Shadow IT Stack) documents this from the security angle; this entry covers the registry infrastructure that makes governance fast enough to use.
- **Agent capabilities and risk profiles change between deployments.** A harmless research agent in Q1 becomes a GDPR liability in Q3 when pointed at customer PII. A read-only MCP integration in staging writes to production in deployment. The registry cannot be a one-time snapshot — it must track the current state of what each agent actually does, not what it was approved to do.
- **Fleet-wide properties are invisible at the agent level.** An individual agent's audit log is useless for answering "which agents touched this customer record?" or "which agents have write access to our ERP?" Fleet-level queries require fleet-level instrumentation — a registry that tags agents with data categories, risk levels, and decision scope at the job definition level.

## The Move

**Build a dynamic, job-level agent registry that is the single source of truth for fleet inventory, risk classification, and governance status — integrated into the deployment pipeline so registration is frictionless enough that teams don't bypass it.**

### 1. The Registry Data Model

Every registered agent (or automated job) carries a structured manifest with:

| Field | Purpose |
|-------|---------|
| `agent_id` | Stable identifier (UUID or semantic name) |
| `owner_team` | Who is accountable |
| `risk_classification` | EU AI Act / internal tier (high/medium/low) |
| `data_categories` | What data classes it can access (PII, financial, health, public) |
| `decision_scope` | What it can do: read-only, modify, execute, delegate |
| `delegation_targets` | Which other agents it can hand work to (A2A scope) |
| `model_provider` | Which LLM backs it (for compliance and cost attribution) |
| `registry_version` | Incremented on every config change |
| `last_heartbeat` | Last observed runtime activity |

The model is inspired by Google Cloud Agent Registry (which registers MCP servers and A2A agent cards as discoverable endpoints) and Knowlee's Jobs Registry primitive (which attaches risk metadata at job definition time).

### 2. Auto-Discovery: Register Agents Without Team Cooperation

Manual registration fails because it relies on voluntary compliance. Auto-discovery works:

- **MCP server scan**: Enumerate all MCP client connections from identity logs. Every MCP client implies an agent. Tag with the MCP server's capability manifest (what tools it exposes). This is how you find the 47 agents nobody told you about.
- **A2A Agent Card ingestion**: A2A agents publish Agent Cards (capability manifests at a well-known URL). The registry scrapes known Agent Card endpoints and imports them automatically. Google ADK 1.0, Microsoft Copilot Studio, and Salesforce Agentforce all publish signed Agent Cards. Apicurio Registry added native A2A Agent Card storage in v3.1.7 (December 2025) — use it as a central Agent Card store.
- **CI/CD pipeline hooks**: Any agent deployed through the standard pipeline auto-registers with its manifest. This is the registration gate that doesn't create a bottleneck — it happens in the deploy step, not in a separate review step.

### 3. Risk Stratification and Progressive Autonomy

Not all agents need the same governance intensity. The registry drives a progressive autonomy model:

- **Low risk** (read-only, public data, no decision): register and monitor, minimal approval overhead
- **Medium risk** (internal data, modify actions): require owner attestation + data category confirmation
- **High risk** (PII, financial, health, delegation chain): require security review, human-in-the-loop configuration, and runtime audit logging

The registry enforces this: agents above their approved risk tier get their delegation requests rejected at the A2A negotiation layer.

### 4. Fleet-Wide Query Infrastructure

The registry enables fleet-level questions that individual agent logs cannot answer:

```
Which agents accessed customer PII this week?
Which agents have outbound internet access?
Which agents delegate to third-party agents outside our A2A trust domain?
What is the complete decision chain for this customer record?
```

This requires the registry to be queryable, not just readable. Back it with a graph database (Neo4j, Amazon Neptune) where agent nodes are linked by A2A delegation edges. A delegation from Agent A to Agent B creates a directed edge with the registry manifest of both agents attached — enabling upstream and downstream lineage queries.

### 5. Drift Detection

The registry's most important job is detecting when the deployed agent diverges from its manifest:

- **Capability drift**: agent gains new MCP tool access not in its manifest (scan MCP client connections weekly against registry)
- **Delegation drift**: agent delegates to an agent not in its approved delegation_targets list
- **Model drift**: agent switches model providers (detected via API call logs)
- **Scope drift**: a read-only agent starts making POST calls (detected via network egress logs)

Drift violations trigger automatic alerts and can gate A2A delegation — the receiving agent refuses the task until the delegation is re-authorized.

### 6. The MCP/A2A Native Registry Path

If you're building on a cloud platform, use the native registry as your foundation:

- **Google Cloud**: Agent Registry in Gemini Enterprise Agent Platform. MCP servers and A2A Agent Cards are first-class registry entries. Enables direct discovery from Vertex AI Agent Builder.
- **AWS**: AgentCore provides runtime and governance services. The Agent Registry tracks agent identity, policies, and telemetry. Azure Citadel (Microsoft) offers equivalent with unified governance and cost attribution per agent.
- **Cross-platform**: If agents span multiple clouds or frameworks, aggregate into a platform-agnostic registry (your own or Apicurio) that ingests Agent Cards via their published JSON endpoints. This is the pragmatic path for heterogeneous fleets.

## Receipt

> Verified 2026-07-23 — Google Cloud Agent Registry docs confirmed as general availability (docs.cloud.google.com/agent-registry). A2A Agent Cards confirmed as native artifact type in Apicurio Registry v3.1.7 (GitHub #6996, closed/completed). Knowlee's six-primitives fleet governance model reviewed (knowlee.ai, May 2026). Microsoft Azure Citadel fleet governance primitives confirmed (Azure-Samples/foundry-citadel-platform GitHub). GCP MCP server registration and A2A Agent Card discovery patterns documented in official MCP best practices site (mcp-best-practice.github.io). EU AI Act Article 9/12 compliance deadline August 2026 referenced in multiple 2026 sources — direct regulatory driver for registry adoption.

## See also
- [S-1041 · The Agent Shadow IT Stack](/stacks/s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — security team visibility problem (this entry covers the registry infrastructure to solve it)
- [S-988 · The Agent Fleet Resilience Stack](/stacks/s988-the-agent-fleet-resilience-stack-when-your-orchestrator-dies-but-your-agents-keep-running.md) — fleet-level operational resilience
- [S-972 · The Agent Trust Negotiation Stack](/stacks/s972-the-agent-trust-negotiation-stack-when-your-agent-has-to-prove-itself-to-another-agent.md) — A2A delegation authorization, which the registry enforces
- [S-1104 · The Three-Layer Protocol Stack](/stacks/s1104-the-three-layer-protocol-stack-when-your-agent-lives-in-a-world-of-three-simultaneous-protocols.md) — MCP, A2A, and A2UI protocols, of which the registry tracks agent endpoints across all three
