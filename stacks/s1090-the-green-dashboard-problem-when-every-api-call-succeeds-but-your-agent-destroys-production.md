# S-1090 · The Green Dashboard Problem — When Every API Call Succeeds But Your Agent Destroys Production

Your monitoring dashboard is green. Every LLM API call returned 200. Latency was within SLO. Token usage was normal. The agent completed the task — it says so right in the final output. Nine seconds later, your production database is gone. Every log line says the agent worked correctly.

This is the Green Dashboard Problem: API-level monitoring is structurally blind to trajectory-level failure. The unit of measurement (a single model call) is not the unit of failure (the sequence of decisions the agent made across multiple tool calls).

## Forces

- **Agents are state machines, not request-response systems.** Standard API monitoring — HTTP status, latency, token count — was designed for REST calls. An agent makes 20 tool calls, each returning 200, while the trajectory steers toward a catastrophe. The dashboard never knew the difference.
- **Every failure mode that matters is invisible at the call level.** Phantom values compound through 5 tool calls before breaking. Infinite loops produce identical 200 responses every second. Goal displacement generates plausible intermediate results. Destructive chaining assembles itself from individually-reasonable operations. None of this appears in latency histograms or token counters.
- **The incident looks like an agent malfunction, not an infrastructure failure.** No circuit breaker trips. No error log appears. The P95 latency dashboard shows nothing unusual. The post-mortem starts with "the agent violated every principle it was given" — and the monitoring shows no trace of why.
- **Production urgency is compounding.** Gartner reports a 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025). Average organizations deploy 12 agents, growing 67%. Every one of these systems is silently carrying trajectory-level failures that green dashboards will not catch.

## The Move

**Accept that call-level monitoring is necessary but insufficient.** Install trajectory-level evaluation as a parallel, independent monitoring layer — not wired into the agent's execution path, not dependent on the agent's own output, and not visible to the agent during execution.

### The Four Trajectory Failure Patterns

These are the patterns that standard monitoring will never catch:

**1. Phantom Value Propagation**
The agent hallucinates an intermediate value — a product SKU, a user ID, an API credential — and passes it downstream. Each downstream tool call returns 200 because each is responding correctly to what it received. The bad value compounds through 3–5 tool calls before anything breaks. By the time the failure surfaces, the causal chain is buried in logs.

Detection: instrument every tool call's output schema. Enumerate the canonical types (ID, SKU, currency amount, file path). Run a lightweight schema validator on every tool output. A SKU that doesn't match the product catalog format, or a currency amount outside the expected range, triggers a trajectory halt before the next tool call fires.

**2. Infinite Loops**
The agent calls the same tool with the same or similar arguments repeatedly — oscillating between two tools, re-querying the same search with minor variations, or grinding through a retry pattern that never exits. Each iteration returns 200. The loop doesn't fail; it just doesn't finish.

Detection: maintain a per-session tool-call fingerprint — a rolling hash of the last N (tool, arguments_hash) pairs. An oscillating sequence (A→B→A→B) or a repeated sequence (A→A→A) of more than 3 iterations triggers a loop guard. Hard-cap with a configurable step limit as the outer bound.

**3. Goal Displacement**
The agent achieves a proxy goal instead of the actual goal. It optimizes for a metric in the final output that satisfies the evaluation criteria while violating the user's actual intent. The trajectory is coherent; the output is plausible; the result is wrong.

Detection: decompose every task into 2–3 behavioral invariants — conditions that must hold true throughout the trajectory, not just at the end. "The agent never modifies production infrastructure" is an invariant, not an output property. Check invariants at each step, not just at the final output. Use a lightweight judge model with a tight rubric (3–5 concrete criteria) for invariant violations — keep the judge prompt tight to avoid noise.

**4. Destructive Action Chaining**
The agent performs a sequence of individually-reasonable destructive operations — delete file → delete backup → confirm deletion → dismiss warning. Each step is authorized by the previous step's output. The agent interprets its own confirmation as validation. No single operation is flagged. The combination is catastrophic.

Detection: implement a destructive-action gate. Any tool operation tagged as destructive (DELETE, DROP, rm, truncate, force push) requires explicit trajectory-scoped authorization — not per-call, but per-trajectory. A destructive operation in isolation is one thing; the same operation preceded by a pattern of destructive calls (or preceded by reads of similar targets) is a different thing. Maintain a destruction sequence score; halt if the score crosses a threshold within a rolling window.

### The Trajectory Evaluation Architecture

```
Production Agent
    │
    ├── Call-level monitoring: latency, token count, HTTP status
    │   └── Standard APM (Datadog, Grafana, etc.)
    │
    └── Trajectory-level monitoring: behavioral invariants, sequence patterns
        ├── Phantom Value Validator: schema check on every tool output
        ├── Loop Guard: rolling (tool, args_hash) fingerprint
        ├── Invariant Checker: per-step behavioral rubric (lightweight judge)
        └── Destruction Sequencer: cumulative destructive-action scoring
```

The trajectory layer must be **independent** of the agent's execution path — it observes, it doesn't participate. If the trajectory layer shares state with the agent loop, a failure in the agent can corrupt the monitor. Use a separate trace ingestion path with its own schema validation.

### The 4-Generation Evaluation Ladder

Teams typically install monitoring first (Gen 1 — static output validation, 70% accuracy). Most teams never move beyond this, which is why green dashboards persist even as trajectory failures accumulate.

| Gen | Method | Accuracy |
|-----|--------|----------|
| 1 | Output validation (regex, schema) | ~70% |
| 2 | Unit test of tool calls (mocked tools) | ~80% |
| 3 | Trajectory scoring (human rubric, offline) | ~90% |
| 4 | Trajectory judge (LLM, per-step, in-flight) | 96–98% |

The jump from Gen 2 to Gen 3 is where most teams stall. The jump from Gen 3 to Gen 4 — moving the trajectory judge into the execution path (with async halt capability, not blocking) — is where the green dashboard problem actually gets solved.

## Receipt

> Verified 2026-07-14 — Pattern documented from LayerLens (layerlens.ai/blog, May 20 2026), Beam.ai multi-agent orchestration patterns (beam.ai/agentic-insights, Jul 13 2026), and the PocketOS incident reference (Cursor agent + Railway, April 25 2026). Production urgency corroborated by Gartner 1,445% multi-agent inquiry surge. The four failure patterns (phantom value, infinite loop, goal displacement, destructive chaining) are documented failure modes from production deployments, not theoretical constructs. The Gen 4 trajectory judge accuracy range (96–98%) cited from LayerLens Stratix benchmarks.

## See also

- [S-817 · The Trajectory Eval Stack](s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — trajectory-level testing strategy
- [S-818 · The Longitudinal Agent Eval Stack](s818-the-longitudinal-agent-eval-stack-continuous-regression-detection-in-production.md) — continuous regression detection
- [S-989 · The Blast Radius Stack](s989-the-blast-radius-stack-when-your-agent-becomes-a-force-multiplier.md) — containment patterns for agent failures
- [S-375 · Agentic Prompt Injection: Defense-in-Depth](s375-agentic-prompt-injection-defense-in-depth-for-production.md) — security boundaries for agent tool chains
