# S-1005 · AI SRE — The Reliability Discipline Your Agent Team Doesn't Have Yet

Your agent passed every test. It passed every benchmark. It passed eval week. Then Monday morning a domain expert notices it has been routing invoices incorrectly for 72 hours — systematically, plausibly, with no error logs, no alerts, and no indication that anything is wrong. This is not a code bug. This is an SLO violation that your monitoring stack cannot see.

The discipline to prevent this has a name: **AI SRE**.

## Forces

- **Agents fail with the surface plausibility of success.** Unlike a crashed service or a 500 error, an agent that degrades produces outputs that look correct. Standard APM (error rates, latency histograms, CPU saturation) was designed for crashes — it cannot detect behavioral regressions where the agent keeps responding and keeps spending tokens.
- **Every agent deployment is a de-facto SLO change.** A prompt update, a model swap, a tool schema modification, a retrieval config change — each is a release. Most teams have no structured promotion gate for any of them. SLOs that nobody defined cannot be violated intentionally.
- **Agent incident classification has no shared taxonomy.** When a traditional service fails, you have a playbook: 500s → roll back, latency spike → scale, memory pressure → restart. When an agent silently starts hallucinating tool calls, no playbook exists. Teams reinvent incident response from scratch every time.
- **The blast radius of an agent failure is not bounded by a single request.** A misbehaving agent can make hundreds of downstream calls, corrupt memory state across sessions, write bad data to external systems, and spend thousands of dollars before anyone notices. Speed of detection is the primary damage-control lever.
- **Agent reliability requires behavioral SLOs, not infrastructure metrics.** p99 latency tells you nothing about whether the agent made the right routing decision. Token-per-task cost tells you nothing about whether the agent used the right tool. You need SLOs that measure the thing you actually care about.

## The move

### Define behavioral SLOs, not just infrastructure SLOs

Traditional SRE measures: availability, latency, error rate, saturation.

AI agent SLOs must add a **behavioral tier**:

```
BEHAVIORAL SLOs (agent-specific)
├── Task completion rate         — % of tasks completed without escalation
├── Tool call accuracy          — % of tool calls that were necessary and correct
├── Hallucination rate          — % of outputs flagged by verifiers as factually wrong
├── Escalation rate             — % of tasks requiring human intervention
├── Cost per task               — tokens spent / task; tracked against a ceiling
└── Drift index                 — rolling behavioral similarity score vs. baseline
```

These are not soft metrics. Each requires a concrete measurement method (eval harness, verifier model, human-in-the-loop annotation sample, token counter). Without a measurement method, the SLO does not exist.

### Set error budgets for behavioral dimensions

Error budgets translate "we care about this" into "we act when it degrades."

```
SLO: Task completion rate ≥ 94%
  Error budget: 6% of tasks may fail per 30-day window
  Consume 80% of budget → alert: SLO at risk
  Consume 100% of budget → freeze deployments, launch incident
  Budget remaining 0% → mandatory post-mortem before any change
```

The same error-budget discipline applies to hallucination rate, tool-call accuracy, and cost-per-task. The budget is not a soft target — it is the decision threshold that governs when the team acts versus when it continues shipping.

### Classify agent incidents by type, not severity

Traditional incident severity (P1/P2/P3) maps poorly to agent failures. Use a taxonomy that captures the actual shape of agent failure:

```
AGENT INCIDENT TYPES
├── Type I — Crash-equivalent      — Agent produces no output, loops, or burns budget to zero
├── Type II — Silent regression   — Agent produces output that looks correct but decides wrong
├── Type III — Cascade             — Agent error propagates through a multi-agent pipeline
├── Type IV — Data integrity       — Agent writes bad state to external systems
└── Type V — Cost anomaly          — Token spend diverges from baseline without outcome improvement
```

Each type has a different response playbook. Type II (silent regression) is the most dangerous because it has the highest dwell time — teams discover it last, after the most damage.

### Instrument the four agent signals

Inspired by the SRE golden signals (latency, traffic, errors, saturation), adapted for agents:

```
AGENT GOLDEN SIGNALS
├── Quality       — Are outputs correct? (verifier scores, task completion)
├── Quantity      — Is the agent producing enough (or too much)? (call rate, token rate)
├── Cost          — Is spend proportional to outcomes? (cost-per-task, cost-per-correct-task)
└── Drift         — Is behavior changing without intent? (behavioral similarity to baseline)
```

These four signals are the minimum viable AI SRE dashboard. If you only have one: measure **quality** via a rolling eval harness on production traces.

### Write runbooks for agent-specific failure patterns

Generic runbooks ("restart the service") do not help. Write explicit runbooks for each incident type:

```
RUNBOOK: Type II — Silent Regression (suspected)
1. Pull last 50 production traces — compare to baseline eval set
2. Check for upstream schema changes in the last 72h (schema change → memory invalidation)
3. Run offline eval on current production traces vs. last-known-good snapshot
4. If eval score dropped >5% → promote to incident, initiate rollback evaluation
5. Check tool-call logs for novel tool sequences (signals model has re-routed)

RUNBOOK: Type V — Cost Anomaly
1. Pull token spend by task type for the last 7 days
2. Identify which task type has the highest cost-per-task spike
3. Check if average tool-call count per task increased (signals a loop or re-try pattern)
4. Check context length trend (signals memory or retrieval degradation)
5. Compare model selection distribution (signals routing drift)
```

### Treat agent on-call as a distinct rotation

Agent on-call requires different skills than infrastructure on-call. The agent on-call engineer needs:
- Ability to read and interpret traces (not just logs)
- Access to the eval harness to run on-demand evaluations
- Authority to freeze deployments (not just restart services)
- Knowledge of the behavioral SLOs and current error budget consumption

A team that rotates agent on-call without training is running on vibes. The on-call engineer who cannot run an eval on a suspected regression is blind.

## Receipt

> Verified 2026-07-12 — Patterns distilled from: McKenna Consultants "AI Agent Observability" (May 2026), OpenTelemetry GenAI Blog (2025), GitHub trending agent debugging patterns, industry practitioner reports on AI SRE maturity. The behavioral SLO + error budget + incident taxonomy framework is synthesized from multiple independent sources converging on the same gap: standard SRE tooling was not designed for probabilistic systems that produce plausible failures.

## See also

- [S-997 · The Agent Observability Stack](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — the observability foundation this builds on
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — behavioral eval as the measurement layer for SLOs
- [S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — Type I crash-equivalent failure handling
- [S-362 · Budget-Aware Agents](s362-budget-aware-agents-cost-self-regulation-as-first-class-behavior.md) — cost as a behavioral SLO dimension
- [S-152 · Live Event Significance Scorer](s152-live-event-significance-scorer.md) — detecting which signals actually matter in real time
