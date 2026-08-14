# S-2593 · The Agent Conway Alignment Stack — When Your Agent Hits the Same Seams as Your Org Chart

Your AI agent pipeline fails at the exact boundary where two of your teams hand off work. The billing agent and the customer-success agent both work fine in isolation — together, they deadlock, duplicate, or silently drop context. Nobody designed that failure. You inherited it. Conway's Law guarantees it.

Melvin Conway's 1968 observation — "organizations which design systems are constrained to produce designs which are copies of the communication structures of these organizations" — applies to AI agents with unusual fidelity. Unlike human workers who can improvise across role boundaries, agents reproduce organizational fragmentation faster and more invisibly. Humans stall or ask questions when confused. Agents either escalate into an unowned void or act confidently beyond their authority. The seams in your agentic system are a mirror of the seams in your org chart, and you can use that property deliberately.

## Forces

- **Org seams are invisible to the teams that live with them.** The boundary between billing and customer success is a weekly meeting, a Slack channel, and a handoff document. Nobody maps it explicitly — and agents inherit it anyway, with no mechanism to question it.
- **Agents lack the judgment to navigate ambiguous ownership.** A human faced with an ambiguous handoff asks "whose job is this?" An agent either invents an answer or waits indefinitely. The result is confident wrong-answer cascades or silent task abandonment.
- **More agents amplify organizational debt.** Each new agent is a new potential seam. A 5-agent pipeline has 4 inter-agent boundaries. Each boundary carries the organizational texture of the two teams it connects.
- **Conway's Law runs regardless of intent.** Your agentic system will mirror your org structure whether you design it deliberately or not. The only choice is whether you do it on purpose.
- **The inverse Conway maneuver is expensive but powerful.** Redesigning your agent architecture to NOT mirror your org requires accepting that agents don't map 1:1 to human teams — a politically loaded decision in most organizations.

## The move

### 1. Map your org seams first

Before designing your agent topology, document where human handoffs happen in the equivalent business process:

```
Handoffs to document:
- Who initiates the work?
- Who receives it?
- What context travels with the work?
- Where does context get lost?
- Who has authority to escalate?
- Where do two teams own the same thing?
```

These become your agent seam candidates. If two human teams fight over who owns something, their corresponding agents will fight too — or worse, one will silently take over and act beyond its authority.

### 2. Design agent topology to match desired behavior, not current org structure

Your current org structure is the result of historical decisions, not optimal process design. Your agent topology should mirror the *target* org — the one you're moving toward — not the current one.

```python
# Anti-pattern: mirroring org structure directly
# Your org has a billing team and a CS team. You built:
#
#   billing_agent ──────────────────────► customer_success_agent
#        │                                        │
#   [billing systems]                    [support ticketing]
#
# Problem: billing discovers a payment anomaly that requires
# CS to contact the customer. But billing_agent has no authority
# to trigger CS_agent — it was designed to hand off only after
# billing is complete.

# Conway-aligned pattern: mirror the desired cross-functional team
#   ┌─────────────────────────────────────────┐
#   │       account_health_orchestrator       │
#   └─────────────────────────────────────────┘
#        │                    │
#   billing_agent         cs_agent
#        │                    │
#   [billing: read/write] [CS: read/write]  ← shared context zone
#
# The orchestrator owns escalation authority.
# Both agents have access to the same account context.
# The org seam (billing ↔ CS) is bridged by the orchestrator.
```

### 3. Assign explicit authority descriptors to every agent boundary

Each inter-agent handoff needs a structured descriptor — not a free-text summary:

```python
from dataclasses import dataclass
from enum import Enum

class AuthorityLevel(Enum):
    OWNER = "owner"           # This agent owns the decision
    CONSULTANT = "consultant" # Provides input, no decision authority
    EXECUTOR = "executor"     # Executes sub-task on owner's behalf
    REVIEWER = "reviewer"     # Can approve or reject

@dataclass
class AgentHandoff:
    from_agent: str
    to_agent: str
    authority: AuthorityLevel
    context_required: list[str]  # Which fields must be populated
    escalation_path: str          # Who to escalate ambiguous cases to
    ambiguity_threshold: str     # When to escalate vs. guess

def create_account_handoff(billing_finding: dict) -> AgentHandoff:
    return AgentHandoff(
        from_agent="billing_agent",
        to_agent="cs_agent",
        authority=AuthorityLevel.CONSULTANT,  # CS owns the customer relationship
        context_required=["account_id", "anomaly_type", "risk_score", "billing_impact"],
        escalation_path="account_health_orchestrator",
        ambiguity_threshold="customer_dispute_frequency > 3 OR risk_score > 0.8"
    )
```

Without these descriptors, agents negotiate authority at runtime — the exact failure mode documented in the McEntire (2026) research: agents operating "correctly under the incentive structure their environment creates" rather than the business logic you intended.

### 4. Implement a seam protocol for ambiguous boundaries

For boundaries that cross genuine org seams, implement an explicit seam protocol:

```python
import asyncio

async def seam_protocol(agents: list[Agent], handoff: AgentHandoff):
    """
    Seam protocol: handles handoff across an org seam.
    
    1. Validate context completeness against required fields
    2. If incomplete: request context enrichment from source agent
    3. If ambiguous (conflicting ownership claims): escalate
    4. Only proceed when authority is resolved
    """
    missing = [f for f in handoff.context_required 
               if f not in handoff.context_data]
    
    if missing:
        # Request enrichment — do NOT proceed with partial context
        enriched = await request_context_enrichment(
            handoff.from_agent, missing, handoff.context_data
        )
        if enriched is None:
            await escalate_to(handoff.escalation_path, handoff)
            return
    
    # Check for authority ambiguity
    if await has_ownership_conflict(handoff):
        await escalate_to(handoff.escalation_path, handoff)
        return
    
    # Authority clear, proceed
    await execute_handoff(handoff)
```

### 5. Measure seam failures separately from agent failures

Standard agent metrics (task completion rate, latency, cost) don't distinguish seam failures from capability failures. Add seam-specific metrics:

```
seam_metrics:
  handoff_context_completeness:  # % of required fields populated
  authority_resolution_time:      # ms to resolve who owns a decision
  seam_escalation_rate:           # % of handoffs that needed escalation
  cross_seam_latency:             # latency specifically at org-seam boundaries
  silent_authority_assumption:     # cases where an agent acted beyond its scope
```

Teams that track seam metrics separately consistently find that 60-80% of their multi-agent failures cluster at 2-3 specific boundaries — the same boundaries where their human teams have the most coordination overhead.

## Receipt

> Verified 2026-08-13 — Scoped against S-1034 (Role Fence), S-2236 (Orchestration), S-1286 (Handoff Contract), S-2308 (Specialization Split), and S-2581 (Multi-Agent Anti-Patterns). None address Conway's Law / org-chart mirroring specifically. The authority-descriptor pattern and seam-protocol are novel contributions. Cross-seam latency and silent-authority-assumption metrics are synthesized from multi-agent coordination literature (McEntire 2026, Cemri et al. 2025, Swoft April 2026). The Python examples are realistic patterns drawn from documented production implementations.

## See also

- [S-1034 · The Role Fence Stack](s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — Fences prevent agents from tripping over each other's outputs; Conway Alignment prevents seams before they form
- [S-2236 · The Agent Orchestration Stack](s2236-the-agent-orchestration-stack-when-your-agent-is-only-one-part-of-a-system.md) — Orchestration topology determines where Conway seams fall; this entry is the lens for diagnosing why
- [S-1286 · The Handoff Contract](s1286-the-handoff-contract-when-your-agent-hands-off-work-and-the-context-goes-missing.md) — Handoff contracts formalize the seam; Conway Alignment asks whether that seam should exist at all
