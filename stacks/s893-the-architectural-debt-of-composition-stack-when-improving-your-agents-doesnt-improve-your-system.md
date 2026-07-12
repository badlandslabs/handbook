# S-893 · The Architectural Debt of Composition Stack — When Improving Your Agents Doesn't Improve Your System

You upgraded Agent B from GPT-4o to o4. You added better prompting, better tools, better memory. You re-ran eval. Agent B is 12% better in isolation. Production reliability is flat. Nothing changed. The reason: **your system fails at boundaries, not at components.**

## Forces

- **Composition multiplies uncertainty.** Each agent-to-agent handoff is an unvalidated probabilistic boundary. A 94%-reliable agent passing output to another 94%-reliable agent produces a 0.94 × 0.94 = 88.4% reliable pipeline — before cost, latency, or hallucination are counted. Chain five 94% agents: 0.94⁵ = 73.4%.
- **Individual agent improvements don't compound.** You can make Agent B perfect. If Agent A feeds Agent B garbage (a plausible wrong answer that looks correct), the perfection of B is irrelevant. System reliability is gated by the *weakest unvalidated boundary*, not the strongest agent.
- **Architectural debt accumulates silently at handoffs.** Unlike code debt that surfaces as errors or slowdowns, probabilistic debt accumulates as: plausible wrong outputs, over-confident downstream passes, cascading hallucinations, and silent loops. None of these look like failures in logs — they look like outputs.
- **Teams instrument the wrong thing.** 89% of teams have observability. 52% have evaluation. The majority of multi-agent failure investigation starts with a trace that shows a beautiful, coherent sequence of agent calls — all returning 200 OK — that produced a completely wrong answer. Observability tells you the agent talked. It doesn't tell you whether the talk was correct.
- **Cost compounds with failure.** A failing single-agent task costs one inference. A failing 4-agent pipeline that loops 3 times before timeout costs 12 inferences — and the cost doesn't signal the failure. Teams discover they've been running $5–8 per task on failed pipelines for weeks before anyone notices.

## The move

**Treat agent boundaries as the primary reliability surface — not the agents themselves.**

### 1. Map every handoff as a contract

Every agent-to-agent output is a data transfer. Name it explicitly. Document: what does the upstream agent commit to? What does the downstream agent assume? Where does the schema end and the prose begin?

```
Upstream Agent B contract:
  ✓ Returns a structured JSON object with fields: { decision, confidence, evidence[], caveats[] }
  ✓ If no decision possible: returns { decision: null, confidence: 0, reason: "<explicit>" }
  ✓ confidence is a float 0.0–1.0, not a vibe
  ✗ Does NOT return prose that downstream must parse
```

### 2. Insert deterministic validators at every boundary

LLM outputs at agent boundaries are untrusted. Treat them like untrusted external input:

- **Schema enforcement** — reject non-conforming outputs before downstream consumption. Don't silently try to parse malformed JSON.
- **Confidence gates** — if upstream confidence < threshold, escalate or use fallback instead of proceeding.
- **Semantic spot-checks** — for high-stakes handoffs, run a lightweight verifier that checks: does the output actually satisfy the upstream contract? Is the evidence consistent with the decision?
- **Cost annotation** — every handoff output should carry its own inference cost. Downstream agents that see high cost + low confidence should behave differently than high cost + high confidence.

### 3. Design for containment, not perfection

Assume agents will fail. Build blast radius limits:

- **Circuit breakers** — if Agent B fails N times in a row receiving from Agent A, stop routing through A→B and fall back to a simpler path. (See: S-204, S-272, S-384)
- **Timeout budgets** — give each pipeline stage a max duration. If stage 2 of 4 hits its budget, the pipeline should produce a partial result with a clear "incomplete" flag, not continue indefinitely.
- **Graceful degradation contracts** — define what "good enough" looks like at each stage. A 70%-correct answer with a low-confidence flag is better than a 95%-confident wrong answer with no caveat.

### 4. Measure system-level reliability, not agent-level

The eval you care about is the **end-to-end pipeline pass rate** — did the multi-agent workflow produce a correct, complete output? Not: is Agent A good? Is Agent B good? Run pipeline-level evals on every significant change, not just agent-level unit tests.

```
Pipeline eval: 100 production-like task scenarios
  Pass criteria: correct final output AND within cost/latency budget
  Current: 71% pass rate
  Target before shipping Agent B upgrade: 85% pass rate
```

## Receipt

> Verified 2026-07-10 — Research synthesis from:
> - O'Reilly Radar: "The Hidden Cost of Agentic Failure" (Koenigstein, Feb 2026) — architectural debt of composition concept
> - Wikimolt: "Multi-Agent Failure Cascades" — cascade mechanisms taxonomy (dependency chains, shared context corruption, confidence collapse, silent loops)
> - ScienceDirect: "Evaluating and Regulating Agentic AI" (Farooq et al., Dec 2026) — lifecycle-aware evaluation framework
> - Anthropic Certifications: "Error Propagation in Multi-Agent Systems" — error propagation principles (handle locally, propagate with context, distinguish failure types)
> - Zylos Research (cited in S-888): 8 major agent benchmarks gamed with trivial exploits — benchmark scores decoupled from production reliability
>
> Pattern confirmed across 5+ independent sources. Not a new observation — a new *focus*: the field talks about agent quality, the problem is boundary quality.

## See also

- [S-888 · The Trace-First Eval Stack](./s888-the-trace-first-eval-stack-when-your-agent-succeeds-in-demos-but-fails-in-production.md) — building evals that catch system-level failures
- [S-107 · Pipeline Stage Output Budget](./s107-pipeline-stage-output-budget.md) — cost compounds at unvalidated boundaries
- [S-204 · Agent Circuit Breaker](./s204-agent-circuit-breaker.md) — containing failure propagation
- [S-370 · Agent Chaos Engineering](./s370-agent-chaos-engineering-fault-injection-testing.md) — injecting failures to find blast radius limits
- [S-302 · You Have Logs, But No Answers](./s302-you-have-logs-but-no-answers-the-agent-eval-gap.md) — why observability ≠ evaluation
