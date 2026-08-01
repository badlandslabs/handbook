# S-1941 · The Agentic SLA Stack

*When your agent is in production and you have no way to measure it — and neither does anyone else.*

Your AI agent handles 500 customer support tickets a day. It's been running for three weeks. Then someone asks: "What's the SLA?" You don't have one. Nobody defined it. The agent can be online, return HTTP 200, and still fail every customer by choosing the wrong tool, hallucinating a refund policy, or taking 90 seconds to do what should feel instant. Your monitoring dashboard is green. Your users are not.

This is the state of most agent deployments in 2026: production-critical, budget-eating, and unmeasurable. The agentic SLA problem is not a paperwork exercise. It is a reliability architecture problem.

## Forces

- **Agents fail with the surface plausibility of success.** Unlike a crashed API or a 500 error, an agent that degrades produces outputs that look correct. Standard APM — error rates, latency histograms, CPU — was designed for crashes. It cannot detect behavioral regressions where the agent keeps responding and keeps spending tokens.
- **Traditional SLA dimensions are necessary but insufficient.** Uptime and p99 latency tell you whether the service is reachable and fast. They tell you nothing about whether the agent completed the task, called the right tools, avoided hallucination, or knew when to escalate.
- **Outcome probability replaces binary success.** You cannot promise a deterministic outcome from a probabilistic system. You can promise statistical bounds — and 2026 teams are learning to make those legally defensible.
- **The SLA cannot precede the SLO.** Writing a customer-facing SLA before internal SLOs are defined and measured is theater. If you cannot measure "agent accuracy" consistently today, you cannot promise it contractually tomorrow.

## The move

The Agentic SLA Stack builds reliability guarantees in five layered dimensions — from internal instrumentation to customer-facing contractual commitments.

### 1. Define the five SLI dimensions (before anything else)

An agent's Service Level Indicator must cover the behavioral surface, not just the infrastructure:

| SLI Dimension | What It Measures | How to Measure |
|---|---|---|
| **Availability** | Is the agent reachable? | HTTP health checks on the agent endpoint |
| **Latency** | Does it respond within budget? | TTFT (Time to First Token) and end-to-end task duration, p50/p95/p99 |
| **Task completion rate** | Did it finish the task without escalation? | % of sessions completing autonomously, rolling window |
| **Tool-call accuracy** | Did it call the right tools with the right arguments? | Eval harness on a golden set; structured tool-call validation |
| **Output quality score** | Is the output actually correct? | LLM-as-judge or verifier model on a graded sample |

Each SLI needs a concrete measurement method. If you cannot operationalize it with a query or a script, it is not an SLI — it is a hope.

### 2. Set SLOs with error budgets per dimension

Convert each SLI into a target with a budget:

```
Task Completion SLO:   ≥ 92% autonomous completion / 1-hour window
Tool Accuracy SLO:      ≥ 87% correct tool calls / 24-hour window
Quality Score SLO:      ≥ 4.1 / 5.0 average / rolling 7-day window
p95 Task Latency SLO:   ≤ 45s / session / 1-hour window
Escalation Rate SLO:    ≤ 8% sessions requiring human handoff
```

Error budgets translate "we care about this" into "we act when it degrades." When the task completion error budget burns through 50% in a single day, that is a P1. When it burns 5% over a week, you schedule remediation.

### 3. Expose outcome probability bounds (not binary guarantees)

For customer-facing SLA language, express results as statistical bounds rather than deterministic promises:

> "The agent will complete the intent classification with ≥ 85% accuracy. When confidence falls below 0.80, the session is routed to a human agent within 30 seconds."

Outcome probability bounds are more defensible — and more honest — than "99.9% uptime" for a probabilistic system. The 2026 standard is a **Fail-Fast contract**: when internal confidence drops below a threshold, the agent does not guess — it escalates and the SLA clock resets cleanly.

### 4. Instrument trace-grounded scoring

Attaching a structured execution trace to every session closes the audit loop:

```
session_id: sess_7f3a2b
  → intent: classify_ticket
  → tool_calls: [classify_intent, fetch_kb, draft_response]
  → quality_score: 0.84  (pass ≥ 0.80)
  → escalation_trigger: null
  → tokens_spent: 3821
  → duration_ms: 12400
```

With trace-grounded scoring, you can reconstruct every session, explain every decision, and prove — not assert — that the SLA was met or violated. This is what regulators and enterprise customers increasingly demand.

### 5. Write the SLA last, and keep it narrow

The customer-facing SLA should only promise what you can measure and defend. Common mistakes:

- **Promising accuracy without defining it** — specify the evaluation method, the test set, and the threshold
- **Including downstream failures** — if the agent depends on a third-party API that fails, carve out those failures explicitly
- **Writing a single-dimension SLA** — "99.9% uptime" covers availability, not correctness; a task-completion SLA and a quality SLA need to coexist

## Receipt

> Verified — 2026-07-31. Sources: BuildMVPFast "AI Agent SLAs: Uptime, Accuracy, and Response Time Guarantees" (Apr 24, 2026); futureagi.com "AI Agent Reliability Metrics: Six SLOs, Not One Score" (updated May 20, 2026); bittalks.org "The Agentic-SLA: How 2026 Teams Guarantee Performance" (2026); pagebolt.dev "Measuring and Maintaining SLA Reliability for AI Agent Workflows" (Mar 2026). All sources independently describe 5-6 SLO dimensions for agentic systems, consistent naming convention (SLO/SLI/SLA), and the outcome-probability-bounds framing. SLA template patterns verified against agentmodeai.com enterprise vendor comparison (2026).

## See also

- [S-1005 · AI SRE — The Reliability Discipline Your Agent Team Doesn't Have Yet](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — SLO architecture for agent deployments
- [S-1031 · The Flip Rate Problem](s1031-the-flip-rate-problem-when-your-llm-judge-sometimes-votes-a-and-sometimes-votes-b-on-identical-inputs.md) — why single-trial LLM evaluation is unreliable
- [S-1103 · The Agent Eval Stack — When Pass/Fail Tests Are a Lie](s1103-the-agent-eval-stack-when-passfail-tests-are-a-lie.md) — why behavioral evaluation must replace binary testing
