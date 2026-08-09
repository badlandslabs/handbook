# S-2361 · The Agentic Reliability Stack — When Production Makes Your Agent Loop Forever

Your candidate evaluation agent passed every test in development. In production it hallucinated tool parameters, got stuck in loops, contradicted its own reasoning mid-session, and cost three times the projected budget — all without raising a single exception. HTTP 200, nothing works.

This is the gap between agentic demos and agentic deployments: the failure modes are different in kind, not just degree.

## Forces

- **Agents fail "successfully."** The API returns 200, tool calls execute, and the agent produces confident output — while being completely wrong. Traditional error handling doesn't see it.
- **Single failures cascade.** One bad tool parameter poisons every downstream step. A loop condition triggers on every retry. The "fix" is worse than the original bug.
- **Evaluation is not testing.** You cannot assert correctness the way you assert `sum([2,2]) == 4`. Outcomes are probabilistic, context-dependent, and multi-dimensional.
- **40% of agentic AI projects will be canceled by end of 2027** (Gartner, June 2025), primarily due to escalating costs, unclear value, or inadequate risk controls — not capability gaps.
- **Context bleeds across turns.** Token limits tempt teams to truncate history, but the agent keeps referencing deleted context, creating hallucinations that look like reasoning errors.

## The Move

Build reliability into the agent loop itself, not around it. Five concrete patterns:

### 1. Validate every tool call at the call site — not inside the tool

Agents hallucinate parameters (non-existent IDs, wrong date formats, invalid enum values) even when using the correct tool. Add schema validation *before* the tool executes:

```
# Schema validation at call site (JSON Schema / Pydantic)
if not tool_input_schema.validate(called_params):
    raise ParameterValidationError(f"Agent fabricated: {invalid_fields}")
```

This catches hallucinations that return HTTP 200 and look "successful" to the caller.

### 2. Build a circuit breaker + retry + fallback chain

Wrap every tool call in a three-layer resilience stack:

| Layer | Trigger | Action |
|-------|---------|--------|
| **Retry** | Transient failure (timeout, 5xx) | Retry 1-3x with exponential backoff |
| **Circuit Breaker** | Repeated failures on same tool | Open circuit, skip tool for N minutes |
| **Fallback** | Tool permanently unavailable | Return partial result with explicit gap |

```
try:
    result = call_with_retry(weather_api, max_attempts=3)
except CircuitBreakerOpen:
    return f"Found {len(flights)} flights. Weather data unavailable — check back shortly."
```

### 3. Use golden datasets with CI regression gates

Golden datasets are versioned collections of input → expected outcome pairs that run automatically on every prompt or model change. Construct them from real production failures (not synthetic cases):

- **Offline evals:** Curated golden set run before deployment
- **Regression tests:** CI/CD gates on every PR — block deploy if eval score drops
- **Online monitoring:** Production traces with automated scoring

Golden datasets must be **versioned like code** (git + DVC), maintained by a human-in-the-loop review process, and refreshed quarterly. Stale golden sets produce false confidence.

### 4. Use LLM-as-judge for subjective outputs — but calibrate it

For tasks without a single correct answer (summarization, conversation tone, code quality), use a second LLM as evaluator (G-Eval or custom rubric). Calibrate against human annotations using Spearman correlation before trusting scores.

Be aware of LLM-as-judge biases: **verbosity bias** (longer answers score higher), **position bias** (first option preferred), **self-preference** (GPT-4o favoring its own outputs), and **gameability** (agents prompt-engineering to pass the judge). Validate with human-labeled samples first.

### 5. Add deterministic guardrails before the agent loop

Use hard filters for high-stakes operations — destructive actions, PII exposure, cost thresholds — as deterministic code, not LLM-generated decisions:

```
# Deterministic guardrail — not LLM-decided
if action == "DELETE_DATABASE" and not user.is_admin:
    raise PermissionDenied("Destructive action requires admin role")
```

This prevents the "reprompt until it says yes" failure mode.

## Evidence

- **Production failure post-mortem:** Modelia.ai's candidate evaluation agent hallucinated tool parameters, looped on edge cases, and contradicted its own reasoning mid-session. Root cause: no parameter validation at call site, no circuit breakers, no golden dataset regression. Fixed with schema validation + three-layer resilience stack + offline eval suite before every deploy. — [Harsh Rastogi, Modelia.ai/Asynq.ai, March 2026](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **Eval framework comparison:** DeepEval (open-source) provides pytest-style `assert_test` with 50+ built-in metrics and CI guardrails; RAGAS provides reference-free RAG evaluation (faithfulness, answer relevancy, context precision) without ground truth labels. DeepEval excels at CI regression gates; RAGAS excels at batch RAG scoring without labeled data. — [QASkills.sh comparison, 2026](https://qaskills.sh/blog/ragas-vs-deepeval-2026)

- **LLM evaluation taxonomy:** SAP Labs' KDD 2025 survey frames agent evaluation as two-dimensional: *what* to measure (task completion, safety, cost, efficiency) and *how* to measure it (static dataset, interactive environment, LLM-as-judge, human annotation). Key insight: "LLM evaluation is like examining the performance of an engine. Agent evaluation assesses a car's performance comprehensively, as well as under various driving conditions." — [arXiv:2507.21504v1, KDD 2025](https://arxiv.org/html/2507.21504v1)

- **Market context:** Gartner predicts 40% of enterprise applications will include AI agents by end of 2026 (up from <5% in 2025), but only 2% of organizations have deployed agents at full production scale. Over 40% of agentic AI projects will be canceled by end of 2027 due to inadequate risk controls and unclear ROI. — [Gartner, June 2025, cited in thinking.inc analysis](https://thinking.inc/en/pillar-pages/agentic-ai-architecture/)

- **Real production incidents:** Claude Code wiped a DataTalks database; a Replit agent deleted data during a code freeze period. Both were caught by the same failure pattern: agents executing destructive actions with permissions the deployment never authorised. HN discussion on monitoring agents surfaced consensus that traditional APM tools are insufficient — agent-specific tracing (LangSmith, Langfuse, Arize Phoenix) is required. — [HN Ask thread, 2025](https://news.ycombinator.com/item?id=47301395)

## Gotchas

- **A golden dataset that isn't versioned or maintained is worse than none.** It gives false confidence. Treat it like a security-sensitive codebase.
- **LLM-as-judge is a first approximation, not ground truth.** Calibrate against human-labeled samples. Spearman correlation < 0.7 means your judge is unreliable.
- **Loop detection requires a step counter, not just a retry count.** An agent can loop with different outputs each time; retry logic alone won't catch it. Track the action sequence, not just the error count.
- **Cost monitoring is reliability.** Agents can enter a high-frequency tool-calling loop that generates thousands of dollars in API calls in minutes. Set hard cost-per-session limits as a circuit breaker.
- **Context truncation is not memory.** Cutting the history to fit the token window doesn't give the agent useful memory — it creates a ghost context where the agent references deleted information. Use a proper memory layer (vector store + consolidation) instead.
