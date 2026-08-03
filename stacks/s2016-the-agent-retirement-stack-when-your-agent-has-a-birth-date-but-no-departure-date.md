# S-2016 · The Agent Retirement Stack — When Your Agent Has a Birth Date but No Departure Date

Your shipping agent has been running for 14 months. It has 7 OAuth tokens, 3 service accounts, a dedicated vector index, 2 MCP server registrations, and an IAM role with write access to your order management system. Nobody scheduled a review. Nobody set a TTL. The agent that shipped to replace it is live, but this one was never terminated — it still has its credentials, still responds to internal routing rules, and nobody noticed because nobody was watching for death. This is the agent retirement gap: teams obsess over the birth, ignore the life, and forget the death entirely.

## Forces

- **Agents don't quit.** Human employees have departure events: termination, role change, offboarding. Agents run until someone explicitly stops them. Without a scheduled retirement date, every agent accumulates a tail of integrations that never gets cleaned up. By mid-2026, non-human identities outnumber human identities in enterprise environments at a ratio of roughly 45:1 — and unlike human accounts, agents never trigger a deprovisioning workflow.
- **Deployment is the finish line in software; it is the midpoint in agent lifecycles.** Every week an agent runs, it writes state to memory stores, acquires cached tokens, registers tool schemas, and logs traces that grow its storage footprint. A 6-month-old agent has accumulated credential debt, memory pollution, and downstream state ownership that a fresh agent doesn't have. Treating deployment as the finish line means this debt compounds invisibly.
- **Agents own state in downstream systems.** Unlike a batch job that writes a file and exits, an agent creates entities, modifies records, schedules follow-ups, and writes to shared databases. Retiring the agent without retiring its downstream effects leaves dangling references, orphaned records, and workflows waiting on a ghost. The retirement process must include artifact cleanup, not just credential revocation.
- **The attack surface of a dormant agent is indistinguishable from an active one.** From the credential system's perspective, a 14-month-old agent with active tokens looks identical to a brand new one. Revocation gates that require manual intervention never trigger. Every month of unattended operation is another month of accumulated NHI exposure with no governance checkpoint.
- **Eval sets decay, but nobody rotates them.** When an agent is replaced, its eval set stays behind. The replacement agent runs a stale benchmark designed for the previous agent's capabilities, task types, and failure modes. Over time, the eval set measures "last quarter's agent" — not the current one. This is invisible degradation: the tests pass, the quality is wrong.

## The move

**1. Define the retirement contract at provisioning time — not at termination.**

Before the agent goes live, document its termination triggers:
```
Agent Retirement Contract
- Hard deadline:  [date or null]
- Trigger-based: [e.g., "replaced by agent X", "task queue empty for 30 days", "error rate > 15%"]
- Re-certification interval: [90 days]
- Owner:          [email]
- Decommission checklist: [link to runbook]
```
Store this contract alongside the agent's credentials in the NHI registry. Treat it like a YYYY-MM-DD expiration date on a human account.

**2. Build the offboarding checklist as a first-class artifact.**

An agent offboarding is a runbook, not a delete button. It must cover:

```
Agent Offboarding Runbook
├── Credential layer
│   ├── Revoke OAuth tokens (active + refresh)
│   ├── Delete service account or reassign
│   ├── Rotate IAM role credentials (don't just delete — rotation ensures
│   │   downstream systems using the old credential fail loudly)
│   └── Remove MCP server registration
├── Memory layer
│   ├── Export and archive final memory state
│   ├── Clear session-scoped memory stores
│   ├── Delete or reassign owned vector index entries
│   └── Update downstream records owned by this agent (flag or reassign)
├── State layer
│   ├── Identify records created by this agent
│   ├── Reassign open workflows or mark as "agent retired"
│   └── Audit log: export final trace for compliance
└── Observability layer
    ├── Remove from active routing rules
    ├── Archive traces > N days
    └── Disable alerting for this agent's metrics
```

**3. Implement graceful degradation before forced termination.**

Agents that own downstream state need a handoff protocol, not an abrupt kill. Before revocation, run a final state reconciliation:

```python
async def agent_retirement_handoff(agent_id: str) -> RetirementReceipt:
    """Run before revoking any credentials. Returns a signed receipt."""
    # 1. Snapshot current state ownership
    owned_records = await state_registry.find(owned_by=agent_id)
    
    # 2. For each record, either reassign or archive
    for record in owned_records:
        if has_active_workflow(record):
            await workflow_system.transfer(record, new_owner=None)
            await record.flag("awaiting-human-review", agent_id=agent_id)
        else:
            await record.archive()
    
    # 3. Export final memory snapshot
    memory_export = await memory_store.export_session_history(agent_id)
    await archive_store.put(f"agent-{agent_id}-final-state.json", memory_export)
    
    # 4. Revoke all credentials (last step, after state is clean)
    await nhi_registry.revoke_all(agent_id)
    
    return RetirementReceipt(
        agent_id=agent_id,
        records_reassigned=len([r for r in owned_records if r.reassigned]),
        records_archived=len([r for r in owned_records if r.archived]),
        memory_exported=True,
        credentials_revoked=await nhi_registry.count_active(agent_id),
        retired_at=datetime.utcnow()
    )
```

**4. Set re-certification gates, not just retirement dates.**

Not all agents have a natural end date. For long-lived agents, require periodic re-certification: quarterly owner sign-off that the agent's scope, credentials, and eval set are still correct. This catches credential sprawl and eval decay before they become incidents. A 3-question review: (1) Is this agent's scope still correct? (2) Are its credentials still minimally scoped? (3) Is its eval set still representative?

**5. Detect ghost agents via credential-last-used analysis.**

Agents that haven't been called in N days but still hold active credentials are ghost agents. Run a weekly scan:

```bash
# Weekly ghost agent detector
for nhi in $(nhi_registry list --type=agent --active=true); do
    last_used=$(tracing_system last_invocation --nhi="$nhi")
    days_since=$(($(date +%s) - $(date -d "$last_used" +%s) / 86400))
    if [ $days_since -gt 30 ]; then
        echo "GHOST: $nhi inactive for $days_since days, credentials still active"
        notify --owner=$(nhi_registry get --nhi="$nhi" --field=owner)
    fi
done
```

## Receipt

> Receipt pending — 2026-08-02

## See also

- [S-1388 · The NHI Lifecycle Stack](s1388-the-nhi-lifecycle-stack-when-your-agent-has-an-identity-but-no-one-is-managing-it.md) — NHI management during the agent's active lifetime (this entry is the closing chapter of that lifecycle)
- [S-1999 · The NHI Aggregation Stack](s1999-the-nhi-aggregation-stack-when-one-agent-holds-ten-identities-and-your-rbac-never-knew.md) — the credential accumulation problem that retirement reverses
- [S-1058 · The Production Eval Stack](s1058-the-production-eval-stack-when-your-evaluation-is-a-spike-and-your-production-is-a-mystery.md) — eval set maintenance and staleness (relevant to re-certification gates)
- [S-997 · The Agent Observability Stack](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — detecting silent degradation that signals an agent needs retirement review
