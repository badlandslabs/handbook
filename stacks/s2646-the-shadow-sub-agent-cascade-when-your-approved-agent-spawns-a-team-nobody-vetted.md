# S-2646 · The Shadow Sub-Agent Cascade

Your enterprise agent passed the security review, got approved by IT, and landed in production with a clean audit trail. Nobody noticed when it spawned 12 sub-agents over the following three days — each one inheriting its parent's credentials, each one operating outside the original approval scope.

## Forces

- **Dynamic delegation is a feature, not a bug.** Approved frameworks like LangChain, AutoGen, and CrewAI encourage agents to spawn sub-agents for parallel task execution. The architecture makes this invisible by design — the parent agent's identity is the only thing in the audit log.
- **Credential inheritance is silent and total.** When your approved agent spawns a sub-agent, that sub-agent inherits the parent's authentication context by default. It can read what the parent could read, write what the parent could write, and call APIs the parent was authorized to call — all under the parent's identity in the audit trail.
- **Governance checks happen at deployment, not at runtime.** Most agent governance frameworks (including the EU AI Act's conformity assessment) evaluate the parent agent before production. None of them watch for dynamic sub-agent spawning at runtime, because traditional IAM and SIEM tools don't know what a "sub-agent" is.
- **The cascade compounds your attack surface exponentially.** One approved agent spawning 12 sub-agents creates 13 distinct behavioral surfaces under one approved identity. If any one sub-agent receives a poisoned input (an indirect prompt injection in a retrieved document, for example), the contamination spreads to all sub-agents that inherit from the compromised parent.
- **Discovery happens after the incident.** CSA (Apr 2026): 65% of organizations had a real AI agent security incident in the past year — the most common being data exposure — and the discovery typically comes from a downstream system noticing anomalous behavior, not from any governance tool catching the sub-agent spawn.

## The move

**1. Treat sub-agent spawning as a first-class governance event.**

Every time an agent spawns a sub-agent, your control plane needs to know. This means instrumenting the orchestration framework to emit a lifecycle event (CREATE_SUBAGENT) with metadata: parent identity, requested permissions, task description, and TTL. If your framework doesn't emit this event natively, wrap the spawn call in a governance proxy.

**2. Enforce a permission budget, not just a permission scope.**

The parent has access to the CRM, the database, and the email API. The sub-agent only needs the CRM. Define the minimum necessary permission set for each sub-agent at spawn time. Your control plane should reject sub-agent spawns that request permissions beyond a declared scope — or at minimum, flag them in the audit trail with a high-severity tag.

```python
# Governance proxy around sub-agent spawning
def spawn_subagent(parent_context, task_description, requested_permissions):
    approved = CONTROL_PLANE.check(
        identity=parent_context.identity,
        action="SUBAGENT_SPAWN",
        permissions=requested_permissions,
        task=task_description,
        audit=True,
    )
    if not approved.granted:
        # Log the denied spawn and either block or flag
        AUDIT.emit(blocked=True, parent=parent_context.identity, permissions=requested_permissions)
        raise PermissionError(f"Sub-agent spawn denied: {approved.reason}")
    if approved.flags & HIGH_RISK_FLAG:
        # Notify security team immediately
        SECURITY_ALERT.send(
            source="agent_control_plane",
            event="shadow_subagent_attempt",
            parent=parent_context.identity,
            permissions=requested_permissions,
        )
    return approved.subagent_token(scoped=True, ttl=task_description.estimated_duration)
```

**3. Propagate context isolation, not just identity.**

Sub-agents that inherit the parent's full conversation context inherit whatever the parent retrieved — including potentially poisoned RAG results. Use a context tunnel: pass only the relevant slice of context to each sub-agent, not the entire parent session state. This limits the blast radius of a single compromised context.

**4. Set a spawn depth limit and enforce it at the framework level.**

If your agent is authorized to act at autonomy tier T2 (human-in-the-loop on consequential actions), its sub-agents should not be able to spawn further sub-agents at T3 or T4. Cap the delegation depth and tag each sub-agent with the maximum depth it can reach. Reject spawns that would exceed the parent's authorized depth.

**5. Build the shadow agent into your observability from day one.**

Add a dedicated span type to your tracing: `subagent.spawn`. Instrument it in every orchestration framework you use. Query your traces for "parent X has more than N sub-agent spans in the last 24 hours" as a production alert. This is the only way to catch the cascade before it produces an incident.

## Receipt

> Verified 2026-08-14 — Source research: CSA Shadow AI Agent report (Apr 28, 2026 — 82% of organizations discovered unknown agents, 65% had real incidents), Superblocks "Shadow AI Agents" guide (Jul 15, 2026 — credential inheritance risk), Fullestop "Multi-Agent Systems: Ending Enterprise Agent Sprawl" (Mar 18, 2026 — 40% of enterprise apps will use agents by end of 2026). Code example is a pattern illustration; implement against your specific orchestration framework and control plane API.

## See also

- [S-622 · Agent Sprawl: The Governance Crisis Nobody's Tracking](s622-agent-sprawl-the-governance-crisis-nobodys-tracking.md) — the parent problem: ungoverned agent proliferation
- [S-2615 · The Three-Layer Agent Reliability Stack](s2615-the-three-layer-agent-reliability-stack-when-your-model-is-smart-but-your-system-still-fails.md) — eval / guardrail / harness taxonomy for orchestrating agent behavior
- [S-1855 · The Sequence Authorization Gap](s1855-the-sequence-authorization-gap-when-each-tool-call-is-authorized-but-the-chain-is-an-attack.md) — per-call vs. per-trajectory authorization
