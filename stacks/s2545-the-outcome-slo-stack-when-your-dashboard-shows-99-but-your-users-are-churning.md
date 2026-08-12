# S-2545 · The Outcome SLO Stack

{You shipped an agent. The dashboard shows 99.4% uptime. A customer calls to cancel because the feature has been broken for three weeks. The agent was returning HTTP 200s the entire time — confident, fluent, wrong. Nobody noticed because nobody was measuring what the agent was actually supposed to do.}

## Forces

- **HTTP success and task success are independent events.** An agent can return a 200 with plausible but incorrect output, call the wrong tool and still complete, or silently degrade across model versions — all while your infrastructure metrics report green.
- **Traditional APM tools measure the wrong system.** Latency, error rate, and uptime are infrastructure signals. Agents fail at the task layer, not the HTTP layer. A 99.9% provider SLA composed across 12 LLM calls in a single agent turn can yield an effective task availability of 88.8% — before any user-facing failure is counted.
- **The silent regression is the worst kind.** A model swap, a prompt drift, a retrieval quality drop — these cause task failures without any HTTP error. The system logs say success. The users say churn.
- **You cannot improve what you don't measure.** Teams that measure only infrastructure metrics discover task failures through customer complaints, not dashboards.

## The Move

### The Three-Layer Agent SLO

Agent reliability requires three separate SLOs that fail independently. Conflating them is the root cause of the dashboard-lies-about-quality problem.

| Layer | Measures | Traditional APM | Agent reality |
|-------|----------|-----------------|---------------|
| **Service SLO** | HTTP 200s, API availability, throughput | ✅ Already tracked | Provider meets 99.9% independently |
| **Capability SLO** | Per-step quality: tool call accuracy, retrieval precision, step success rate | ❌ Invisible | Fails silently — wrong tool, right status code |
| **Outcome SLO** | Did the user get what they came for? | ❌ Not measured | The only number that predicts retention |

**The composition math.** If a provider publishes a 99.9% availability SLA on per-call availability, and an agent makes 12 LLM calls to complete one user task, and the task fails when any call fails, effective task availability is approximately 0.999¹² = **98.8%**. Add a retry on failure (2 attempts per call) and the per-call failure rate doubles. This arithmetic is not a bug — it's a structural property of multi-step agentic systems. Most teams never compute it.

### Implementing the Outcome SLO

**1. Define task-level ground truth.** Before instrumenting anything, define what "success" means for each agent task. This is a product decision, not an engineering decision. A research agent's success is different from a data-entry agent's success. Ground truth can be:
- **Outcome verification**: did the downstream system accept the result? (e.g., CRM updated, email delivered, file written)
- **LLM-as-judge**: does a judge model rate the output as meeting the user's intent?
- **Structured rubric**: a defined rubric score above a threshold (e.g., "all required fields present AND no hallucinations detected")
- **Human sampling**: 5–10% of sessions reviewed by a human, extrapolated

**2. Instrument at the task boundary, not the call boundary.** Log a task ID that spans the full user request from receipt to delivery. Attach success/failure labels at that level.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
import uuid

tracer = trace.get_tracer(__name__)

def run_agent_task(user_request: str, context: dict) -> dict:
    task_id = str(uuid.uuid4())
    span = tracer.start_span(f"agent_task:{task_id}")
    span.set_attribute("task.id", task_id)
    span.set_attribute("task.user_intent", user_request[:200])

    try:
        result = agent.execute(user_request, context=context)
        # ── Outcome SLO gate ──
        outcome = verify_outcome(result, user_request)
        span.set_attribute("outcome.success", outcome.success)
        span.set_attribute("outcome.score", outcome.score)
        span.set_attribute("outcome.failure_reason", outcome.reason or "")
        if not outcome.success:
            span.set_status(trace.Status(trace.StatusCode.ERROR, outcome.reason))
        return result
    except Exception as e:
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        raise
    finally:
        span.end()

def verify_outcome(result: dict, intent: str) -> OutcomeResult:
    """Multi-source outcome verification — use all available signals."""
    # Signal 1: downstream system acceptance
    if result.get("downstream_accepted"):
        return OutcomeResult(success=True, score=1.0, reason=None)

    # Signal 2: LLM-as-judge evaluation
    judge_prompt = f"""Rate whether this agent output achieves the user's intent.

User intent: {intent}
Agent output: {result.get("content", "")[:500]}

Rate: PASS only if the output directly addresses the intent with accurate information.
Rate: FAIL if the output is off-topic, hallucinated, or incomplete.
"""
    judge_response = judge_model.generate(judge_prompt)
    score = 1.0 if "PASS" in judge_response else 0.0

    reason = None if score == 1.0 else f"judge: {judge_response[:100]}"
    return OutcomeResult(success=score == 1.0, score=score, reason=reason)
```

**3. Track SLOs as error budgets.** Define a quarterly error budget (e.g., 99% outcome success rate = 1% allowed failures per quarter). When the budget burns faster than expected, you have a reliability incident — even if HTTP metrics are fine.

**4. Detect silent regressions with canary measurement.** Every time you swap a model, change a prompt, or update a retrieval pipeline, measure the capability SLO (step-level quality) before and after. A drop in tool-call accuracy or retrieval precision predicts an outcome SLO drop before users feel it.

### The Provider SLA Trap

Do not confuse the provider's 99.9% API availability SLA with your product's task availability. They are measured at different boundaries:

- **Provider SLA**: per-synchronous-request, one LLM call, one billing event
- **Your task reality**: one user task = 5–20 LLM calls, retries, hedges, partial aggregations

The provider's SLA is real but irrelevant to whether your users get their work done. Compute your own task-level availability from your own telemetry. Treat it as the primary reliability number.

> Verified 2026-08-12 — Tian Pan (tianpan.co) documented the composition arithmetic: 99.9%¹² = 98.8% task availability before user-facing failures. AlexCloudStar (May 2026) reported a production case where a model swap caused a silent regression — 200s returned, zero users served, discovered only through a customer cancellation call.

## See also
- [S-2542 · The Agent Observability Stack](stacks/s2542-the-agent-observability-stack-when-your-agent-returns-200-and-nobody-knows-what-it-did.md) — traces without answers
- [S-2530 · The Evaluation Stack](stacks/s2530-the-evaluation-stack-when-your-agent-ships-but-nobody-knows-if-it-works.md) — ship but don't know
- [S-2544 · The Agent Evaluation Stack](stacks/s2544-the-agent-evaluation-stack-when-your-agent-passed-the-benchmark-but-failed-in-production.md) — benchmark green, users not
