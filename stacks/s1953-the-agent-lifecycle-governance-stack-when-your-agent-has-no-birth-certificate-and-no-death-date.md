# S-1953 · The Agent Lifecycle Governance Stack — When Your Agent Has No Birth Certificate and No Death Date

Your agent has been running for 14 months. It has an owner — a team that no longer exists. It has credentials — keys to four systems, two of which have been decommissioned. It has a memory store — with embeddings of a spreadsheet nobody remembers uploading. It has a purpose — nobody can tell you what it was supposed to do anymore. Nobody built it through a governance gate. Nobody reviewed it when the team changed. Nobody will decommission it when it stops being useful. This is the agent lifecycle governance gap: 77% of organizations say AI adoption is outpacing their governance capabilities, and only 21% have a mature model for managing agentic AI risks.

This entry is not about whether to build agents. It's about what happens to them from birth to death — and why that entire arc is invisible in most organizations today.

## Forces

- **Agents accumulate faster than they can be governed.** Microsoft reports 18× growth in enterprise agents year-over-year, concentrated in data analytics and internal process automation. Each one arrives with a purpose and a set of permissions. Almost none arrive with a planned retirement date or a defined owner beyond the sprint it shipped in.

- **Every lifecycle phase has a distinct threat model.** Birth introduces credential sprawl (agents provisioned with excessive permissions). Life introduces permission creep (gradual accumulation of access). Drift introduces behavioral regression (the agent that worked last quarter doesn't work this one). Death introduces orphaned access (credentials that outlive their agent). Each phase is managed by a different team, and none of the teams talk to each other.

- **Agents fall outside human IAM review cycles.** Traditional access reviews happen quarterly, targeting human identities. Agent identities — non-human identities (NHIs) — sit outside that cycle entirely. In mid-2026, NHIs outnumber human identities in enterprise environments at roughly 45:1. Only 12% of organizations report high confidence in preventing NHI-based attacks. 78% lack formal policies for creating and decommissioning agent identities.

- **Decommissioning an agent is not the same as stopping a process.** Stopping an agent frees compute. It does not revoke the API keys it holds, purge the memory stores it populated, remove the IAM roles it assumed, or delete the audit logs it generated. The credential remains live. The data remains accessible. The audit trail remains active. This is the decommissioning gap — and it is where the breach risk lives after the agent "dies."

- **EU AI Act Article 9 makes lifecycle governance legally mandatory.** High-risk AI systems (agents in HR, credit, hiring, or critical infrastructure) must maintain documented risk management processes covering the full lifecycle. Agents that were compliant at deployment can drift out of compliance as prompts change, tools are added, and permissions expand. Article 9 requires this to be a living process, not a one-time certification.

## The move

The lifecycle governance stack has four phases, each with its own control plane:

```
Birth ──────────────────────────────────────────────────────── Death
  │                                                             │
  ├── Registration gate          Lifecycle control plane ────────┤
  ├── Ownership assignment      Every phase: owner + reviewer   │
  ├── Minimal-privilege          Least privilege at provisioning  │
  ├── Time-bound credentials     Expiry tied to task duration    │
  │                                                             │
Life ────────────────────────────────────────────────────────── │
  │                                                             │
  ├── Permission audit trail      Log every permission change    │
  ├── Quarterly NHI review        Include agents in IAM reviews  │
  ├── Behavioral baseline         Trapdoor: compare to known-good│
  │                                                             │
Drift ───────────────────────────────────────────────────────── │
  │                                                             │
  ├── Capability trajectory        Track success rate over time   │
  ├── Prompt version audit        Log prompt changes as code     │
  └── Escalation gate             Human review before autonomy ↑ │
  │                                                             │
Death ─────────────────────────────────────────────────────────┘
  │
  ├── Credential revocation       API keys, OAuth tokens, IAM roles
  ├── Memory store purge         Vector DB, episodic memory, logs
  ├── Audit log retention        Keep trails per compliance req.
  └── Artifact deletion          Output artifacts, temp files
```

### Phase 1 — Birth: Registration gate

Before an agent touches a production system, it must exist in a control plane. This means a registration record with:

- **Human owner**: a named individual accountable for the agent's behavior
- **Stated purpose**: a one-paragraph description of what the agent does and why
- **Permission manifest**: every system the agent can access, with the specific scope (read-only, read-write, admin)
- **Planned review date**: typically 90 days post-deployment, then quarterly
- **Decommission trigger**: a condition that ends the agent (task complete, date reached, human decision)

Okta for AI Agents (GA April 30, 2026) provides a centralized directory for agent registration across any build platform. Microsoft Entra Agent ID (GA 2026) adds owner assignment and lifecycle controls to Entra. Both target the same problem from different angles: making agents first-class identities with a paper trail.

The registration gate is not a bureaucratic hurdle. It is the only mechanism that answers "does this agent still have a purpose?" six months after launch.

### Phase 2 — Life: Permission audit trail and NHI reviews

Agents accumulate permissions through friction. A customer-support agent hits a permission wall. Someone grants an exception. The exception becomes permanent. Repeat for 18 months.

This is the permission creep cycle, and it is the leading cause of over-privilege in production agentic systems. Organizations that grant AI more access than a human in the same role face a 4.5× higher security incident rate.

The fix is not stricter provisioning — it is continuous auditing:

```python
# Agent permission audit (run monthly against your IAM system)
import boto3, json

def audit_agent_permissions(agent_id):
    # Fetch agent's registered permission manifest
    manifest = control_plane.get_manifest(agent_id)
    
    # Compare against live IAM roles
    iam_roles = iam.list_roles(PathPrefix=f"/agents/{agent_id}/")
    
    granted = {r['RoleName']: parse_policy(r) for r in iam_roles['Roles']}
    expected = manifest['permissions']
    
    drift = {}
    for perm, scope in expected.items():
        if perm not in granted:
            drift[perm] = 'MISSING'
        elif granted[perm] != scope:
            drift[perm] = f'SCOPE_DRIFT: expected {scope}, got {granted[perm]}'
    
    # Alert on unexpected grants (creep detection)
    for role_name, policy in granted.items():
        if role_name not in expected:
            drift[f'UNREGISTERED:{role_name}'] = 'ACCUMULATED'
    
    return drift

# Alert owner if drift detected — triggers permission review
drift = audit_agent_permissions("cust-support-v3")
if drift:
    alert(agent_id, owner, drift)
    # Block agent if drift exceeds threshold
    if len(drift) > 3:
        suspend_agent(agent_id, reason="permission drift exceeds threshold")
```

Agents must be included in quarterly NHI access reviews — the same review cycle used for human identities. 97% of organizations breached by AI-related incidents lacked proper AI access controls. Quarterly reviews would have caught most of those.

### Phase 3 — Drift: Behavioral baseline and prompt version audit

An agent's behavior changes over time even when its code doesn't. Model updates shift confidence distributions. Prompt changes introduce subtle behavioral shifts. Tool updates change the agent's action space. The result: the agent that passed its launch evaluation no longer behaves the same way.

The Agent Drift Stack (S-1945) covers this in detail. For lifecycle governance, the key controls are:

- **Prompt version control**: treat prompts as code. Every change goes through a PR, gets reviewed, and is tagged with a version. AgentMarketCap (April 2026) measured that 60% of agent regressions in production trace to an unversioned prompt change that nobody linked to the regression.
- **Capability trajectory tracking**: measure success rate per task type per week. A downward trend triggers an evaluation review before the regression becomes user-visible.
- **Escalation gate**: as agents gain autonomy (moving from advisory to acting), require a human gate. Cordum (2026) recommends treating this as a compliance control under EU AI Act Article 14, not a prompt instruction.

### Phase 4 — Death: The decommission checklist

When an agent is retired, every artifact it created must be explicitly handled. A stop command is not a decommission. It is an interruption. The decommission checklist:

```
Agent Decommission Checklist
─────────────────────────────
☐ Revoke API keys         aws iam delete-access-key (per key ID)
☐ Revoke OAuth tokens     Provider revocation endpoints
☐ Remove IAM roles        /agents/{agent_id}/* roles deleted
☐ Purge memory store      Vector DB namespace deleted, episodic store wiped
☐ Delete output artifacts S3 bucket / prefixed objects deleted
☐ Archive audit logs      Retain per compliance requirement (typically 5–7 years)
☐ Update control plane    Mark agent DEACTIVATED, record decommission date
☐ Notify data owner       Confirm personal data handled per retention policy
☐ Remove from agent catalog  Catalog entry marked retired, not deleted
```

The last step — catalog entry marked retired, not deleted — is intentional. Compliance audits need to show what existed, even after it no longer does. Delete the artifact; keep the record of its existence.

Dark Reading (May 2026) reports that "orphaned automation" is creating unmanaged access risks across enterprise environments. The fix is not better agents — it is treating decommissioning with the same rigor as provisioning.

## Receipt

> Verified 2026-08-01 — VE3 Blog (Jun 29, 2026): 77% of orgs say AI adoption outpaces governance. Only 21% have mature agentic AI governance. Okta for AI Agents GA April 30, 2026. Microsoft Entra Agent ID GA 2026. Dark Reading (May 25, 2026): NHIs outnumber human identities ~45:1; 78% lack formal NHI policies. Tian Pan (Apr 15, 2026): 70% of orgs grant AI more access than humans in same role; 4.5× breach rate for over-privileged AI. Entro Security (2025): NHI growth 44% YoY. Cordum (2026): EU AI Act Article 14 requires human oversight as external constraints, not prompt instructions. CodeX (May 2026): agents must be treated as having a birth, life, and retirement — credential cleanup is part of the retirement, not optional.

## See also

- [S-1945 · The Agent Drift Stack](stacks/s1945-the-agent-drift-stack-when-your-agent-isnt-broken-but-its-becoming-worse.md) — Behavioral drift detection across the agent's life
- [S-1196 · The Agent Catalog Plane](stacks/s1196-the-agent-catalog-plane-when-you-cant-govern-discover-or-trust-an-agent-you-dont-know-exists.md) — The discovery layer that makes lifecycle visibility possible
- [S-1041 · The Agent Shadow IT Stack](stacks/s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — The discovery problem that makes lifecycle governance impossible without it
