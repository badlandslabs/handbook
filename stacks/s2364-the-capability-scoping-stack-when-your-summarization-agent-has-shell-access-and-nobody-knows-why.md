# S-2364 · The Capability Scoping Stack — When Your Summarization Agent Has Shell Access and Nobody Knows Why

Your summarization agent is processing internal meeting notes. It has shell access, subagent spawning permissions, and credential-store read rights — because that's what your OpenClaw runtime exposes to every session by default. Nobody added those capabilities on purpose. Nobody reviewed them. The tool inventory grew organically, and now a summarization task carries the same attack surface as a code deployment task: a **15–19× overprovision ratio** with no owner, no review, and no metric tracking it.

This is the capability overprovisioning problem. It is not a model failure — the model is doing exactly what it's designed to do. It is an infrastructure architecture failure: tools are exposed to sessions without scoping to task type, creating an attack surface that compounds silently.

## Forces

- **Open-source agent runtimes expose every tool to every session.** OpenClaw v2026.3.28 (and most runtimes) ships with all available tools in scope for all sessions by default. The capability surface is the union of everything installed, not the intersection of what a given task needs.
- **The Skill Economy Ratio (SER) quantifies overprovisioning.** Sidik & Rokach (arXiv:2604.11839, NeurIPS 2026 Agent Safety Workshop) define `SER = tools_actually_needed / tools_exposed`. Baseline OpenClaw achieves SER = 0.053 — meaning only 5.3% of exposed capabilities are actually used. The ideal is 1.0. Existing defenses (NemoClaw sandbox, Cisco DefenseClaw skill scanner) address containment and threat detection but don't learn the minimum viable capability set per task.
- **Tool visibility changes model behavior.** A model that can see shell execution considers it. A model that can see subagent spawning uses it. The capability surface isn't just a security boundary — it shapes the agent's action space. Scoping what the agent is *aware of* changes which solutions it generatesdate: 2026-08-09.
- **Runtime-based governance (S-574) and ambient authority bucketing (S-743) cover adjacent problems but not this one.** S-574 handles credential scoping per NHI principal. S-743 handles tool schema poisoning. Neither addresses the question of which tools the agent should be aware of at all, based on task classification.

## The move

The fix is **three-layer adaptive capability governance**: scope what the agent is aware of, intercept what it tries to use, and learn the minimum viable set per task type from audit data.

### Layer 1 — Capability Governor: task-scope tool awareness

Classify the incoming task type at session start. Dynamically restrict which tools appear in the system prompt (not just which are allowed — which are *visible*).

```python
from agentwarden import CapabilityGovernor

governor = CapabilityGovernor()

async def start_session(task: TaskRequest) -> ScopedSession:
    task_type = governor.classify(task.description)  # "summarize" | "deploy" | "research" | ...
    allowed_tools = governor.get_toolset(task_type)
    # Returns only tools relevant to this task type
    # All others are excluded from the system prompt entirely
    return ScopedSession(
        session_id=task.session_id,
        visible_tools=allowed_tools,
        task_type=task_type,
    )
```

Task classification uses a lightweight classifier or rule engine over the task description, not an LLM call — it must be fast and deterministic.

### Layer 2 — Safety Router: runtime intercept before execution

Even with awareness scoping, intercept every tool call before execution. A hybrid rule-based + fine-tuned classifier catches calls that escaped Layer 1 (or were added after policy was written).

```python
from agentwarden import SafetyRouter

router = SafetyRouter()

async def on_tool_call(call: ToolCall) -> RoutingResult:
    result = router.evaluate(call)
    if result.status == "BLOCKED":
        logger.warning(f"Blocked tool call: {call.tool_name} — {result.reason}")
        raise ToolCallBlocked(f"{call.tool_name}: {result.reason}")
    elif result.status == "ESCALATE":
        # Route to human for approval before execution
        await human_approval_queue.put(call)
    return result
```

The Safety Router (AgentWarden Layer 3) uses a fine-tuned classifier over call metadata (tool name, parameters, call frequency, time-of-day) rather than a generic LLM prompt. Rule-based patterns catch known-high-risk combos (e.g., file write + shell + network) without LLM latency.

### Layer 3 — PPO Learning Policy: learn the minimum viable toolset from audit data

Accumulate audit logs. Train a PPO policy on which tools are actually needed per task type across your fleet. Re-scope Layer 1 tool awareness automatically as patterns emerge.

```python
# Sidik & Rokach: PPO training loop over accumulated audit logs
# SER improves from 0.053 (baseline) to 0.557 (10.5× improvement) in batch mode (N=500)
# 73% attack surface reduction on live OpenClaw deployment

from agentwarden.ppo import PPOGovernancePolicy

policy = PPOGovernancePolicy(
    audit_log_path="gs://agent-audit/audit_logs/",
    task_types=["summarize", "deploy", "research", "admin"],
)
policy.train(epochs=100)
policy.deploy()  # Updates Capability Governor toolset for each task type
```

On AgentDojo adversarial benchmarks: AgentWarden reduced successful attack rate from 90.3% to 88.9% (vs baseline unprotected). The absolute numbers are modest because this is a defense-in-depth layer, not a replacement for containment — but the SER improvement demonstrates that the attack surface shrinks meaningfully.

### Operational metric: track SER per task type

```python
# SER dashboard per task type — run weekly
import pandas as pd

def compute_ser_by_tasktype(audit_df: pd.DataFrame) -> pd.Series:
    exposed = audit_df.groupby("task_type")["tools_exposed"].first()
    used = audit_df.groupby("task_type")["tools_invoked"].nunique()
    return (used / exposed).rename("SER")

ser_report = compute_ser_by_tasktype(audit_df)
# Alert if SER < 0.3 for any task_type (high overprovisioning)
# Alert if SER > 0.95 (potential under-scoping — task blocked)
```

Target SER: 0.7–0.9 per task type. Below 0.5 means the task type is over-scoped. Above 0.95 means you may be blocking legitimate tool use — check your task classifier.

## Receipt

> Verified 2026-08-09 — arXiv:2604.11839 (AgentWarden, Sidik & Rokach, NeurIPS 2026 Agent Safety Workshop): OpenClaw baseline SER=0.053; AgentWarden achieves SER=0.557 (10.5× improvement, N=500 batch sessions). Attack surface reduction: 73% on live deployment with DeepSeek-chat. AgentDojo adversarial benchmark: BU=89.7%, ASR=88.9% (defended) vs ASR=90.3% (baseline). GitHub: github.com/sidikbro/agentwarden-core. SecAgentLabs (2026-06-24): capability-based security for agent tools via scoped per-tool tokens and object capabilities — complementary architectural pattern. EU AI Act Article 12 (full enforcement from 2026-08-02) requires audit trail and traceability for autonomous agent decisions; SER metrics provide the per-task accountability layer regulators will look for. Real tradeoffs: PPO training requires meaningful audit log volume (cold-start problem); Layer 3 re-scopes slowly and may lag fast-changing tool inventories; Safety Router adds ~5–15ms latency per tool call depending on classifier complexity.

## See also

- **[S-574 · Agent Per-Principal, Per-Endpoint Least Privilege](stacks/s574-agent-per-principal-per-endpoint-least-privilege.md)** — NHI-as-first-class-principal, brokered credentials, per-endpoint authorization. Capability Scoping governs *which tools the agent can consider*; S-574 governs *what the agent's credentials can do*. Different layers of the same problem.
- **[S-743 · MCP Tool Description Poisoning: The Schema Is the Attack Surface](stacks/s743-mcp-tool-description-poisoning-the-schema-is-the-attack-surface.md)** — Tool descriptions are LLM instruction at session start. Tool poisoning affects the content of what the agent sees; Capability Scoping affects whether the agent sees it at all. Defense in depth: scope what tools exist, then verify what those tools' schemas say.
- **[S-1065 · The Inter-Agent Trust Escalation Stack](stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md)** — Multi-agent delegation bypasses authentication boundaries. Capability Scoping limits what a delegated agent can do even if it receives a trusted-seeming request. Trust escalation is blocked at the capability level when the receiving agent has no shell/subagent access in its task type scope.
