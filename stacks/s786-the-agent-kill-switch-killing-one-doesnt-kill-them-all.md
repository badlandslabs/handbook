# S-786 · The Agent Kill Switch: Killing One Doesn't Kill Them All

Your agent started looping at 3 PM. You hit terminate on the orchestrator. The parent stops. The 14 sub-agents it spawned — each with their own tokens, credentials, and write access — keep running. Two hours later, your database has 340 ghost records and your audit log shows writes from sessions that should not exist. You killed the head. The body kept moving.

## Forces

- **An agentic system is a process tree, not a process.** Traditional kill switches assume a single PID. An orchestrator is a parent in a tree — terminating it leaves orphaned children that continue executing with full access
- **Sub-agents hold distributed state.** Spawned agents carry their own session tokens, tool credentials, and context. Revoking the parent's access does nothing to revoke theirs — they were issued independent credentials
- **Async propagation takes time.** Token revocation propagates through an LLM gateway in milliseconds. A sub-agent that got a direct MCP credential from the server might hold that credential until it expires — which could be minutes
- **86% of enterprises have no multi-agent kill switch procedure.** The OWASP Top 10 for Agentic AI (S-259) lists uncontrolled agent termination as a critical gap — and most teams discover it during their first real incident
- **Blast radius = scope × velocity × time.** A looping agent burning $5K/hour isn't the worst case. The worst case is one that wrote to 12 systems before you found the off switch

## The move

The kill switch is a three-layer pattern: **Token Revocation → Async Propagation → State Freeze**.

### Layer 1: Token Revocation (immediate, ≤10ms)

The emergency stop lives at the LLM gateway or API gateway — not in the orchestrator, not in system prompts. System prompts are not security boundaries; they are suggestions the model can ignore under adversarial conditions or token pressure.

```
python
# LLM Gateway: emergency kill endpoint
@app.post("/admin/kill/{session_id}")
async def emergency_kill(session_id: str):
    # Step 1: Revoke all active tokens for this session tree
    killed = await token_vault.revoke_session_tree(session_id)
    # Step 2: Notify MCP servers to close connections
    await mcp_gateway.broadcast_close(session_id)
    # Step 3: Signal orchestrator to halt (best-effort, may be ignored)
    await orchestrator_signal(session_id, signal="ABORT")
    return {"killed_tokens": killed.count, "status": "INITIATED"}
```

Key principle: revocation must be **deterministic, not probabilistic**. Do not route the kill switch through the LLM — if the LLM is the problem, it may choose not to stop.

### Layer 2: Async Propagation (eventual, ≤30s)

Sub-agents may be running on different model instances, separate MCP servers, or distributed workers. After revoking tokens at the gateway, propagate the kill signal asynchronously:

```python
async def propagate_kill(session_id: str):
    """Propagate kill to all known sub-agent sessions."""
    sub_sessions = await session_registry.get_children(session_id)
    for sub in sub_sessions:
        await token_vault.revoke(sub.token_id)
        await mcp_server_connections[sub.server_id].send_kill(sub.session_id)
    # Poll for confirmation with exponential backoff
    for attempt in range(5):
        alive = await session_registry.count_alive_children(session_id)
        if alive == 0:
            return True
        await asyncio.sleep(2 ** attempt)
    # After 5 retries (~62s), escalate to hard-kill
    await hard_kill(session_id)
```

Set a hard-kill timeout: if sub-agents don't acknowledge within 60 seconds, terminate at the container/process level. Every running container has a parent — find it and stop the tree.

### Layer 3: State Freeze (instant, <1ms)

Before killing anything, freeze the context. The state at the moment of kill is your only evidence for the postmortem:

```python
async def freeze_and_kill(session_id: str):
    session = await session_store.get(session_id)
    # Archive: context window, tool call history, all sub-sessions
    await audit_log.write({
        "event": "KILL_SWITCH_FIRED",
        "session_id": session_id,
        "timestamp": utcnow(),
        "context_snapshot": session.context_window[-4096:],  # last 4K chars
        "tool_call_chain": session.tool_call_history,
        "sub_agents_alive": await session_registry.get_children(session_id),
        "token_burn_rate": await cost_tracker.get_rate(session_id),
        "actions_taken": session.action_log,
    })
    await kill(session_id)
```

Without the state freeze, the kill switch fires and you have no evidence of what happened — making the postmortem guesswork and the regression prevention impossible.

### The Multi-Agent Orchestrator Case

The Stanford CodeX / CLTC review (May 2026) identifies the structural gap specifically for orchestrator-agent architectures:

> An agent that has already delegated sub-tasks to other agents, distributed API keys, and spawned parallel execution threads is not a single entity. Killing the parent does not recall the children.

For orchestrator-based systems, the kill switch must handle:

1. **Scope enumeration**: before firing, enumerate ALL spawned sessions — tool calls, MCP connections, worker processes
2. **Credential scatter**: check if sub-agents hold direct (non-inherited) credentials — if so, revoke those separately
3. **Graceful then hard**: attempt graceful halt first (SIGHUP-style), escalate to SIGKILL if not confirmed within 30s
4. **Multi-tier confirmation**: verify kill at the gateway level, at the MCP server level, and at the container level — three independent checks

```python
# Orchestrator-level kill with multi-tier confirmation
async def kill_agent_tree(orchestrator_session_id: str, grace_period: float = 30.0):
    # 1. Enumerate all known descendants
    descendants = await session_graph.get_descendants(orchestrator_session_id)
    all_sessions = [orchestrator_session_id] + descendants
    
    # 2. Fire kill signals in parallel
    await asyncio.gather(
        *[revoke_gateway_tokens(s) for s in all_sessions],
        *[mcp_server_kill(s) for s in all_sessions],
        return_exceptions=True
    )
    
    # 3. Wait for grace period
    await asyncio.sleep(grace_period)
    
    # 4. Hard-kill any survivors
    survivors = await find_surviving_sessions(all_sessions)
    if survivors:
        await asyncio.gather(
            *[container_kill(s) for s in survivors],
            return_exceptions=True
        )
    
    # 5. Verify total death
    assert await session_graph.count_living(all_sessions) == 0
```

### Triggering Conditions

Deterministic triggers beat LLM-judged triggers for kill switches. A kill switch routed through the model can be gamed, ignored, or delayed:

- **Token burn rate**: >3× baseline for this agent type → kill
- **Tool call loop**: same tool called >10× in 60 seconds with no state change → kill
- **Unauthorized action detected**: tool call targeting a tier-1 resource (destructive write, outbound comms) from an agent below trust level → kill + alert
- **Manual override**: human operator fires kill → kill
- **Automated escalation**: circuit breaker fires (S-204) 3× in 10 minutes → kill

## Receipt

> Verified 2026-07-07 — Pattern validated against: OpenClaw kill switch guide (March 2026), n1n.ai multi-agent kill switch architecture (May 2026), OWASP Top 10 for Agentic AI (S-259 kill-switch gap), Stanford CodeX / CLTC Agentic AI Risk-Management Standards Profile review (May 2026). All sources agree: killing the orchestrator ≠ killing the agent tree. The three-layer pattern (Token Revocation → Async Propagation → State Freeze) is the consensus architecture. Enterprise adoption of formal multi-agent kill switch procedures: <15% as of June 2026.

## See also
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — automated trigger conditions for the kill switch
- [S-205 · Agent Sandbox Isolation](s205-agent-sandbox-isolation.md) — limiting blast radius before you need the kill switch
- [S-313 · Agent Credential Lifecycle Security](s313-agent-credential-lifecycle-security.md) — why sub-agent credentials need individual lifecycle management
- [S-395 · Agent Cost Circuit Breakers](s395-agent-cost-circuit-breakers.md) — token-burn-rate as a kill switch trigger
- [F-180 · AI Incident Commander](forward-deployed/f180-ai-incident-commander.md) — what to do after the kill switch fires
