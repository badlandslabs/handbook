# S-1323 · The Reversibility Gate Stack — When Your Agent Commits Before Checking If It Can Roll Back

Your agent just sent 47,000 emails to customers, deleted a production database table, and transferred funds to the wrong accounts. In each case, the agent had the tools, the permissions, and the confidence. What it didn't have was a pre-flight check: *can this be undone?* No alert fired. No gate held. The irreversible action executed in the same step as the reversible ones.

This is the **Reversibility Gate** — a pre-execution classification layer that forces every action through one question before any tool call dispatches. It's the difference between an agent that can recover from mistakes and one that creates permanent ones.

## Situation

You deploy an agent to handle customer onboarding, invoice processing, and CRM updates. It works well for months. Then a prompt drift or unexpected input causes it to chain: read customer list → update CRM → send welcome emails → post to Slack → mark done. Somewhere in the chain it reads stale state and sends the wrong welcome email to 200 customers. Or it overwrites a field and the previous CRM data is gone. No error occurred — the API returned 200. The agent didn't know it was doing something irreversible until it was already done.

## Forces

- **Agent autonomy and safety are in tension.** Maximum autonomy means maximum blast radius. Every tool the agent can call is a potential irreversible action. Permitting all tools is dangerous; permitting none defeats the purpose.
- **Reversibility is not binary.** A database write is not the same as an email send. A Slack message can be deleted; a fund transfer cannot. Classifying everything as "irreversible" makes the gate useless; treating everything as "safe" makes the gate invisible.
- **The gate must fire before execution, not after.** Post-hoc logging tells you what broke; it doesn't prevent the break. The reversibility check must gate the tool call itself, not observe it in passing.
- **Compensation is not restoration.** If the action cannot be undone, compensation (a mitigating follow-up) is the next best thing. But compensation must be planned before execution, not improvised after failure.

## The move

### The four-tier action classification

Before every tool call, the execution layer classifies the action into one of four tiers:

| Tier | Label | Definition | Enforcement |
|------|-------|------------|-------------|
| **1** | Read-only | No external state change — queries, reads, searches | Proceed freely. Log for audit. |
| **2** | Reversible | External change with an undo path — create/update where a revert exists | Proceed with a 30-second compensation window. If the action fails or the outcome mismatches intent within the window, trigger rollback automatically. |
| **3** | Compensatable | Irreversible but mitigable — sent emails, posted messages, API calls that can be followed by a correction | Proceed only if a compensation plan exists in the execution context. The plan must name the compensating action and its trigger conditions. |
| **4** | Irreversible | No undo, no reliable compensation — financial transactions, deletes, permission changes | Block. Require human approval. Escalate with full context (intent, stakes, alternatives). |

### Implementation

```python
class ReversibilityGate:
    def classify(self, tool_call: ToolCall, context: AgentContext) -> ActionTier:
        tool = tool_call.name
        params = tool_call.params

        # Tier 1: Read-only
        if tool in READ_ONLY_TOOLS:
            return ActionTier.READ_ONLY  # proceed

        # Tier 4: Hard block
        if tool in IRREVERSIBLE_TOOLS or self._has_irreversible_params(params):
            return ActionTier.IRREVERSIBLE  # block + escalate

        # Tier 2: Check for undo path
        if self._has_revert_operation(tool, params):
            return ActionTier.REVERSIBLE  # proceed + enable rollback window

        # Tier 3: Compensatable if a plan exists
        compensation_plan = self._find_compensation_plan(tool, context)
        if compensation_plan:
            return ActionTier.COMPENSATABLE  # proceed + attach plan
        else:
            return ActionTier.IRREVERSIBLE  # no plan → treat as irreversible

    def dispatch(self, tool_call: ToolCall, tier: ActionTier) -> ToolResult:
        if tier == ActionTier.IRREVERSIBLE:
            raise HumanApprovalRequired(tool_call, context=self.context)
        if tier == ActionTier.COMPENSATABLE:
            self._attach_compensation_watcher(tool_call)
        return self._execute(tool_call)
```

### Compensation plan structure

For Tier 3 actions, attach a structured plan before execution:

```json
{
  "action": "send_email",
  "params": { "to": "customers@example.com", "template": "welcome" },
  "compensation": {
    "action": "send_email",
    "params": { "to": "customers@example.com", "template": "retraction" },
    "trigger": "outcome_mismatch | human_flag | 5m_timeout"
  },
  "escalation_contact": "onboarding-team-lead"
}
```

### The compensation watcher

After dispatching a compensatable action, a background watcher monitors the outcome:

1. **Outcome mismatch** — the agent's model of the result diverges from the actual API response → trigger compensation immediately.
2. **Human flag** — a human operator marks the action as incorrect → trigger compensation.
3. **Timeout** — no confirmation of intended effect within the window → trigger compensation.

The watcher runs asynchronously. It does not block the agent's main loop, but it does open a compensation context that can interrupt if the agent continues incorrectly.

### Key insight: the gate is a classifier, not a firewall

The Reversibility Gate does not enumerate dangerous tools. It classifies every tool dynamically based on:
- The specific parameters being sent (deleting record ID 42 ≠ deleting all records)
- The current execution context (a DELETE in a sandbox environment is Tier 1)
- The availability of a compensation path

This means the same tool can move between tiers based on what it is being asked to do. The classification is dynamic, not static-deny list.

### LangGraph integration

LangGraph's error edges map naturally to the Reversibility Gate:

```python
from langgraph.graph import StateGraph
from langgraph.types import Send

def reversibility_edge(state):
    tool_call = state["next_tool"]
    tier = gate.classify(tool_call, state["context"])
    if tier == ActionTier.IRREVERSIBLE:
        return "human_approval"
    elif tier == ActionTier.COMPENSATABLE:
        return "execute_with_watcher"
    else:
        return "execute"

graph.add_conditional_edges("classify", reversibility_edge)
```

### Rollback coverage metric

Track **Rollback Coverage Rate (RCR)**: the fraction of Tier 3 actions that have a valid compensation plan attached. Target >95% for production agent fleets. Actions without plans are treated as Tier 4 (blocked by default in strict mode).

## Receipt

> Receipt pending — 2026-07-18. Four-tier taxonomy from Paperclipped "AI Agent Reversibility Checks" (March 2026). $47,000 silent rework loop case study documented there. Compensation plan JSON structure synthesized from Curve Labs RFTC research. LangGraph error-edge integration pattern from LangChain State of Agent Engineering 2026. RCR metric from Curve Labs research. Distinct from S-1005 (AI SRE — post-hoc reliability) and S-1069 (sandboxing — isolation, not reversibility).

## See also

- [S-1012 · The Failure Recovery Stack](s1012-the-failure-recovery-stack-when-your-agent-has-to-figure-out-what-to-do-when-things-go-wrong.md) — covers recovery mechanics after failure; this entry covers pre-failure prevention via action classification
- [S-1265 · The Agent Kill Switch Stack](s1265-the-agent-kill-switch-stack-when-your-agent-is-breaking-things-and-nobody-can-stop-it.md) — covers post-failure containment and halting; this entry covers pre-failure gating and compensation planning
- [S-1005 · The AI SRE Stack](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — covers production reliability practices; this entry covers the specific gap of action-level reversibility enforcement
