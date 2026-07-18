# S-1318 · The Ephemeral Identity Stack — When Your Agent Wears the Master Key

Your customer-service agent just moved $2.3M to an account that doesn't exist. The credentials it used were generated three months ago for the onboarding prototype. Nobody rotated them. Nobody scoped them. The agent had read, write, and delete permissions on every table in the database — because during the experiment, it was easier to give it everything and narrow down later. Nobody narrowed it down. The agent had the master key, and the master key was never taken back.

## Forces

- **Non-human identities outnumber human users 144-to-1.** Most originate from "vibe-coded" development — credentials spun up during experimentation that persist long after the experiment ends. Every one of them is an unmanaged attack surface.
- **Agent blast radius is operational, not informational.** A compromised LLM app reads data. A compromised agent opens tickets, moves money, modifies infrastructure, emails customers, and exfiltrates data through legitimate connectors. Traditional APM cannot see this class of failure.
- **Long-lived credentials amplify every failure mode.** A prompt injection exploit that captures a credential works for the lifetime of that credential — weeks, months, or forever if it's a static API key. The attack surface isn't the injection; it's the credential that never expires.
- **Least privilege gets applied to humans, not agents.** Security teams enforce the principle for human access. Agents get everything because "we're not sure what it'll need." This asymmetry is where the breach happens.
- **Identity and credential rotation for agents is architecturally different from humans.** Agents can have thousands of concurrent sessions. You cannot enroll each one in your human IAM pipeline. You need machine-native identity infrastructure.

## The move

Treat every agent session as an untrusted actor. Design identity, scoping, and credential management around that assumption.

### 1. Per-task identity provisioning

Before any agent task begins, mint a scoped identity:

```
// Pseudocode: per-task credential issuance via vault
task_id = uuid4()
vault_response = vault.issue(
    role=f"agent-task-{task_id}",
    policies=["read-only", "customer-data"],
    ttl="2h"
)
agent_credential = vault_response.credential
```

The agent receives a credential valid only for this task, scoped to only the resources this task needs, expiring within hours. If the credential is captured, its window of usefulness is bounded. This is not a configuration option — it is the default posture.

The key primitive is the **credential broker**: a service that issues short-lived, scope-minimal credentials on demand, integrated with the agent runtime. No static long-lived keys embedded in agent code. No shared service accounts.

### 2. The three-ring permission boundary

Segment agent capabilities into three rings with progressively wider blast radius:

```
Ring 1 — Observation (read-only, no external contact)
  → Read internal docs, search knowledge base, analyze context

Ring 2 — Interaction (read + write to designated systems, no deletion)
  → Create tickets, send approved emails, update records in allowlist

Ring 3 — Mutation (read + write + delete, requires pre-approval gate)
  → Database writes, money movement, infrastructure changes
     → Requires human-in-the-loop for Ring 3 actions
     → Every Ring 3 action generates an audit event
```

Agents start in Ring 1. They are promoted to higher rings only when the task requires it, and only for the minimum duration. This is the inverse of how most agents are currently deployed.

### 3. Credential rotation on risk signals

Beyond scheduled rotation, rotate credentials on behavioral anomalies:

```
// Rotate when:
on_risk_signal = (
    unusual_resource_access(session) OR
    tool_call_sequence_deviates_from_expected(session) OR
    external_data_enters_context(session) OR
    repeated_authentication_failures(session) OR
    session_duration_exceeds_policy_threshold(session)
)
if on_risk_signal:
    revoke_and_rotate(session.identity)
    alert(security_team)
```

The credential broker intercepts the revocation and re-issues with tighter scope. The agent continues operating — it never goes dark — but with reduced blast radius.

### 4. Ephemeral execution context

Isolate the agent runtime from production systems at the infrastructure level, not just the credential level. This is sandboxing for agentic systems:

- **Container-per-task**: Each agent task runs in an ephemeral container with no mounted credentials. It receives its scoped credential at startup via the broker.
- **Network segmentation**: Agent containers cannot reach internal services directly. They go through an API gateway that enforces the capability ring.
- **No shared state**: Agent task memory is isolated. If the agent is compromised, the blast radius is one task, not the entire session history.

This layer catches credential-compromise failures that credential rotation alone cannot: a compromised agent still needs network path and data access to cause harm. Remove both.

### 5. Audit as identity

Every agent action is traceable to an identity and a task. The audit log records:

```
{
  "task_id": "uuid",
  "agent_identity": "agent-task-<uuid>",
  "ring": 2,
  "credential_id": "vault-cred-<uuid>",
  "action": "db.write",
  "resource": "customers table",
  "timestamp": "2026-07-18T09:23:11Z",
  "decision": "ALLOWED",
  "task_description": "update customer contact preferences from email thread"
}
```

The identity trail answers "what did this agent do?" and "what identity was used?" — the two questions that determine whether an incident is a bug or a breach.

## Receipt

> Receipt pending — 2026-07-18

## See also

- [S-743 · Ambient Authority: Capability Bucketing](stacks/s743-mcp-tool-description-poisoning-the-schema-is-the-attack-surface.md) — least-privilege defense for multi-agent handoffs
- [S-1006 · The Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — Docker isolation and credential exfiltration via generated code
- [S-1040 · The Protocol Gap](stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP server security with least-privilege tool scoping
