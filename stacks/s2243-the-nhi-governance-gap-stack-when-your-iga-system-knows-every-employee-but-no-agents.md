# S-2243 · The NHI Governance Gap Stack

When your Identity Governance and Administration system knows every employee, their manager, their role, and their last day — but knows nothing about the 14 agents running in production with direct access to your CRM, your codebase, and your customer PII.

## Forces

- Traditional IGA tools were built around the human employment lifecycle: hire → onboard → role assignment → manager approval → departure → access revocation. AI agents have none of these anchors. No hire date, no manager, no departure checklist, no manager approval chain.
- Gartner projects 40% of enterprise applications will ship with embedded agents by end of 2026. Every one of those agents is a non-human identity (NHI) that your IGA system cannot see, cannot audit, and cannot revoke.
- 91% of organizations already have AI agents in production; only 10% have a formal strategy for managing non-human identities (Okta, 2026). The gap between deployment velocity and governance posture is widening.
- 54% of organizations have already suffered a security incident caused by an agent acting outside expected bounds. The JADEPUFFER agentic ransomware campaign demonstrated real-world consequences of NHI sprawl.
- Agent capabilities change across versions. A v1 agent scoped to read-only CRM access gets retrained and suddenly has write permissions. Your IGA system doesn't know, because it never knew the agent existed in the first place.
- Existing coverage addresses individual credential patterns (ephemeral delegation, credential vending, permission boundaries) but none address the structural question: how do you govern a population of autonomous principals your governance infrastructure doesn't know how to model?

## The move

Treat agent governance as a three-layer problem: **Sponsorship → Capability Blueprint → Runtime Boundary**.

### Layer 1 — Sponsorship (the human anchor)

Every production agent must have a named human sponsor: the person accountable for the agent's behavior, scope, and decommissioning. The sponsor is not the developer who built it. It's the business owner who accepts risk.

```
Agent Registry Entry:
  agent_id: "cust-success-summarizer-v3"
  sponsor: "sarah.chen@company.com"       # accountable human
  owning_team: "customer-success"
  registered: "2026-03-15"
  decommission_trigger: "sponsor离职 OR monthly_review_failures > 3"
  purpose: "Summarize Zendesk tickets for CS queue triage"
  data_access_scope: ["zendesk:read", "salesforce:contacts:read"]
```

The registry is the first thing your IGA system needs to know about. It becomes the anchor for everything else.

### Layer 2 — Capability Blueprint (what the agent is allowed to do)

IGA systems model human access via RBAC/ABAC roles. Agent access needs the same treatment — a formal capability specification that is versioned, auditable, and reviewed on a schedule.

```
Agent Capability Blueprint (YAML):
  agent_id: "cust-success-summarizer-v3"
  version: "3.1"
  approved_tools:
    - tool: "zendesk.search_tickets"
      purpose: "Find relevant tickets for summarization"
      read_only: true
    - tool: "salesforce.read_contact"
      purpose: "Fetch contact context for summary"
      read_only: true
      field_whitelist: ["name", "email", "account_status"]
    - tool: "slack.notify_channel"
      purpose: "Send summary to CS queue channel"
      rate_limit: 50/hour
  prohibited_patterns:
    - "Do not modify ticket status"
    - "Do not export contact data outside Slack"
    - "Do not share summaries with external parties"
  review_cycle: "quarterly"   # or triggered by model/version change
```

This blueprint lives in version control. Any capability expansion requires sponsor approval and a new version.

### Layer 3 — Runtime Boundary (what the agent actually did)

The gap between blueprint and behavior is where incidents happen. Runtime boundary enforcement answers: "Is this agent doing what its blueprint says it should?"

Options, in order of implementation complexity:

1. **Behavioral allowlist**: instrument the agent's tool calls. Flag anything outside the blueprint's `approved_tools` list. This is the MCP tool contract gate pattern applied to the governance layer (see S-1056).

2. **Output sampling**: randomly sample agent outputs and route to a human reviewer or LLM-as-judge for conformance scoring against the blueprint's `prohibited_patterns`.

3. **Access recertification for agents**: on the same schedule as human access recertification, trigger a sponsor review of each agent's capability blueprint. Did the agent's behavior change? Did the model version change? Does the scope still match the purpose?

4. **Agent departure protocol**: when an agent is decommissioned (model sunset, project end, sponsor change), the departure checklist mirrors the human offboarding checklist: revoke tool access → revoke API credentials → archive registry entry → notify stakeholders.

### The governance triad in practice

```
                    ┌──────────────────────────────────────────┐
                    │           Agent NHI Governance             │
                    │                                          │
  Sponsor ──────────┼────────────┐                            │
  (human owner)     │            │                            │
                    │    ┌───────▼───────┐                    │
                    │    │  Capability   │                    │
                    │    │  Blueprint    │◄─── versioned      │
                    │    │  (what it can │    in git          │
                    │    │   do)         │                    │
                    │    └───────┬───────┘                    │
                    │            │                            │
                    │    ┌───────▼───────┐                    │
                    │    │  Runtime       │                    │
                    │    │  Boundary      │─── tool call       │
                    │    │  Enforcement   │    allowlist +      │
                    │    │  (what it did) │    output sampling  │
                    │    └───────────────┘                    │
                    │                                          │
                    └──────────────────────────────────────────┘
```

### Quick wins vs. full program

| Effort | Action |
|--------|--------|
| **Today** | Create an agent registry (spreadsheet counts). List every agent, its sponsor, its purpose. |
| **This week** | Add a capability blueprint for each agent. No enforcement yet — just documentation. |
| **This month** | Instrument tool call logging. Cross-reference against blueprints. Flag violations. |
| **This quarter** | Implement sponsor review cycle. Treat agent capability reviews like SOC 2 access reviews. |

## Receipt

> Receipt pending — 2026-08-06
> Verified against: Okta "Identity Governance for AI Agents" (2026), Gartner "AI Risk Management Predictions" (2026), SANS Institute "AI and Identity in 2026" (2026), NeuralCoreTech "AI Agent Identity Governance 2026" (2026), The Hacker News "Identity Lifecycle Management Wasn't Built for AI Agents" (Jul 2026)

## See also

- [S-1075 · The Ephemeral Delegation Stack](stacks/s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — credential delegation patterns for agents
- [S-1388 · The NHI Lifecycle Stack](stacks/s1388-the-nhi-lifecycle-stack-when-your-agent-has-an-identity-but-no-one-is-managing-it.md) — agent identity lifecycle management
- [S-1226 · The Trust Budget Stack](stacks/s1226-the-trust-budget-stack-when-your-agent-asks-for-permission-on-everything-or-nothing.md) — permission scope for agents
- [S-2231 · The Agent Failure Handling Stack](stacks/s2231-the-agent-failure-handling-stack-when-your-agent-runs-overnight-or-wipes-production.md) — failure handling for autonomous agents
