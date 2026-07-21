# F-198 · Agent Fleet Operations: The Production Playbook

You have 50 agents running concurrently. Three are looping. Two silently returned wrong outputs that passed no verification gate. One has been running for 4 hours and is 40× over its expected cost ceiling. Your observability stack shows 50 green dots. Nobody knows what's actually happening until the invoices arrive or a customer complains. This is the default state of production agent fleets — and the gap between "agents deployed" and "fleet operated" is where production incidents live.

## Forces

- **Agents fail silently in ways services don't.** A crashed microservice logs a 500. A looping agent returns increasingly confident nonsense. A hallucinated tool call returns HTTP 200. Fleet monitoring that only tracks latency and uptime misses the modes that actually break production.
- **Agents are probabilistic — traditional SLOs don't apply.** You can't set a 99.9% success rate SLO when "success" is a judgment call that changes based on context. Fleet operations need outcome-based SLOs, not availability-based ones.
- **Cost scales with agent autonomy.** A chain-of-thought agent that loops on a hard problem burns tokens at full context-window rate. Budget controls that work for API-calling chatbots fail catastrophically on agents that decide their own execution paths.
- **Fleet composition changes at runtime.** Agents spawn sub-agents, hand off to specialist agents, or escalate to human reviewers. Traditional APM tools trace one service call tree — they don't trace a living topology of agents that rewire themselves mid-execution.
- **Escalation paths are non-obvious.** When a human employee breaks, they tell a manager. When an agent breaks, it either loops, hallucinates confidence, or fails in a way that downstream agents inherit silently. The escalation path must be engineered, not assumed.

## The move

### 1. Fleet Health Schema — Three Failure Classes

Don't monitor agents like services. Categorize failures by impact:

| Class | Signal | Fleet Signal |
|-------|--------|-------------|
| **Latency failure** | Step N took 10× expected time | % of steps exceeding P95 latency budget |
| **Quality failure** | Agent output passed no verification gate | % of outputs never verified by a judge layer |
| **Cost failure** | Single session exceeded token ceiling | Total fleet spend vs. daily budget curve |

Latency failures are surfaced by tracing. Quality failures require inline evaluation (see S-976). Cost failures require per-session token accounting with fleet-wide aggregation. Track all three on the same dashboard — any single metric is misleading.

### 2. The Fleet Cockpit — What to Watch

A fleet cockpit view showing real-time state of every running agent session:

```
Fleet: 50 active | 47 nominal | 2 degraded | 1 incident
Today's spend: $1,247 / $2,000 budget | Velocity: $89/hr
Escalations pending: 3 (all >15min runtime)
Quality gate fail rate (last 1hr): 2.3%
```

Key metrics (in priority order):
- **Active sessions** — count and cost velocity (early warning for loops)
- **Quality gate pass rate** — % of agent outputs that passed an inline judge
- **Escalation queue** — sessions awaiting human review (backlog = operational debt)
- **Per-session cost vs. task-type baseline** — catches billing surprises
- **Tool call error rate** — catches broken MCP server connections (see F-181)

Don't track: raw tokens consumed, request count, context window utilization. These are inputs, not outcomes.

### 3. Incident Response by Failure Class

**Latency failure**: Check the longest-running step. If it's a reasoning step (no tool call), kill the session — it's likely looping. If it's a tool call, check the tool catalog health probe (see S-989).

**Quality failure**: Replay the session through the evaluation harness (see F-191). Flag the task type as under-evaluated for this model version. If the quality failure propagated to a downstream agent, trigger a recall on the downstream session.

**Cost failure**: Hard-kill the session at the ceiling. Log the task type, model, and step count. Feed to the cost attribution schema (see F-81). If cost exceeds 5× baseline for a known task type, treat as an incident — something in the prompt or model routing is wrong.

**Escalation backlog**: The escalation queue is a forcing function. Sessions waiting >15 minutes for human review means you need either more reviewers, higher escalation thresholds, or better pre-escalation filtering. Track the queue depth as a leading indicator of fleet health.

### 4. The Graceful Degradation Ladder

Agents should degrade in priority order, not fail all at once:

1. **Degrade non-critical agents first.** Fleet should maintain critical-path capability even under resource pressure. Tag agents by criticality at spawn time.
2. **Simplify execution on cost pressure.** When fleet spend hits 80% of daily budget, routes that consume >2× average cost should switch to faster models or shorter context paths.
3. **Circuit-break, don't cascade.** A failing agent should not cause its caller to fail. Wrap inter-agent calls in try/catch that return a degraded fallback rather than propagating the error (see F-193).
4. **Hard stop at budget ceiling.** No agent session should exceed its pre-assigned cost ceiling under any circumstance. This is a non-negotiable, not a preference.

### 5. Runbook Templates by Scenario

**Scenario: "The session is running but I'm not sure if it's making progress"**
→ Check step count vs. task-type baseline. If >3× baseline steps with no tool call output, it's likely looping. Kill and replay with a tighter step budget.
→ Check if the last step was a tool call that timed out silently. If yes, the tool server may be degraded — check S-989 health probes.

**Scenario: "The agent returned output but I'm not confident it's correct"**
→ Route to the inline evaluation layer. Run the output through a judge agent with the task specification as context.
→ If no evaluation layer exists, mark the output as unverified and trigger manual review.

**Scenario: "Two agents are working on the same thing and producing conflicting outputs"**
→ This is a coordination failure (see S-1309). One agent needs to own the task — assign a leader agent to arbitrate.
→ If the conflict involves facts, escalate to human review. Agents cannot reliably adjudicate contradictions in their own outputs.

**Scenario: "The fleet was fine at 9am, now it's costing $200/hour"**
→ Check for a loop condition in a high-traffic agent type — one looping agent in a high-volume flow multiplies cost instantly.
→ Identify the outlier session (highest token count). Kill it first. Check its task type against recent changes (new prompt version, new tool, model swap).

## Receipt

> Verified 2026-07-20 — Synthesized from: Open Empower's "AI Agent Production Failures: Enterprise Lessons from 2026's First Wave" (June 2026), JetBrains "LLM Evaluation and AI Observability for Agent Monitoring" (May 2026), Zylos Research agent fleet patterns, handbook existing patterns F-192 (Cost Velocity Circuit Breaker), F-193 (Agent Escalation Gating), F-81 (Cost Attribution by User Action), S-989 (Tool Catalog), S-1223 (Fleet Cockpit), S-1388 (Retry Storm). No single source covers the complete operator's playbook — this entry synthesizes across them.

## See also

- [F-192 · Cost Velocity Circuit Breaker](f192-cost-velocity-circuit-breaker.md) — fleet-wide cost monitoring and circuit breaking
- [F-193 · Agent Escalation Gating](f193-agent-escalation-gating.md) — when and how agents escalate to humans
- [F-181 · Silent Tool Call Failures](f181-silent-tool-call-fails.md) — the most common fleet health failure
- [S-1223 · Fleet Cockpit](s1223-the-fleet-cockpit-stack-when-you-have-12-agents-and-no-idea-what-any-of-them-are-doing.md) — dashboarding a running fleet
- [S-1388 · Retry Storm](s1388-the-retry-storm-stack-when-your-agent-burns-200x-budget-on-a-single-glitch.md) — the cost failure pattern at agent level
