# S-1689 · The Tiered Approval Stack — When Your Agent Waits for You at the Wrong Moment

Your customer support agent autonomously reads tickets, drafts replies, and looks great in demos — until it starts sending replies without approval. You add a human-in-the-loop gate. Now it asks for approval on every action, including "read the knowledge base." Nobody wants to babysit it. You need the right gate in the right place: fully autonomous for low-stakes reads, escalated for anything that touches the customer. The pattern is action-level autonomy, not agent-level.

## Forces

- **Agents are not uniformly risky.** A single agent can read documents, draft summaries, query databases, send emails, and delete records — each with wildly different risk profiles. Agent-level autonomy means you either lock it all down or open it all up. Both are wrong.
- **Approval gates placed at the wrong granularity collapse into rubber-stamping.** When an agent pauses for approval on 95% of its actions, reviewers stop reading and start clicking. False approval is worse than no approval — it creates an audit log without an audit function.
- **Context evaporates across boundaries.** An approval gate that lives outside the runtime (a separate ticketing queue, an email thread) loses the agent's working state. The reviewer approves an action without knowing what the agent was about to do, what context it had, or what the alternative was. Approval given in a void is not real oversight.
- **Maximum autonomy is a local maximum, not the goal.** Teams treat full automation as the graduation milestone. The actual goal is calibrated human oversight — present where it changes outcomes, absent where it doesn't. The difference is structural, not philosophical.

## The Move

### 1. Classify actions by risk axis, not by agent

Split on two dimensions:

| | **Reversible** | **Irreversible** |
|---|---|---|
| **Internal** | Read docs, search KB, draft summary | Modify memory, update session state |
| **External** | Read customer data, query DB | Send email, delete records, spend money, API writes |

Internal + Reversible = fully autonomous. External + Irreversible = mandatory gate. Everything else is tiered.

### 2. Place gates at the action boundary, not the session boundary

```python
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Awaitable

class ActionRisk(Enum):
    READ = "read"           # fully autonomous
    WRITE_INTERNAL = "write_internal"   # warn + log
    WRITE_EXTERNAL = "write_external"  # approve
    DESTROY = "destroy"     # two-person control

@dataclass
class ApprovalGate:
    action_type: ActionRisk
    threshold: float          # cost of mistake in USD
    latency_budget_ms: int     # how long to wait for human

    def requires_approval(self) -> bool:
        return self.action_type in (
            ActionRisk.WRITE_EXTERNAL,
            ActionRisk.DESTROY,
        )

# Agent action router
async def route_action(
    agent_id: str,
    action: AgentAction,
    context: dict,
    reviewer: Callable[[AgentAction, dict], Awaitable[ApprovalResult]],
) -> ActionResult:
    gate = get_gate(action.risk)
    state = await agent.runtime.state_snapshot()

    if gate.requires_approval():
        # Capture context BEFORE the gate, not after
        approval_request = ApprovalRequest(
            action=action,
            context=state,           # agent's working memory, tool outputs, reasoning
            risk_explanation=explain_risk(action),
            alternatives_considered=state.reasoning_trace[-3:],
            reviewer=route_reviewer(action),
            timeout_ms=gate.latency_budget_ms,
        )
        result = await reviewer(approval_request)
        if result.status == ApprovalStatus.REJECTED:
            return ActionResult(rejected=True, reason=result.feedback)
        if result.status == ApprovalStatus.TIMED_OUT:
            # Escalate or fail safe — don't proceed
            raise ApprovalTimeout(f"No reviewer available for {action}")

    return await execute(action)
```

### 3. Surface decision-grade context, not summary text

The reviewer needs what the agent had, not what the agent says. Include:
- **What the agent is about to do** (rendered action, not the LLM's description of it)
- **What it has already done** (prior steps in this session)
- **What the outputs were** (actual tool returns, not summaries)
- **What alternatives were considered** (reasoning trace — last 3 steps)
- **What the risk is** in operational terms: "This will send an email to 1,247 customers"

```python
def build_approval_context(
    state: RuntimeState,
    action: AgentAction,
) -> ApprovalContext:
    return ApprovalContext(
        rendered_action=render_action_for_human(action),
        session_history=state.step_history[-5:],
        tool_outputs={k: v.raw for k, v in state.tool_returns.items()},
        reasoning_trace=state.reasoning_trace[-3:],
        blast_radius=estimate_blast_radius(action),   # "affects 1,247 customers"
        reversibility=action.reversibility,
        has_rollback=action.has_rollback(),
    )
```

### 4. Route to the right reviewer by action type

Approval gates fail when sent to the wrong person. Route by capability, not availability:

```python
def route_reviewer(action: AgentAction) -> ReviewerRole:
    if action.risk == ActionRisk.DESTROY:
        return ReviewerRole.SUPERVISOR
    elif action.risk == ActionRisk.WRITE_EXTERNAL:
        if "billing" in action.target_domain:
            return ReviewerRole.FINANCE
        if "customer_communication" in action.type:
            return ReviewerRole.SUPPORT_LEAD
        return ReviewerRole.DOMAIN_OWNER
    return ReviewerRole.NONE
```

### 5. Design the timeout path, not just the approval path

The gate only works if the timeout is defined. Define three behaviors:

| Timeout | Behavior |
|---|---|
| < 5 min | Escalate to backup reviewer |
| 5–30 min | Log as delayed, continue tracking cost |
| > 30 min | Escalate to supervisor, pause agent |

```python
async def handle_approval_timeout(
    request: ApprovalRequest,
    elapsed_ms: int,
) -> ActionResult:
    if elapsed_ms < 5 * 60 * 1000:
        return await escalate_to_backup(request)
    elif elapsed_ms < 30 * 60 * 1000:
        await agent.runtime.log_delay(request, elapsed_ms)
        return ActionResult(waiting=True, queued=True)
    else:
        await agent.runtime.notify_supervisor(request)
        raise AgentPaused(f"Approval timeout exceeded for {request.action.type}")
```

## Receipt

> Verified 2026-07-26 — Pattern confirmed across AgentixForce (May 2026), CreateOS (June 2026), Neuronex Automation (2026), and Conceptualise (May 2026). Key implementation primitives: action-level risk classification, pre-gate state capture, reviewer routing by capability domain, tiered timeout escalation. Real tooling: AxmeAI agent-workflow-with-human-approval (GitHub, 2026-03-24) provides 3-line integration. Code examples above are composable from existing primitives (OpenAI Agents SDK, LangGraph checkpointing, Temporal).

## See also

- [S-1059 · The 88% Chasm](stacks/s1059-the-88-percent-chasm-why-ai-agent-pilots-stall-and-the-graduated-autonomy-playbook.md) — deployment sequence that precedes this runtime decision
- [S-1025 · When to Stop Orchestrating](stacks/s1025-when-to-stop-orchestrating-and-let-the-llm-drive.md) — framework selection vs. action-level autonomy
- [S-1005 · AI SRE](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — where approval gates fit in the broader reliability discipline
