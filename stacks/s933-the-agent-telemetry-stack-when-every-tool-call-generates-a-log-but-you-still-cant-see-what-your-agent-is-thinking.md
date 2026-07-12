# S-933 · The Agent Telemetry Stack — When Every Tool Call Generates a Log But You Still Can't See What Your Agent Is Thinking

Your agent has 47 log lines this session. HTTP 200. Zero errors. It called your Slack tool, your database tool, and your email tool. It took 3.2 seconds and cost $0.18. Your APM dashboard shows green. Three days later your customer success team reports the agent sent a billing confirmation to the wrong customer. The logs say it succeeded. The outcome was wrong.

This is the agent observability gap: traditional telemetry captures the plumbing, not the reasoning. Agents generate logs at every layer, but none of those logs tell you what the model was actually trying to do, whether its plan made sense, or whether the output matched the intent.

## Forces

- **Agents are state machines with invisible transitions.** A traditional service: request → function → response → log. An agent: request → reasoning → tool call → model reads result → reasoning → tool call → ... → response. Each reasoning step is a model call that standard APM never sees.
- **Tool call success ≠ outcome correctness.** Your Slack API returned 200. The agent sent the message to the wrong channel. Your observability stack reports zero errors. The customer reports a data breach.
- **Token burn is invisible without per-session accounting.** An agent in a long session can accumulate $8 in LLM costs from 12 rounds of re-planning. Standard billing shows you total spend, not spend-by-session or spend-by-task-type.
- **The LLM layer is unobservable by default.** Model providers give you latency and token counts per call. They do not give you: which tool the model chose and why, whether it re-planned mid-session, how many loop iterations it ran, or what context it had at decision points.
- **Standard APM vendors have no agent semantics.** Datadog, Grafana, and CloudWatch model services as stateless request/response. Agents are stateful, multi-turn, and tool-mediated. Their data models don't fit.

## The move

Build a three-layer telemetry stack that captures the reasoning layer — the part that lives between tool calls.

### Layer 1 — Structural spans (what happened, in order)

Instrument every tool call and model call as a span in a distributed trace. The critical addition beyond standard APM: capture the *model's reasoning output* at each step. Tools: OpenLLMetry (auto-instruments OpenAI, Anthropic, Azure, Google models; exports to any OTLP backend), LangSmith (agent-native traces with tool call playback), or Traceloop (OpenTelemetry for LLM apps).

```python
from traceloop.sdk import Traceloop
from traceloop.sdk.decorators import workflow, task

Traceloop.init(app_name="order-agent")

@workflow(name="customer_onboarding")
async def customer_onboarding(customer_id: str):
    # Root span: session-level
    session_span = Traceloop.get_current_span()
    session_span.set_attribute("customer_id", customer_id)
    session_span.set_attribute("agent.version", "2.4.1")

    customer = await fetch_customer(customer_id)  # span: tool
    plan = await synthesize_plan(customer)         # span: model-reasoning

    # Capture reasoning output — not just that model was called
    reasoning_span = Traceloop.get_current_span()
    reasoning_span.set_attribute("llm.reasoning.output", plan.summary)
    reasoning_span.set_attribute("llm.reasoning.steps", len(plan.steps))
    reasoning_span.set_attribute("llm.reasoning.confidence", plan.confidence)

    for step in plan.steps:
        await execute_step(step)                   # spans: sub-agent calls

    session_span.set_attribute("session.token_total", await count_session_tokens())
    session_span.set_attribute("session.cost_estimate", await estimate_session_cost())
```

### Layer 2 — Semantic spans (what it meant)

Structural spans show what happened. Semantic spans encode what it *should* have done. This is the layer that catches "tool succeeded, outcome wrong" failures. Define a schema of semantic invariants per workflow and emit them as span attributes.

```python
# Semantic invariants for an order confirmation workflow
ORDER_INVARIANTS = {
    "confirmation.sent_to": lambda ctx: ctx["email"] in ctx["allowed_recipients"],
    "confirmation.amount_matches": lambda ctx: ctx["amount"] == ctx["order.total"],
    "confirmation.channel": lambda ctx: ctx["channel"] == "support" or ctx["channel"] == "email",
}

async def confirm_order(ctx: dict):
    result = await send_confirmation(ctx["order"])
    # Semantic check: did the right thing happen?
    for invariant, check in ORDER_INVARIANTS.items():
        passed = check(ctx)
        span = Traceloop.get_current_span()
        span.set_attribute(f"semantic.{invariant}", passed)
        if not passed:
            span.set_attribute("semantic.violation", invariant)
            alert("semantic-invariant-violated", invariant, ctx)
    return result
```

### Layer 3 — Budget and loop telemetry (when it's going wrong)

The two highest-value signals that standard APM never captures:

**Token burn tracking.** Aggregate tokens-per-session and cost-per-session in real time. Set a session budget and emit a span event when the agent burns 50%, 80%, 100% of its token budget. This catches re-planning loops that silently accumulate cost.

```python
async def track_session_budget(session_id: str, max_tokens: int = 8000):
    used = await count_session_tokens(session_id)
    pct = used / max_tokens
    span = Traceloop.get_current_span()
    span.set_attribute("budget.used_tokens", used)
    span.set_attribute("budget.max_tokens", max_tokens)
    span.set_attribute("budget.pct", round(pct, 3))

    if pct >= 1.0:
        span.set_attribute("budget.exceeded", True)
        emit_alert("session-budget-exceeded", session_id, used)
        # Trigger graceful degradation or handoff
        await escalate_to_human(session_id, reason="token_budget_exceeded")
    elif pct >= 0.8:
        span.set_attribute("budget.warning", True)
```

**Loop detection.** Track action fingerprints — hash of (tool_name, target_resource, operation) — per session. If the same action repeats 3× within a window, flag it as a potential loop. The signal: not just "same tool called N times" (normal for retries) but "same tool on same resource with same operation N times without progress."

```python
from collections import Counter
from hashlib import sha256

action_log: Counter[str] = Counter()
LOOP_THRESHOLD = 3
LOOP_WINDOW_SECONDS = 30

def action_fingerprint(tool: str, resource: str, params: dict) -> str:
    # Stable fingerprint of this specific action
    key = f"{tool}:{resource}:{sorted(params.items())}"
    return sha256(key.encode()).hexdigest()[:16]

async def check_loop(tool: str, resource: str, params: dict):
    fp = action_fingerprint(tool, resource, params)
    action_log[fp] += 1
    span = Traceloop.get_current_span()
    span.set_attribute("loop.count", action_log[fp])
    span.set_attribute("loop.action_fp", fp)
    if action_log[fp] >= LOOP_THRESHOLD:
        span.set_attribute("loop.detected", True)
        emit_alert("agent-loop-detected", tool=tool, resource=resource, count=action_log[fp])
```

## Receipt

> Verified 2026-07-11 — Pattern validated against: OpenLLMetry auto-instrumentation docs (Traceloop, 2026), LangSmith agent tracing guide (LangChain, 2026), Maxim AI observability stack analysis (2026), Digital Applied sandboxing guide (May 2026), and production agent deployment data from Ahmed Atoui (June 2026) showing 71% adoption but 11% production — the gap is observability. The three-layer telemetry model (structural/semantic/budget) is a synthesis of documented production patterns, not a novel invention.

## See also

- [S-929 · The Agent Eval Stack](s929-the-agent-eval-stack-when-your-benchmark-passes-but-production-fails.md) — eval vs. observability: testing before launch vs. watching during it
- [S-817 · The Trajectory Eval Stack](s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — trajectory traces as eval input; telemetry as the source
- [S-914 · The Observability Trap Stack](s814-the-observability-trap-stack-when-your-dashboard-watches-your-agent-burn-47k.md) — the cost dimension of invisible agent behavior
- [S-931 · The Orchestration Decision Stack](s931-the-orchestration-decision-stack-when-your-team-needs-an-agent-framework-but-doesnt-know-which-one.md) — framework choice affects what your telemetry can see
