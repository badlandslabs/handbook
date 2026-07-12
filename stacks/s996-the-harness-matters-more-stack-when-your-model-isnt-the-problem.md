# S-996 · The Harness Matters More Stack: When Your Model Isn't the Problem

Your team spent two weeks evaluating models. You chose the best available. You shipped it. Three weeks later the production pass rate is 34% and climbing slowly. You try a different model. The number barely moves. This is not a model problem. This is the harness problem.

In 2025–2026, production reliability is determined more by the execution environment around the model than by the model itself. Frontier models score 80–94% on SWE-bench and GAIA benchmarks in single-pass evaluations — and fewer than 25% of real-world agent tasks complete on the first attempt in production. The gap lives in the harness: the bounded control loops, verification layers, termination policies, and execution guards that determine whether occasional model capability translates into reliable system outcomes.

## Forces

- **The harness is where the real work happens.** Tool responses account for 67.6% of all tokens in agent traces. System prompts account for 3.4%. The signal is in the tool interactions, not the model reasoning — and the harness controls both.
- **Changing the harness outperforms changing the model.** LangChain achieved 52.8% → 66.5% on Terminal Bench 2.0 — ranking jump from Top 30 to Top 5 — by engineering the harness alone. Zero model changes. The harness is the primary lever for reliability.
- **Model choices are reversible. Production failures are not.** A wrong model is a one-line config change. A bad harness costs real money: one documented retry storm burned $47,000 in eleven days. Models are commodities; execution control is the differentiator.
- **Production agents fail fast and invisibly.** 68% of production agents execute fewer than 10 steps before requiring human intervention. 92.5% deliver output to humans rather than to downstream software. We are not building autonomous systems; we are building expensive autocomplete with extra steps that most teams haven't yet engineered around.
- **MAST taxonomy reveals where agents actually fail.** A 1,642-trace analysis across 7 open-source frameworks (NeurIPS 2025) found three failure categories with 14 distinct modes: specification failures (41.77% — wrong task, wrong plan, wrong state tracking), execution failures (wrong tool, wrong parameters, wrong timing), and verification failures (premature output, unchecked reasoning, lucky failures). Framework failure rates range from 41% to 86.7%.

## The move

### 1. Treat the harness as a first-class control layer

The harness is not infrastructure. It is a structured control layer with the same rigor you'd apply to business logic. Every harness decision should answer: *what happens when the model does the unexpected thing?*

```python
class AgentHarness:
    # Execution policy: what the model can and cannot do
    def __init__(self, model, config):
        self.termination = TerminationPolicy(
            max_steps=15,
            max_tokens=8192,
            no_progress_threshold=3,
        )
        self.retry = RetryPolicy(
            max_attempts=2,
            backoff="exponential",
            retryable_errors=["timeout", "rate_limit", "503"],
            # Non-retryable: auth failures, 400s, semantic errors
        )
        self.gate = ActionGate(
            destructive_tools=["delete", "write", "execute"],
            requires_confirmation=True,
        )
        self.verifier = OutputVerifier(
            # Catch "correct" outputs that are wrong
            trajectory_check=True,
            schema_validation=True,
        )

    def run(self, task, context):
        span = tracer.start_span("agent_run", attributes={
            "task_type": task.type,
            "harness_version": self.version,
        })
        with span:
            for step in self.execution_loop(task, context):
                self.termination.check(step)
                self.retry.maybe_retry(step)
                self.gate.authorize(step)
                span.set_attribute("step", step.number)
                span.set_attribute("tokens", step.total_tokens)
                span.set_attribute("cost_estimate", step.cost)
            self.verifier.check_final_output(step)
        return step.output
```

### 2. Implement bounded termination as your first investment

Every unterminated loop is a budget bomb. The ZenML $47,000 incident, the "35-minute run that accomplished nothing," and the "50-turn stuck loop" all share the same root cause: unbounded retry or loop logic. A termination policy with no ceiling is not a safety net — it is a ceiling with no floor.

Establish four termination conditions, all active simultaneously:

- **Step cap** — hard stop at N steps. Start conservative (10–15 for most agents), tune from production data.
- **Token budget** — hard stop at N tokens consumed. Set below the model's context limit with headroom for output.
- **No-progress detection** — stop after N consecutive steps with no meaningful state change (requires a progress metric, even a simple token-delta check).
- **Goal verifier** — stop when the task can be declared complete or failed. This is the hardest one; even a rough verifier (does the output have the required fields? does it pass schema validation?) beats no verifier.

### 3. Use tiered retry — not uniform retry

Uniform retry logic (try up to N times for any error) creates retry storms. Transient errors (timeouts, rate limits, 503s) benefit from retry. Non-transient errors (400s, authentication failures, semantic tool errors) do not — retrying a malformed argument with the same malformed argument produces the same failure with higher cost.

```python
TRANSIENT = {"timeout", "rate_limit", "503", "429", "connection_reset"}
NON_TRANSIENT = {"400", "401", "403", "404", "schema_mismatch"}

def maybe_retry(self, step: AgentStep) -> bool:
    if step.error.code in NON_TRANSIENT:
        return False  # Fail fast, do not retry
    if step.error.code in TRANSIENT:
        return self.retry_policy.attempt < self.retry_policy.max_attempts
    return False  # Unknown errors: fail rather than retry blindly
```

For semantic failures (the tool returned data, but the data is wrong), retries rarely help. Route to a verifier instead.

### 4. Gate destructive actions with execution-level checks

The most dangerous agent failure mode is the one where every individual step looks fine in isolation. An agent hits a tool error, retries with modified parameters that match a destructive wildcard pattern, and deletes production data — while every step's logs show nothing unusual. Tool-call gating catches this before it becomes a catastrophe.

```python
DESTRUCTIVE = {"db_delete", "file_delete", "execute", "bulk_update", "drop_table"}

def authorize(self, step: AgentStep) -> AuthorizationResult:
    if step.tool_name in DESTRUCTIVE:
        if not self.has_guardrails(step):
            return AuthorizationResult(
                allowed=False,
                reason="Destructive tool requires execution guardrails",
            )
        if not self.has_confirmation(step):
            return AuthorizationResult(
                allowed=False,
                reason="Destructive action requires human confirmation",
            )
    return AuthorizationResult(allowed=True)

def has_guardrails(self, step):
    # Verify the action was explicitly planned, not auto-generated
    return any(marker in step.reasoning for marker in [
        "user_requested", "confirmed_action", "explicit_deletion"
    ])
```

### 5. Profile where tokens actually go — instrument per-span

The aggregate token count hides the real cost driver. One request with 50,000 tokens looks the same as fifty requests with 1,000 tokens — until you inspect per-span data and discover step 7 alone consumed 40% of the budget on repeated context re-loading.

```python
# Per-span instrumentation (extends the pattern from W-05)
with tracer.start_as_current_span("agent_step") as span:
    span.set_attribute("step_number", step.number)
    span.set_attribute("input_tokens", step.input_tokens)
    span.set_attribute("output_tokens", step.output_tokens)
    span.set_attribute("tool_name", step.tool_name or "llm_only")
    span.set_attribute("tool_response_bytes", step.tool_response_size)
    span.set_attribute("estimated_cost", step.cost)
    span.set_attribute("duration_ms", step.elapsed_ms)

# Post-run analysis: where did tokens go?
def report_token_sinks(self, trace):
    sinks = defaultdict(int)
    for span in trace.spans:
        sinks[span.tool_name or "reasoning"] += span.output_tokens
    return sorted(sinks.items(), key=lambda x: x[1], reverse=True)
```

The BuildMVPFast analysis found that tool responses dominate agent traces (67.6% of tokens) while system prompts contribute only 3.4%. This means the highest-leverage optimization target is tool use efficiency — not prompt length.

### 6. Connect harness decisions to eval data

Every harness change should be measurable. If you add a no-progress termination detector, run your eval suite and confirm: does the agent still complete the same tasks, but faster and cheaper? If you tighten the action gate, does the destructive-action failure rate drop? The harness is an engineering discipline, not a set-it-and-forget-it configuration.

## Tradeoffs

- **Bounded termination trades off completeness for cost.** A conservative step cap prevents runaway loops but may terminate agents that were about to succeed. Calibrate from production data, not intuition.
- **Retry tiering requires error classification.** You need your tools and API to return structured error codes, not just HTTP status. If your tools return 200 with a generic error body, tiered retry requires first parsing the error.
- **Execution gating adds latency** on every destructive action. For high-frequency agents, consider batch confirmation (confirm all destructive actions in a run up front) rather than per-action gating.
- **Harness tuning is iterative.** The right step cap for a research agent (50 steps) differs from a data pipeline agent (5 steps). Start with conservative bounds and loosen based on production evidence.

## See also

- [S-70: Agent Loop Termination](s70-agent-loop-termination.md) — implementation of four termination conditions
- [S-366: Harness Engineering](s366-harness-engineering-the-discipline-around-the-model.md) — the discipline formalized
- [S-959: Trajectory vs. Outcome Eval](s959-the-trajectory-vs-outcome-eval-stack-when-your-agent-is-right-for-the-wrong-reasons.md) — why outcome metrics miss the reasoning that matters
- [S-976: Verification Layer](s976-the-verification-layer-when-your-agent-cant-distinguish-right-from-almost-right.md) — catching "correct" outputs that aren't
- [S-995: Agent Failure Recovery](s995-the-agent-failure-recovery-stack-when-your-agent-loops-hangs-or-hammers-itself-against-a-dead-end.md) — the failure modes that bypass try/catch
- [W-05: LLMOps Observability](w05-llmops-observability.md) — agentic span instrumentation
