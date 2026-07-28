# S-1766 · The Non-Human Identity Stack — When Your Agent Lives on a Shared API Key

When your AI agent authenticates to six downstream services — your CRM, your database, your email API — and all six log it as the same shared API key that also belongs to three other services and two human engineers, you have a non-human identity crisis. No service can distinguish which agent acted, which task it was running, or whether the action was authorized. There is no audit trail, no scoped credential, no way to revoke access for one agent without revoking it for all. This is not a configuration problem. It is a structural one: traditional IAM was designed for humans, and AI agents are neither.

## Forces

- **Agents are dynamic, humans are static.** Human identities have HR records, departure dates, and role assignments. Agents are instantiated on demand, may run for seconds or months, and their "role" is defined by a prompt — not a directory entry. IAM systems built for people cannot register, track, or decommission agents reliably.
- **Shared credentials are the default agent auth pattern.** Because proper per-agent identity is hard, most teams give their agent an API key, service account, or OAuth token borrowed from a human user. Every action the agent takes is attributed to whoever owns that credential. Revocation means breaking the agent and everything else using that key.
- **Credential lifecycle is decoupled from task lifecycle.** An agent starts a task at 9am, finishes at 6pm, but the API key lives forever. When the agent is compromised or the task scope changes, the credential does not follow. This is the inversion of least privilege: agents hold persistent credentials for ephemeral tasks.
- **Multi-agent systems amplify the problem exponentially.** When ten agents all share a service account, you cannot determine which of the ten made a problematic API call. When one agent delegates to another, there is no standard mechanism for the downstream agent to verify the delegator's identity, capability scope, or authorization chain.
- **Standards are emerging but adoption lags by 12–18 months.** IETF WIMSE (Workload Identity in Multi-System Environments) drafts are actively advancing. SPIFFE/SPIRE provides battle-tested cryptographic workload identity. CSA's AIMS profile maps WIMSE to AI agents. But production deployments still overwhelmingly rely on shared keys and borrowed tokens.

## The move

Treat every agent as a cryptographic workload with a verifiable, scoped, short-lived identity — not a shared secret or a human user's credential.

### 1. Issue a SPIFFE identity to every agent instance

Every agent — even ephemeral ones — gets a SPIFFE ID at startup:

```
spiffe://your-org.com/agent/research-agent/v1
spiffe://your-org.com/agent/coder-agent/prod-tenant-42
```

SPIFFE IDs are URIs, not IP addresses. The trust domain names your organization; the path encodes agent type, version, and tenant. The SPIRE agent attests the workload (verifying it is actually running where it claims), then issues an X.509 SVID (SPIFFE Verifiable ID) — a short-lived TLS certificate the agent presents to every downstream service.

This is not a shared secret. Each agent instance has its own private key, its own certificate, its own identity. Revocation is a SPIRE API call, not a key rotation that breaks five other systems.

### 2. Chain delegation with WIMSE-style scoped tokens

When Agent A delegates a subtask to Agent B, do not pass the shared API key. Instead, issue a WIMSE-style delegation token scoped to:

- **Who**: Agent B's SPIFFE ID
- **What**: only the specific tools/resources it needs for this subtask
- **How long**: 5–30 minutes, auto-expires
- **Why**: the specific task ID and authorization chain

```
POST /identity-broker/delegate
{
  "delegator": "spiffe://org.com/agent/planner/v1",
  "delegatee": "spiffe://org.com/agent/researcher/v1",
  "scope": ["web-search", "internal-docs-read"],
  "ttl_minutes": 15,
  "task_id": "task-7823"
}
→ { "token": "eyJ...", "expires_at": "..." }
```

Agent B presents this token alongside its own SVID when calling downstream services. The receiving service verifies both: the agent is who it claims (SVID) and it was authorized for this specific action (delegation token).

### 3. Enforce trust-on-first-use for MCP servers

MCP servers (S-10) are a common identity gap: an agent calls a third-party MCP server using a shared API token, and the server has no way to know which agent, tenant, or task triggered the call. Pin the MCP server's SPIFFE ID (if it has one) or issue a unique per-tenant API key via your identity broker on first use. On every subsequent call, verify the certificate or key before executing privileged operations.

### 4. Map agent identities to capability scopes, not just roles

A human's IAM role maps to job function. An agent's identity maps to capability grants: what tools it can call, what data it can read, what actions it can take. Use Open Policy Agent (OPA) or Cedar to define these as policies over the agent's SPIFFE ID. When the agent's task changes, its effective scope changes — not its credential.

### 5. Audit trail from identity, not from logs

Every log entry, every database row written, every API call made should carry the agent's SPIFFE ID as a structured field. This is not grep-through-logs work — this is `grpc_metadata.copy(context, {x-agent-id: spiffe://...})` in your instrumentation layer. With cryptographically signed identities, the audit trail is tamper-evident.

## Tradeoffs

- **SPIRE adds operational complexity.** You need a SPIRE server and agent on every node. For teams already running Kubernetes with SPIRE integrations (AWS KMS + IRSA, Vault PKI), this is incremental. For teams starting from scratch with no workload identity infrastructure, the setup cost is non-trivial.
- **Short-lived credentials require renewal logic.** Agents that run longer than the SVID TTL need a renewal loop. The SPIFFE Workload API handles this, but your agent framework needs to support it.
- **Not all downstream services accept SPIFFE SVIDs.** Legacy APIs, SaaS products, and third-party MCP servers still expect API keys or OAuth tokens. The identity stack bridges this gap — you wrap the third-party credential in your broker, map it to the agent's SPIFFE ID, and get the audit trail even when the downstream service does not support it.
- **Standard fragmentation.** WIMSE, SPIFFE, CSA AIMS, and OAuth 2.0 for workload identity are all converging but not yet converged. Picking SPIFFE as the implementation layer is the most battle-tested choice; the standards layer continues to evolve.

## See also

- [S-10 · MCP](s10-mcp.md) — MCP is where most agents encounter the identity gap first (shared API keys for tool servers)
- [S-1075 · Ephemeral Delegation](s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — delegation tokens are the trust chain building on top of agent identity
- [S-1050 · Tool Response Poisoning](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — catalog poisoning defense (SPIFFE attestation) builds on workload identity
