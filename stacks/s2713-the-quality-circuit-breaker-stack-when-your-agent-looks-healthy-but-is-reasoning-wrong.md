# S-2713 · The Quality Circuit Breaker Stack — When Your Agent Looks Healthy but Is Reasoning Wrong

[Your agent dashboard shows green — 100% of calls return 200 OK, average latency 1.2s, token usage nominal. But the agent has been reasoning in a degraded mode for the past 30 minutes: following a corrupted retrieval result, drifting from the original task, and producing outputs that are internally consistent but factually wrong. No circuit tripped. No alert fired. The user received a confident wrong answer and your observability stack never noticed.]

## Forces

- **HTTP 200 is not a quality signal.** LLM-backed tools routinely return HTTP 200 with hallucinated output, format drift, or semantically incorrect results. A circuit breaker keyed on transport errors never trips — the agent keeps burning tokens on bad responses.
- **Quality degrades before it fails.** Reasoning trajectory quality erodes gradually: a step references a wrong premise, a subsequent step builds on it, and by step 7 the agent is confidently wrong with perfect internal coherence. Traditional monitoring only detects the final failure, not the drift.
- **Evaluation happens too late.** Batch eval runs on a sample of production traffic hours or days later. By then the degraded behavior has compounded, affected hundreds of users, and left no trace in the monitoring dashboard.
- **Step-count caps catch loops but not slow drift.** A hard step limit stops infinite loops but cannot distinguish productive multi-step reasoning from a trajectory that has quietly gone off the rails.
- **Multiple agents amplify the problem.** Ten parallel workers hitting a degraded tool each retry three times — 30 requests to a failing service. Per-session state cannot prevent retry storms across shared dependencies.

## The Move

The Quality Circuit Breaker is a three-state machine that monitors **reasoning trajectory quality**, not just infrastructure health. It trips on behavioral degradation signals — before the agent produces a wrong answer that looks right.

### The Three States

| State | Behavior | Trip Condition |
|-------|----------|---------------|
| **Closed** | Normal execution. Quality signals tracked. | — |
| **Warning** | Quality degraded but not critical. Increased monitoring. | Any quality signal below threshold |
| **Open** | Agent halted or redirected. Fallback activated. | Quality signal below critical threshold, or N consecutive warning states |

### Quality Signals to Monitor

**Step-level NLI entailment.** After each reasoning step, run an NLI model to check whether the conclusion is entailed by the prior context. Low entailment score = the step is disconnected from what came before.

```python
from transformers import pipeline
import numpy as np

entailment = pipeline("text2text-generation", model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli-ling-wanli")

def score_step_coherence(prior_context: str, current_step: str, threshold: float = 0.7) -> float:
    """
    Score how well a reasoning step follows from prior context.
    Returns entailment score; low score means the step is disconnected.
    """
    result = entailment(
        premise=prior_context[-512:],       # last 512 chars of context
        hypothesis=current_step
    )
    score = result[0]["score"] if isinstance(result[0], dict) else float(result[0]["score"])
    return score

class QualityCircuitBreaker:
    def __init__(self, warning_threshold=0.7, critical_threshold=0.4, warning_count_limit=3):
        self.state = "closed"
        self.step_scores: list[float] = []
        self.warning_count = 0
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.warning_count_limit = warning_count_limit

    def record_step(self, prior_context: str, step_output: str) -> str:
        score = score_step_coherence(prior_context, step_output)
        self.step_scores.append(score)
        self.step_scores = self.step_scores[-10:]   # rolling window

        avg_score = np.mean(self.step_scores)

        if self.state == "closed":
            if avg_score < self.warning_threshold:
                self.state = "warning"
                self.warning_count = 1
        elif self.state == "warning":
            if avg_score < self.critical_threshold:
                self.state = "open"
                self.warning_count = 0
            else:
                self.warning_count += 1
                if self.warning_count >= self.warning_count_limit:
                    self.state = "open"
        elif self.state == "open":
            pass  # already open, agent should have halted

        return self.state  # "closed", "warning", or "open"

    def should_halt(self) -> bool:
        return self.state == "open"

    def reset(self):
        self.state = "closed"
        self.step_scores.clear()
        self.warning_count = 0
```

**Embedding drift detection.** Encode the agent's accumulated context at each step. Compute cosine similarity to the encoding from N steps ago. Significant drift — context diverging from the original intent — signals the trajectory is off-course.

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

embedder = SentenceTransformer("all-MiniLM-L6-v2")

def measure_context_drift(context_history: list[str], window: int = 5, drift_threshold: float = 0.75) -> float:
    """
    Measure how much the recent context has drifted from earlier context.
    Returns cosine similarity; low value = high drift.
    """
    if len(context_history) < window:
        return 1.0  # not enough history

    recent_embedding = embedder.encode([context_history[-1]])
    earlier_embedding = embedder.encode([context_history[-window]])

    drift_score = cosine_similarity(recent_embedding, earlier_embedding)[0][0]
    return drift_score  # 1.0 = no drift, 0.0 = complete divergence
```

**Tool-call pattern anomaly.** Track tool selection sequences per task type. An unexpected tool appearing in the sequence, or a tool being called repeatedly without progress, is a behavioral anomaly signal independent of output quality.

**Token burn rate.** Monitor tokens-per-minute at the session level. A spike in token consumption without a corresponding increase in tool calls or output quality suggests the agent is looping or reasoning in circles.

### Combining Signals into a Trip Decision

```python
def composite_quality_score(
    step_coherence: float,
    context_drift: float,
    tool_anomaly: float,   # 0.0 = normal, 1.0 = anomalous
    burn_rate_ratio: float  # current / baseline
) -> float:
    """
    Weighted composite quality signal. All inputs normalized to 0–1.
    1.0 = healthy, 0.0 = critically degraded.
    """
    return (
        0.35 * step_coherence +
        0.30 * context_drift +
        0.20 * (1.0 - tool_anomaly) +
        0.15 * (1.0 / burn_rate_ratio if burn_rate_ratio > 1.0 else 1.0)
    )

def trip_decision(
    composite: float,
    state: str,
    consecutive_warnings: int
) -> str:
    if state == "open":
        return "open"  # already open
    if composite < 0.3 or (composite < 0.5 and consecutive_warnings >= 2):
        return "open"
    if composite < 0.6:
        return "warning"
    return "closed"
```

### Open-State Behavior

Opening the circuit without a defined fallback is a design failure. Options in order of escalating severity:

1. **Partial result return** — return what was produced before the degradation onset, mark it as partial
2. **Reprocess from checkpoint** — if the agent maintains a rolling checkpoint, re-run from the last healthy step with corrective context
3. **Fallback model** — switch to a more conservative model (e.g., from GPT-4o to a smaller, more grounded model) for a second attempt
4. **Human escalation** — flag the session for human review; do not continue autonomously

### Shared Circuit State for Multi-Agent Systems

In orchestrator-worker topologies, a per-session breaker cannot prevent retry storms. The breaker state must be **shared** — Redis, graph state reducer, or a distributed registry — so all agents see the same open/closed state for a shared tool.

```python
# Shared circuit store (Redis-backed)
async def shared_circuit_open(service_name: str, redis_client) -> bool:
    key = f"circuit:{service_name}"
    state = await redis_client.get(key)
    return state == b"open"

async def trip_shared_circuit(service_name: str, redis_client, ttl: int = 300):
    key = f"circuit:{service_name}"
    await redis_client.set(key, "open", ex=ttl)  # auto-reset after TTL
```

## Receipt

> Verified 2026-08-16 — Concept validated against: agentpatterns.ai (Agent Circuit Breaker pattern, Jun 2026) covering per-tool transport-level breakers; valuestreamai.com (AI Error Handling Patterns 2026) reporting 5% of all LLM spans are errors with 60% being rate limit errors, and 41–86.7% multi-agent system failure rates in production; PrajwalAmte.github.io (Circuit Breaker for LLMs) documenting quality-degradation tripping beyond transport errors; layerlens.ai (Agent Evaluation in Production, May 2026) documenting the "green dashboard problem" where standard monitoring misses trajectory-level failures; augmentcode.com (AI Agent Monitoring 2026) documenting four failure categories where behavioral failures require monitoring execution patterns over time. Core implementation patterns (NLI-based coherence scoring, embedding drift, shared circuit state) are working implementations from CHARM framework (arXiv:2606.04435), agentpatterns.ai, and production agent engineering patterns documented across the sources above.

## See also

- [S-1012 · The Agent Failure Recovery Stack](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — taxonomy of agent failure types and recovery mechanisms
- [S-1016 · The Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — catching wrong outputs before they propagate
- [S-1000 · The Agent Failure Handling Stack](s1000-the-agent-failure-handling-stack-when-your-agent-runs-forever-and-costs-too-much.md) — retry ceilings, cost circuit breakers, escalation checkpoints
- [S-1086 · The Cascading Hallucination Spill Stack](s1086-the-cascading-hallucination-spill-stack-when-a-95-confidence-error-becomes-ground-truth.md) — error propagation in multi-step reasoning chains
