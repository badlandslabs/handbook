# S-1972 · The Agent Approval Gate Stack — When Your Agent Wants to Act and You Need It to Wait

Your agent just drafted an email to all 12,000 customers, queried the production database to backfill missing records, and wants to send a $40,000 wire transfer. It completed every step correctly. It has no mechanism to stop. This is not a failure state — it is an architecture gap. The fix is an approval gate: a defined pause point where the agent yields to a human before executing a class of actions, then resumes or redirects based on the decision.

## Forces

- **Autonomy vs. accountability trade-off.** The whole point of an agent is to act without a human in the loop. But the more consequential the action, the less tolerable autonomous execution becomes. An agent that books a flight is helpful. One that books a corporate retreat burns trust.
- **Gartner's 40% abandonment rate.** Gartner estimates 40% of agentic AI projects started in 2025 will be abandoned by 2027, with the primary cause being trust failure — not technical failure. Teams that ship agents without approval gates hit the trust wall in production.
- **Framework support is uneven.** LangGraph, CrewAI, and AutoGen all expose some form of checkpoint/interrupt, but the depth, ergonomics, and production readiness differ dramatically. Choosing the wrong framework means retrofitting approval gates into a system not designed for them.
- **High-stakes vs. reversible tension.** Not every action needs a human. The trick is matching the gate threshold to the actual consequence — too many gates make the agent useless, too few make it dangerous.

## The move

**Define an action-tier taxonomy, then map each tier to a gate mechanism.**

- **Tier 0 — Inform only.** Agent informs via Slack/email; no blocking gate. Example: generating a weekly summary.
- **Tier 1 — Soft notification with escape hatch.** Agent notifies the human and waits N minutes; auto-proceeds if no objection. Example: updating a draft document.
- **Tier 2 — Explicit approval required.** Agent pauses, presents the planned action + rationale, waits for approve/reject/modify. Example: sending a customer-facing email, updating a live record.
- **Tier 3 — Segregated execution.** Agent prepares the action payload; a separate human-privileged process executes it. Example: database writes, financial transactions, production deployments.

**Implement checkpoint interrupts at the framework level, not in prompts.**

LangGraph's `interrupt()` is the most mature production implementation. Call `interrupt("Awaiting approval for: {action}")` inside the graph at the gate node; the graph freezes and persists state to the thread store. The human reviews via a separate endpoint (dashboard, Slack command, API call) that calls `Command(resume=True, arg={"decision": "approve"})` — the graph resumes from exactly the interrupted node.

```python
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command

def approval_node(state):
    proposed = state["planned_action"]
    # Persist proposed action to human-review queue
    enqueue_for_review(proposed)
    # Freeze the graph until human resolves
    result = interrupt({"type": "approval_request", "action": proposed})
    return {"decision": result["decision"]}

def execute_node(state):
    if state["decision"] != "approved":
        raise AbortException("Action was not approved")
    return run_action(state["planned_action"])

graph = StateGraph(AgentState)
graph.add_node("approval", approval_node)
graph.add_node("execute", execute_node)
graph.add_edge("approval", "execute")
```

For **CrewAI**, use `human_input=True` on specific tasks — the agent pauses and requests terminal/stdin input. For production deployments, wrap the CrewAI executor to surface the prompt via an HTTP endpoint instead of stdin.

For **AutoGen**, the `human_input_mode` parameter on agent construction accepts `ALWAYS`, `TERMINATE`, or `NEVER`. Set `ALWAYS` for high-stakes agents. AutoGen routes human input through a proxy agent pattern — for production, replace the proxy with a webhook handler.

**Instrument every gate.** Log the proposed action, the approving/rejecting human, the decision timestamp, and the elapsed time from proposal to resolution. This audit trail is what makes HITL defensible in EU AI Act and SOC 2 audits.

**Tier thresholds should be policy, not code.** Define thresholds in a YAML or JSON policy file (e.g., `approvals.yaml`) keyed by action type, cost, audience size, and reversibility. The code reads the policy; the policy is owned by the business, not the engineer.

## Evidence

- **Framework comparison:** LangGraph earns 5/5 stars for HITL support in enterprise evaluations; CrewAI earns 2/5. LangGraph's graph interruption with state persistence is described as "the only production-ready choice" for compliance workflows where humans need to review mid-workflow and agents need to resume cleanly after overnight pauses. — *Enterprise framework comparison, TowardsAI/Muitech, 2026-04*
  - https://pub.towardsai.net/langgraph-vs-crewai-vs-autogen-which-ai-agent-framework-should-your-enterprise-use-in-2026-3a9ebb407b09

- **Framework patterns by name:** AutoGen uses `human_input_mode` with `ALWAYS`/`TERMINATE`/`NEVER` options. CrewAI uses `human_input=True` parameter on tasks. LangGraph uses explicit human nodes in the workflow graph that call `interrupt()`. OpenAI Agents SDK uses handoff primitives that can route to humans. — *47Billion enterprise agent framework analysis, 2026-02*
  - https://47billion.com/blog/ai-agents-in-production-frameworks-protocols-and-what-actually-works-in-2026/

- **HITL spectrum and abandonment data:** Three-level classification: HITL (explicit approval), HOOTL (human-on-the-loop, reviews after), HOTL (human-out-of-the-loop, autonomous). Gartner's 40% abandonment figure for 2025-launched agentic projects cited as primary cause: trust failure. — *Paperclipped HITL design patterns guide, 2026-02-09*
  - https://www.paperclipped.de/en/blog/human-in-the-loop-ai-agents/

## Gotchas

- **Gates without instrumentation are invisible.** If you can't see that a gate fired, who approved it, and what they decided, the approval mechanism provides no audit trail — it is theater, not governance.
- **AutoGen's human_input_mode proxies through a separate agent.** In production, this means the human isn't reviewing the actual plan — they're responding to a text prompt from a proxy agent. The proxy can mangle the request. Route the actual proposed action to the human, not a description of it.
- **CrewAI HITL requires custom wrappers for anything beyond demo-level.** The `human_input=True` parameter reads from stdin in the default CLI executor. In a web service, you need to replace the executor with an async queue-backed handler. Budget the wrapper work — it is not zero.
- **Blocking gates create a new failure mode: human latency.** If the approving human is on a different timezone or doesn't check their queue, the agent is frozen indefinitely. Pair gates with SLA timers that escalate to a fallback approver or abort the action after N hours.
