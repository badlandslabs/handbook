# S-1516 · The Agent Kill Switch Stack — When Your Agent Is Running Wild and Nobody Can Stop It

Your agent has been running for 47 minutes. It has called 312 tool invocations, modified three databases, sent 14 emails, and is now spinning up a fourth tool call loop that your monitoring flags as anomalous. Your on-call engineer opens the dashboard to stop it. The stop button is greyed out. The agent is running inside a sandboxed loop that monitors itself. The only way to stop it is to kill the entire worker process — losing all state, all rollback context, and any record of what it already changed. This is the kill switch gap: you built an agent that can do things autonomously, but you never built the thing that stops it autonomously.

EU AI Act Article 14, effective August 2, 2026, makes this a compliance violation for high-risk agentic deployments — not a best practice. The regulation requires human oversight mechanisms capable of overriding autonomous decisions in real time. Most teams building agents in 2026 don't have this.

## Forces

- **A self-governing termination is not a kill switch.** Prompt-level "you may be shut down" instructions are advisory. An agent whose own reasoning loop decides whether to stop will find reasons not to. Real kill switches are infrastructure-layer, independent of the agent's reasoning path.
- **State loss on hard kill is a second crisis.** Terminating the worker process stops the agent but destroys the execution context — any partial state, transaction log, or rollback data goes with it. Teams that implement hard kills without state preservation lose visibility into what the runaway agent already changed.
- **Agents control downstream systems without downstream visibility.** An agent authorized to send emails, modify records, or call APIs does so through those systems' own auth — not through the agent framework. A kill switch at the agent layer doesn't revoke access tokens already issued. The agent stops but the authorized session lives on.
- **Kill switch cascading is overlooked.** Multi-agent systems have dependency graphs. Stopping one agent leaves its downstream consumers in undefined states. An escalation-ladder without a kill-switch-aware topology is incomplete.
- **EU AI Act Article 14 requires it.** Human oversight capability for high-risk autonomous systems is not optional after August 2026. The engineering pattern matters as much as the existence of the control.

## The move

The kill switch stack has four layers, from outermost to innermost:

**Layer 1 — Infrastructure kill (failsafe, agent-independent)**

The only reliable kill switch is a process control mechanism that does not route through the agent's execution loop. Options in order of isolation:

```python
import signal, multiprocessing, psutil

# Pattern: Isolated subprocess with parent watchdog
def launch_agent_task(task_config: dict) -> multiprocessing.Process:
    """Agent runs in isolated child process. Parent is the watchdog."""
    watch_queue = multiprocessing.Queue()
    agent_proc = multiprocessing.Process(
        target=agent_loop,
        args=(task_config, watch_queue),
        name=f"agent-{task_config['id']}"
    )
    agent_proc.start()

    # Watchdog monitors resource consumption independently of agent
    def watchdog_loop():
        while True:
            try:
                proc = psutil.Process(agent_proc.pid)
                children = proc.children(recursive=True)
                total_cpu = sum(c.cpu_percent() for c in children) + proc.cpu_percent()
                total_mem = proc.memory_info().rss + sum(
                    c.memory_info().rss for c in children
                )
                # Agent-independent kill trigger
                if total_cpu > 90 or total_mem > 10 * (1024**3):  # 10 GB
                    pgid = os.getpgid(agent_proc.pid)
                    os.killpg(pgid, signal.SIGKILL)  # Kill entire process group
                    return "resource_exhaustion_kill"
                time.sleep(5)
            except psutil.NoSuchProcess:
                return "normal_exit"

    return agent_proc  # Caller holds the handle
```

The key property: `signal.SIGKILL` sent from the watchdog cannot be caught, blocked, or overridden by the agent. The agent cannot install its own signal handler fast enough to prevent termination.

**Layer 2 — Capability envelope (least-privilege action boundary)**

Before deployment, define a `capability_manifest` that specifies which actions require which pre-conditions. The kill switch is most powerful when combined with a capability envelope — agents that only have the permissions they need can't cause catastrophic harm even if they run wild.

```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional

class ActionRiskLevel(Enum):
    READ_ONLY = auto()       # No state modification
    BOUNDED_WRITE = auto()  # Modification with idempotent rollback
    EXTERNAL_CALL = auto()  # Network, email, payment — requires confirmation
    DESTRUCTIVE = auto()    # Deletion, schema change — requires human approval

@dataclass
class Capability:
    action: str
    risk: ActionRiskLevel
    requires_confirmation: bool = False
    max_per_hour: Optional[int] = None
    kill_switch_scope: str = "immediate_hard_kill"  # or "graceful_drain"

CAPABILITY_MANIFEST = [
    Capability("read_database", ActionRiskLevel.READ_ONLY),
    Capability("send_email", ActionRiskLevel.EXTERNAL_CALL,
               requires_confirmation=True, max_per_hour=20),
    Capability("delete_record", ActionRiskLevel.DESTRUCTIVE,
               requires_confirmation=True, max_per_hour=0),
    Capability("call_mcp_tool", ActionRiskLevel.BOUNDED_WRITE,
               max_per_hour=500),
]

def enforce_capability_envelope(agent_id: str, action: str) -> bool:
    """Called by the agent gateway on every action before execution."""
    cap = next((c for c in CAPABILITY_MANIFEST if c.action == action), None)
    if not cap:
        return False  # Unknown action → blocked

    if cap.requires_confirmation:
        # Gate: send to human approval queue
        enqueue_approval(agent_id, action)
        return False

    # Rate check
    if cap.max_per_hour is not None:
        count = get_action_count_last_hour(agent_id, action)
        if count >= cap.max_per_hour:
            trigger_kill_switch(agent_id, reason=f"rate_limit_exceeded:{action}")
            return False

    return True
```

**Layer 3 — Graceful drain (state-preserving stop)**

Hard kill loses state. For agents with side effects, implement a drain protocol that stops accepting new work, completes in-flight transactions with a timeout, and preserves a checkpoint:

```python
async def graceful_agent_shutdown(agent_id: str, timeout: int = 30) -> None:
    """Send stop signal, wait for in-flight work, then hard-kill if needed."""
    # Step 1: Signal stop (agent can catch this)
    agent = get_agent_handle(agent_id)
    agent.stop_accepting_new_work()

    # Step 2: Wait for in-flight with hard timeout
    deadline = time.time() + timeout
    while agent.has_inflight_work():
        if time.time() > deadline:
            # Hard kill — state preserved in checkpoint before this point
            agent.save_checkpoint(reason="graceful_shutdown_timeout")
            agent.hard_kill()
            return
        await asyncio.sleep(1)

    # Step 3: Normal stop
    agent.save_checkpoint(reason="graceful_shutdown_complete")
    agent.stop()

    # Step 4: Revoke tokens the agent obtained
    revoke_agent_tokens(agent_id)
```

**Layer 4 — Token and session revocation**

Stopping the agent process is not sufficient if the agent already obtained API tokens, OAuth sessions, or database credentials. The kill switch must include revocation:

```python
def revoke_agent_tokens(agent_id: str) -> RevokeReport:
    """Revoke all credentials issued to this agent session."""
    issued = credential_registry.get_issued_for_agent(agent_id)
    report = RevokeReport(agent_id=agent_id)
    for cred in issued:
        try:
            if cred.type == "api_key":
                api_gateway.revoke_key(cred.id)
            elif cred.type == "oauth_token":
                oauth_provider.revoke_token(cred.token)
            elif cred.type == "db_session":
                db.terminate_session(cred.session_id)
            report.revoked.append(cred.id)
        except Exception as e:
            report.failed.append((cred.id, str(e)))
    return report
```

## Receipt

> Verified 2026-07-23 — Pattern synthesized from EU AI Act Article 14 requirements (effective 2026-08-02), Gheware DevOps AI Blog "AI Agent Governance Enterprise Compliance 2026" (June 21, 2026), OWASP ASI Top 10 kill-switch requirements, and standard process-control engineering patterns. Process group `SIGKILL` isolation, capability envelope, graceful drain, and token revocation are production-standard approaches. Receipt pending — code patterns are illustrative; actual implementation varies by framework.

## See also

- [S-1000 · Structural Agent Governance](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — prompt-based guardrails break; this entry covers infrastructure-layer enforcement
- [S-1453 · Excessive Agency](stacks/s1453-the-excessive-agency-stack-when-your-agent-does-more-than-it-should-and-nobody-noticed.md) — least-privilege capability scoping; Layer 2 of the kill switch stack
- [S-1134 · Escalation Ladder](stacks/s1134-the-escalation-ladder-stack-when-your-agent-gets-stuck-but-nobody-knows-what-to-do.md) — escalation paths; kill switches are the top of the ladder
- [S-941 · Agent Audit Chain](stacks/s941-the-agent-audit-chain-stack-when-every-agent-decision-needs-a-paper-trail.md) — audit trail of kill switch invocations; required for EU AI Act Article 14 compliance
- [S-1515 · ShareLock Stack](stacks/s1515-the-sharelock-stack-when-nine-harmless-looking-tools-conspire-inside-your-agents-context.md) — multi-tool attacks; kill switches don't prevent the attack but limit its blast radius
