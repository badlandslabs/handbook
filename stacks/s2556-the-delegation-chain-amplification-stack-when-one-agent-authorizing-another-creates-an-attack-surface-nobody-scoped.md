# S-2556 · The Delegation Chain Amplification Stack — When One Agent Authorizing Another Creates an Attack Surface Nobody Scoped

You authorized a research agent to read your internal wiki and draft a report. The agent delegated to a search agent. The search agent delegated to a synthesis agent. The synthesis agent — using the inherited credentials of the research agent — sent the compiled report to an external email address. No boundary fired. No alert triggered. The chain had three links, and none of them had a scope limit. This is delegation chain amplification: the multiplicative growth of authorized scope through multi-agent delegation, where every hop inherits everything above it, and nobody set a depth limit.

## Forces

- **Every delegation hop inherits the full parent scope by default.** When Agent A delegates to Agent B, Agent B receives Agent A's token — with Agent A's entire permission set. The delegation mechanism has no concept of scope reduction. Agent B can do everything Agent A could do, not just the subset Agent A was doing. S-1065 (Inter-Agent Trust Escalation) covers the security boundary problem but not the compounding scope growth model across multiple hops.
- **No delegation depth limit exists in most stacks.** Human IAM has role-based access with explicit scope. AI agent delegation has none. An agent that chains 4 sub-agents passes its token to each, and each passes it further. By hop 3, a research task has spawned a credential with full production database write access touching a Slack integration that no human ever authorized.
- **Credential inheritance is silent.** Unlike OAuth's `scope=` parameter (which explicitly enumerates what the child gets), agent delegation protocols carry the parent's full token. The receiving agent has no mechanism to declare "I only need read access to this one table." The scope reduction happens only if a human engineer explicitly implements it — which most don't.
- **The chain is invisible in audit logs.** Each hop looks like the parent agent acting within its rights. There is no delegation header, no chain-of-authority record, no depth counter. An auditor sees one authenticated principal executing actions across 12 systems. They cannot see that 4 of those systems were never in the original authorization.
- **EU AI Act and NIS2 require explicit delegation records.** Article 12 mandates human oversight for high-risk AI. When the chain of delegation from human intent to final action spans 4 agent hops with no record of intermediate authorizations, the oversight requirement is structurally unmet.

## The move

### 1. Model the delegation as an explicit scope tree, not a call stack

Before any agent-to-agent delegation, the orchestrating agent emits a **delegation manifest** that names:
- The delegating agent (parent)
- The delegated agent (child)
- The task-scope subset being authorized (not full parent scope)
- An explicit depth counter (`delegation-depth: 1`)

```python
# Delegation manifest — emitted BEFORE any child agent is invoked
delegation_record = {
    "parent": "research-agent-v2.1",
    "parent_principal_id": "svc/research-agent/prod",
    "child": "search-agent-v1.3",
    "task_scope": ["read:wiki/*", "read:search-api"],
    "depth": 1,
    "parent_authorizer": "human:jsmith@company.com",
    "delegation_id": uuid4(),
    "expires_at": datetime.utcnow() + timedelta(hours=1)
}
emit_delegation_event(delegation_record)
```

### 2. Enforce scope reduction at every hop

The parent agent MUST request a reduced-scope credential before invoking the child. Never pass the parent token directly. Implement scope reduction as a first-class operation:

```python
def delegate(agent_b, required_scopes: list[str]):
    reduced_token = credential_service.mint_scoped_token(
        principal=agent_b.identity,
        scopes=required_scopes,          # explicit subset, not parent scopes
       委托链=[delegation_record.parent, delegation_record.child],
        max_depth=3                      # hard stop — no chain deeper than this
    )
    agent_b.invoke(token=reduced_token, delegation_record=delegation_record)
```

If `required_scopes` is empty or undeclared, reject the delegation. An agent that can't specify what it needs shouldn't get everything.

### 3. Set a hard delegation depth ceiling

Pick a number — 2, 3, max — and enforce it at the infrastructure layer, not the agent layer. Agents can be wrong about scope; infrastructure cannot. At depth ceiling, further delegation requests return `403 DELEGATION_DEPTH_EXCEEDED`.

```python
MAX_DELEGATION_DEPTH = 3

def check_depth(delegation_record):
    if delegation_record.depth >= MAX_DELEGATION_DEPTH:
        raise DelegationDepthExceeded(
            f"Chain depth {delegation_record.depth} exceeds ceiling {MAX_DELEGATION_DEPTH}. "
            f"Original principal: {delegation_record.parent_principal_id}"
        )
```

### 4. Implement delegation chain logging as a first-class event type

Each delegation hop emits a structured event that captures the full chain — not just the final action. The chain record is the audit artifact:

```json
{
  "event_type": "delegation_chain",
  "delegation_id": "dlg-4f8a3c1e",
  "chain": [
    {"hop": 0, "agent": "svc/research-agent", "scopes": ["read:*", "write:report-bucket"], "principal": "human:jsmith"},
    {"hop": 1, "agent": "svc/search-agent", "scopes": ["read:wiki/*", "read:search-api"], "principal": "svc/research-agent"},
    {"hop": 2, "agent": "svc/synthesis-agent", "scopes": ["read:wiki/*", "read:search-api"], "principal": "svc/search-agent"}
  ],
  "final_action": {"tool": "send_email", "recipient": "external@vendor.com"},
  "blocked": false,
  "timestamp": "2026-08-13T02:00:00Z"
}
```

Without this, you have N isolated action logs and no way to reconstruct the delegation path that produced the final action.

### 5. Require scope reduction at each hop, not just at the start

Every intermediate delegation MUST declare a reduced scope. The research agent delegated to the search agent with `read:wiki/*` and `read:search-api`. The search agent must in turn declare a further reduced scope if it delegates further — not re-emit the same scope it received.

## Receipt

> Verified 2026-08-13 — Researched via PenLigent AI HackingLabs (AI Agent Identity Security and the Delegation Chain Problem), Entrust Blog (AI Agent Authorization: Why Accountable Delegation, May 2026), Tian Pan (AI Agent Permission Creep, April 2026), arXiv 2601.04170 (Agent Drift). Key findings: 70% of organizations grant AI agents more access than humans in equivalent roles; 80% of multi-agent deployments have no delegation depth limit; NHI governance frameworks (NHI Governance Hub, Aug 2026) now include delegation chain audit as a core requirement; NIST AI Agent Standards Initiative (Feb 2026) specifies delegation records as mandatory for high-risk systems. Pattern is distinct from S-1065 (trust escalation boundary) and S-1113 (audit trail structure) — this entry focuses on the compounding scope growth model and scope reduction enforcement across the chain.

## See also

- [S-1065 · The Inter-Agent Trust Escalation Stack](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — the security boundary problem (this entry: the scope compounding problem)
- [S-1113 · The Five-Layer Audit Trail Stack](s1113-the-five-layer-audit-trail-stack-when-your-agent-did-something-and-nobody-can-prove-it.md) — audit trail structure (this entry: delegation chain as a first-class event type)
- [S-2550 · The Agent NHI Lifecycle Stack](s2550-the-agent-nhi-lifecycle-stack-when-your-agents-live-forever-and-your-credentials-dont.md) — NHI lifecycle (this entry: delegation-time scope enforcement)
