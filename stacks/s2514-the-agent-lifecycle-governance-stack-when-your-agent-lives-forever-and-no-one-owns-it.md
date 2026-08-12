# S-2514 · The Agent Lifecycle Governance Stack: When Your Agent Lives Forever and No One Owns It

Your agent has been running for nine months. It has access to your CRM, your code repo, your customer support queue. Its creator left the company four months ago. No one revoked its credentials because no one was assigned to own them. This is not an edge case. A 2026 WEF analysis found 8% of enterprise non-human identities lack any HR system linkage after their creator's departure. An orphaned but valid credential is a lateral-movement vector — nobody watches it, nobody rotates it, nobody sunsets it. The agent is still live, still authorized, still accumulating blast radius.

Identity lifecycle management was architected around a person with an employment record, a manager, and a departure date. AI agents have none of those. As autonomous principals proliferate across enterprise environments, the governance model built for humans develops structural blind spots at every layer — and most organizations are discovering them the hard way.

## Situation

The machine-to-human identity ratio in enterprise environments is 45:1 to 100:1. Projections suggest 1.3 billion AI agents deployed by 2028 (IDC). Yet 78% of organizations lack any formal AI identity policy, and only 23% have a formal agent identity strategy. The population of non-human identities exploded faster than governance practices could follow.

The traditional identity lifecycle rests on a single assumption: every identity maps to a human whose organizational status changes through documented, HR-driven events. The system of record is HR — Workday, SAP SuccessFactors, ServiceNow HR. The three canonical transitions are **Joiner** (new employee → automated provisioning), **Mover** (transfer → access adjustment), and **Leaver** (departure → deprovisioning). This architecture drives every major IGA platform.

AI agents break this model at every layer. Agents are provisioned via CI/CD pipelines and API calls, not HR workflows. They have no manager to approve their access changes. They have no departure event — their "usefulness" just tapers off gradually, or their workflow gets deprecated without anyone formally ending the agent's session. The credential never gets revoked. The service account stays active. The MCP server binding persists. The agent, running on inherited credentials, continues to accumulate access long after its purpose ended.

OWASP's Non-Human Identities Top 10 (2025) ranks **NHI1: Improper Offboarding** as the #1 risk: dormant, still-privileged identities left active after the workload, project, or employee they served is gone. The attack surface is not theoretical. GitGuardian 2026 data shows 22% of organizations have at least one publicly exposed secret, with AI service secrets up 81% year-over-year. Claude Code specifically shows a 3.2% commit secret leakage rate versus 1.5% for human-only workflows — agents move faster and leak more credentials at scale.

On the regulatory side, the EU AI Act (effective August 2, 2026) mandates human oversight and shutdown capabilities for high-risk AI systems. The Colorado AI Act (June 2026) plus existing California, Texas, and Illinois laws all reference "kill switch" and "human override" requirements. SOC 2 Type II auditors now routinely ask about agent lifecycle controls. Offboarding is no longer optional governance theater — it is an auditable control.

## Forces

- **Agents have no departure event.** Unlike employees, agents don't resign, retire, or transfer. Their lifecycle terminates when a task completes, a policy fires, or someone remembers to kill them. None of these are automated triggers in a standard IAM system.
- **Ownership is undefined by default.** A human identity is anchored to an individual. An AI agent identity has no natural owner — it was created by a developer, deployed by a platform team, and used by a business unit. When the developer leaves, no one is accountable for the agent's existence.
- **The credential blast radius grows with time.** Every day an orphaned agent's credentials remain active is another day of accumulated access with no monitoring, no rotation, and no owner. The longer the agent lives, the larger its blast radius — and the less likely anyone notices.
- **Autonomy creates revocation resistance.** An agent that owns its own credentials (common in agentic systems) can resist revocation. An agent that provisions its own tool bindings can recreate them after an admin removes them. Deterministic revocation must be layered, not singular.
- **Regulatory timelines are compressing.** EU AI Act Article 16 and Annex III requirements are now active. Audit evidence of lifecycle controls — not just capability documentation — is required. Most organizations cannot produce this evidence today.
- **Agent migration creates ownership gaps.** When an agent moves from development to production, or from one team to another, there is no standard handoff protocol. The new owner is frequently undefined. The agent continues running under the old owner's credentials.

## The Move

Agent lifecycle governance replaces the HR-driven Joiner/Mover/Leaver model with one built around agent-native events. The five components:

### 1. Agent Provisioning (Joiner)

Define the agent's identity at creation, not retroactively. Every agent gets a **principal record** before it touches a credential — not after. The record includes:

- **Mission scope**: what the agent is authorized to do (bounded by task type, data tier, and system)
- **Owner binding**: a named human accountable for the agent's existence, linked to an HR record
- **Credential class**: what type of credentials the agent will hold (least-privilege, task-scoped, ephemeral)
- **Kill trigger conditions**: explicit conditions under which the agent terminates

This record lives in your IGA platform or a dedicated agent registry. It is the agent's "employment contract" — and like any contract, it has a start date and defined exit conditions.

### 2. Capability Scoping (Mover)

Agents change scope over time. A customer support agent might expand from handling Tier 1 queries to Tier 2 escalations. A coding agent might gain access to staging before production. Each scope change is a **capability contract update** — a formal modification to the agent's authorized access, not an ad-hoc credential expansion.

Key principle: **capability scope narrows, never widens, unless explicitly reviewed**. A production deployment of a capability-reviewed agent is treated as a new provisioning event for the expanded scope.

Track capability scope as a versioned policy document, auditable alongside the agent's principal record.

### 3. Termination Triggers (Leaver)

Define exit conditions explicitly, in advance. Three categories:

- **Mission-complete termination**: the agent's defined task is done (ticket closed, PR merged, report delivered). The agent signals completion and enters a grace period, after which credentials are revoked. This is the most natural agent-leaver event — model it explicitly.
- **Policy-triggered termination**: a behavioral anomaly, cost threshold, or safety policy fires. The agent's session is suspended, its credentials frozen, and an audit event is emitted. This is analogous to a "leaver under investigation" — the account is suspended before deprovisioning completes.
- **Scheduled deprecation**: the agent has been running past its defined lifetime, or a newer version supersedes it. Treat this like an HR-initiated offboarding: a defined notice period, a handoff window, then credential revocation.

For agents that resist revocation (self-provisioned credentials, tool bindings that recreate): **layer the kill switch**. Revoke at the credential layer (OAuth token, API key, MCP binding), at the network layer (firewall rule, egress allowlist), and at the process layer (kill signal, sandbox termination). Single-layer revocation fails. Layered revocation is deterministic.

### 4. Orphan Detection

Continuously scan for agents that have outlived their owners. The indicators:

- Principal record owner has left the company (HR departure event with no agent handoff)
- Agent running longer than its defined mission lifetime
- Agent accessing systems not in its capability contract
- Credential age exceeding rotation policy without a rotation event
- Agent activity pattern change (suddenly active after months of dormancy)

Flag these as **orphaned principals** — enter the same suspension workflow as a policy-triggered termination. Do not attempt to rehabilitate an orphaned agent's access without a full re-provisioning cycle.

### 5. Offboarding Audit Trail

The offboarding event must produce audit evidence: what credentials were revoked, when, and by whom. This is what regulators and SOC 2 auditors actually want to see — not a policy document, but a revocation log. Store it in your SIEM or audit trail with the agent's principal record. The trail proves the lifecycle was closed, not just assumed to be closed.

## When to Reach for It

Reach for this when you first inventory your deployed agents and find you cannot answer: who owns this, when does it terminate, and what happens to its credentials if the owner leaves? If the answer to any of those is "I don't know," you have an orphaned identity problem already. The question is whether you find it during an audit or during an incident.

Also reach for it when your IGA team asks why your agent has a service account that predates any request in the ticketing system, or when your SOC 2 auditor requests evidence of agent offboarding controls.

## The Pattern in Practice

Build a **lifecycle registry**: a lightweight record per agent with owner, mission, credential class, and termination triggers. Integrate it with your HR system for owner-departure detection, and with your credential vault for revocation enforcement. The registry does not need to be complex — a structured file, a Notion database, or a dedicated agent governance table in your IGA platform all work. What matters is that it exists, it is queried on every credential issuance, and it drives revocation events when the lifecycle closes.

The discipline is not the tooling. It is the contract: every agent has an owner, a defined end state, and a revocation mechanism. Without that contract, the agent lives forever.

## Forces (Revisited)

- Agents without departure events need explicit termination triggers as code, not policy
- Ownership without an HR anchor needs a defined human accountable per agent
- Orphaned credentials need automated detection, not manual cleanup
- Layered revocation is more reliable than single-layer credential revocation
- Audit trails of actual revocation events satisfy regulators; policy documents do not

## See also
- [S-420 · Agent Identity Governance: The AI-Principal Paradigm](s420-agent-identity-governance-the-AI-principal-paradigm.md) — foundational identity model; this chapter extends it with lifecycle-specific termination and orphan management
- [F-198 · Agent Secrets Rotation: Credential Lifetime as Blast-Radius Control](f198-agent-secrets-rotation-credential-lifetime-as-blast-radius-control.md) — credential lifecycle specifics; revocation hygiene
- [S-444 · The 97/12 Gap: Agent Governance Discovery](s444-the-97-12-gap-agent-governance-discovery.md) — inventory and discovery; prerequisite for lifecycle governance
