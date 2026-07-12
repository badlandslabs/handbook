# S-822 · The Structured Failure Taxonomy — Semantic vs. Structural Errors and Cascading Recovery

A request to your agent returns HTTP 200 in 200ms. The JSON parses cleanly. The agent output follows the schema. Your monitoring dashboard is green. The customer is unhappy because the agent recommended a medication dosage that was wrong by a factor of three. Your monitoring caught nothing. This is what the structured failure taxonomy is built to solve.

Production agents fail in two fundamentally different ways. Structural failures — API errors, timeouts, rate limits, malformed JSON — follow the patterns your infrastructure team already knows. Semantic failures — responses that parse correctly but deliver the wrong answer — break every assumption in traditional error handling. A single `except: retry` block treats both the same way. It retries the medication recommendation. The second wrong answer arrives faster and more confidently than the first.

The structured failure taxonomy separates these two failure classes, assigns each a recovery strategy, and chains them into a cascading response that degrades intelligently rather than repeatedly failing the same way.

## Forces

- **Agents fail in two fundamentally different ways, but most code treats them as one.** Structural errors (API outages, timeouts, parse failures) are detectable and recoverable with standard retry logic. Semantic errors (wrong output, hallucination, wrong tool choice) return HTTP 200 and valid JSON — your error handling never fires. The agent continues building on a broken foundation.
- **Naive retry compounds cost without fixing semantic failure.** When the model gives a wrong answer, retrying the same model call with the same context produces the same wrong answer at full cost. A 3-retry loop on a semantically wrong response is $3× the cost with no improvement guarantee.
- **Fallback model routing only works if you know when to trigger it.** Switching to a cheaper or more conservative model only helps if you've correctly diagnosed that the failure is semantic rather than structural. Misclassifying a rate limit as a semantic error and switching to a fallback model guarantees the same rate limit on the new model.

## The move

### Step 1: Classify at the boundary, not inside the call

The taxonomy check happens at the response boundary — after the model call returns, before the agent acts on the result.

```
Response → Structural Check → Semantic Check → Recovery Route
```

### Step 2: Structural failure routing

Structural failures are detected by status code and response shape:

```
429 Rate Limit        → exponential backoff + header polling
500/502/503 Server Err → retry up to N times with jitter
Timeout               → classify as transient structural
Malformed JSON        → classify as transient structural
200 but empty         → classify as structural (API-level failure)
```

Structural failures route to standard retry with exponential backoff and circuit breaker integration. The circuit breaker tracks failure rate per model endpoint; when the error rate exceeds the threshold (e.g., 50% in a 10-request window), the circuit opens and routes to fallback endpoint or queues for later.

### Step 3: Semantic failure detection

Semantic failures require output validation — the response is structurally valid but substantively wrong. Detection strategies:

```python
# Keyword/output guard: check for known-bad patterns before passing to agent
BLOCKED_PATTERNS = ["critical", "do not", "WARNING: unverified"]
if any(p in response.lower() for p in BLOCKED_PATTERNS):
    trigger_semantic_failure_handling()

# Constraint validation: structured output outside valid bounds
if schema_version and value_out_of_range(output, schema_version):
    trigger_semantic_failure_handling()

# Semantic similarity: LLM-as-judge check against expected range
def semantic_correctness_check(output, context) -> float:
    judge_prompt = f"""
    Given: {context}
    Response: {output}
    Score 0-1: does the response correctly address the request?
    """
    score = call_judge_model(judge_prompt)
    return score

# Cross-validation: two independent models agree on wrong answer
# Both Claude and Gemini give the same wrong dosage → structural model bias
```

### Step 4: Cascading recovery routing

Once classified, failures route to their correct recovery:

| Failure Class | Recovery Strategy | Cost Impact |
|---------------|-----------------|-------------|
| Transient structural | Retry with backoff | Controlled |
| Persistent structural | Circuit breaker open → fallback endpoint | Controlled |
| Semantic (mild) | Retry with modified context (add constraint nudge) | Moderate |
| Semantic (severe) | Escalation gate → human review | Stop-before-cost |
| Semantic (model bias) | Switch model family, not just tier | Controlled |

### Step 5: The cascading circuit breaker pattern

```python
class CascadingCircuitBreaker:
    def __init__(self):
        self.structural = CircuitBreaker(failure_threshold=5, timeout=60)
        self.semantic = CircuitBreaker(failure_threshold=3, timeout=120)
        self.model_family = {}  # track per-model semantic failure rate

    def record_structural_failure(self, endpoint):
        self.structural.record(endpoint)
        if self.structural.is_open(endpoint):
            self._route_to_fallback()

    def record_semantic_failure(self, model_family, reason):
        self.semantic.record(model_family)
        self.model_family[model_family] = \
            self.model_family.get(model_family, 0) + 1
        if self.model_family[model_family] >= 3:
            self._route_to_alternative_family(model_family)

    def _route_to_fallback(self):
        raise CircuitOpenError("Structural CB open — fallback endpoint")

    def _route_to_alternative_family(self, failed_family):
        raise SemanticBiasError(
            f"Model family {failed_family} has 3+ semantic failures"
        )
```

### Step 6: Sentinel fallback — stop before compounding

For high-stakes domains (medical, financial, legal), the sentinel fallback is a hard stop that prevents cascading wrong answers:

```python
def execute_with_sentinel(agent_response, stakes: str, max_cascades: int = 2):
    cascade_count = 0
    while cascade_count < max_cascades:
        classification = classify_failure(agent_response)
        if classification == "semantic_severe":
            if stakes == "high":
                return EscalationRequired(
                    reason="semantic_severe",
                    agent_output=agent_response,
                    escalate_to="human_review"
                )
            cascade_count += 1
            agent_response = retry_with_guardrails(agent_response)
        elif classification == "structural":
            agent_response = retry_structural(agent_response)
        else:
            return agent_response  # success
    return EscalationRequired(
        reason="max_cascades_exceeded",
        agent_output=agent_response
    )
```

## Receipt

> Verified 2026-07-08 — Taxonomy framework synthesized from Preporato error handling guide (May 2026), Agentbrisk AI agent error recovery (March 2026), AgentMarketCap Agent Reliability Engineering SRE report (April 2026), and AgentMarketCap enterprise SLA analysis. Code patterns follow standard circuit breaker + semantic validation patterns from those sources. Tested structure against S-821 (Production Failure Stack) — this entry extends that chapter's loop/cost coverage with the semantic/structural classification that precedes recovery decisions.

## See also

- [S-821 · The Production Failure Stack — Loop Detection, Circuit Breakers, and Cost Governors](s821-the-production-failure-stack-loop-detection-circuit-breakers-and-cost-governors.md) — the sibling chapter; S-822 adds failure classification before the recovery stack kicks in
- [S-532 · The Six Agent SLOs](s532-the-six-agent-slos.md) — quality SLOs (semantic accuracy <90%) provide the thresholds that trigger semantic failure detection
- [S-340 · Agent Hard Enforcement Plane](s340-agent-hard-enforcement-plane.md) — the sentinel fallback maps directly to enforcement-plane escalation gates
- [F-193 · Agent Escalation Gating](f193-agent-escalation-gating.md) — escalation gating is the output destination when semantic severe exceeds cascade budget
