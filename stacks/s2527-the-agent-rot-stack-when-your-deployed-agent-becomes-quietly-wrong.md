# [S-2527] · The Agent Rot Stack — When Your Deployed Agent Becomes Quietly Wrong

Your agent is running. Uptime is 99.9%. Latency is fine. Token usage is normal. The dashboard is green. And the answers it is giving your customers are confidently, consistently wrong — because the world changed and the agent didn't notice. This is agent rot: the silent divergence between what your deployed agent believes and what is actually true.

A traditional system fails loudly — a 500 error, a stack trace, an alert. An agent fails silently, returning a confident, factually wrong answer while every metric stays healthy. Rot is not a crash. It is the slow accumulation of world-model drift until the agent is building on a foundation that no longer matches reality. It is the defining production failure mode of 2026.

## Forces

- **The world is dynamic; the agent's world model is not.** Every agent maintains an implicit model of external reality constructed from tool call results, file reads, API responses, and user statements. This model lives in context — it is a snapshot, not a live feed. When that snapshot diverges from the actual state of the world, the agent operates on fiction, and it does so confidently.
- **Standard monitoring catches crashes, not wrong answers.** Uptime checks, latency dashboards, and error rate alerts are all green because the agent is not failing — it is succeeding at the wrong task. The gap between "working correctly" and "working on stale data" is invisible to every conventional monitoring signal.
- **Rot compounds because agents act on their world model.** Unlike a passive model, an agent writes its beliefs into downstream systems — creates files, sends emails, updates records, triggers pipelines. Each action based on a rotted world model potentially propagates the wrong state further. A stale context entry becomes a stale database record becomes a stale customer answer.
- **RAG retrieval surfaces the closest match, not the correct one.** Embedding similarity search answers "which text is most similar to the query?" — not "which doc is current?" An old runbook and the current runbook can be almost identical in wording, so the stale copy scores just as high. The agent retrieves fiction and treats it as ground truth.

## The move

**Three-layer rot detection architecture:**

**Layer 1 — Source-of-truth anchoring.** Every agent task that depends on external state should be able to name the authoritative source and the time it was last fetched. Store `{source, field, fetched_at, value_hash}` alongside the agent's working memory. Before any downstream action, verify the current hash against the source. If stale, re-fetch and invalidate the local copy.

```python
from datetime import datetime, timedelta
import hashlib, json

class WorldModelCache:
    def __init__(self, ttl_seconds: int = 300):
        self.cache: dict[str, dict] = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def set(self, source: str, field: str, value: str):
        key = f"{source}::{field}"
        self.cache[key] = {
            "value": value,
            "fetched_at": datetime.utcnow(),
            "hash": hashlib.sha256(value.encode()).hexdigest()[:16],
        }

    def is_fresh(self, source: str, field: str) -> bool:
        key = f"{source}::{field}"
        entry = self.cache.get(key)
        if not entry:
            return False
        return datetime.utcnow() - entry["fetched_at"] < self.ttl

    def stale_fields(self, source_fields: list[tuple[str, str]]) -> list[str]:
        """Return list of keys that need re-fetching."""
        return [f"{s}::{f}" for s, f in source_fields if not self.is_fresh(s, f)]
```

**Layer 2 — Semantic freshness signal.** Beyond timestamp-based TTL, detect when the *meaning* of retrieved content has changed. Use a lightweight LLM-as-judge call to compare a cached retrieval result against a current fetch and flag semantic drift. Key signal: embedding freshness score (vector similarity of current vs. cached retrieval results drops below threshold). Ground-truth queries — a set of known factual questions with known answers — detect when the agent's retrieval quality has degraded without needing to know what changed.

```python
import numpy as np

def compute_freshness_score(cached_embedding: np.ndarray, 
                             current_embedding: np.ndarray) -> float:
    """Cosine similarity. Below 0.7 = semantic drift detected."""
    similarity = np.dot(cached_embedding, current_embedding) / (
        np.linalg.norm(cached_embedding) * np.linalg.norm(current_embedding)
    )
    return float(similarity)

def ground_truth_check(agent, ground_truth_queries: list[dict]) -> float:
    """Run known-fact queries. Score = fraction answered correctly."""
    correct = sum(
        1 for q in ground_truth_queries
        if q["expected_answer"] in agent.query(q["question"])
    )
    return correct / len(ground_truth_queries)
```

**Layer 3 — Outcome-level verification gate.** The only signal that reliably detects rot is outcome verification — checking whether the agent's actual effect on the world matches the intended effect. This goes inside the agent loop: after each major action, query the system of record directly and compare with the agent's belief.

```python
def verify_world_belief(agent_belief: dict, source_of_record: callable) -> bool:
    """
    agent_belief: {'resource': 'order_1234', 'field': 'status', 'value': 'shipped'}
    source_of_record: callable(resource, field) -> actual_value
    Returns True if agent belief matches reality.
    """
    actual = source_of_record(agent_belief['resource'], agent_belief['field'])
    return actual == agent_belief['value']

# In the agent loop:
for action in planned_actions:
    agent.act(action)
    if not verify_world_belief(agent.memory.last_belief(), get_db_record):
        agent.invalidate_memory()
        agent.replan()
        break
```

**Anti-patterns to avoid:**
- Relying solely on TTL-based cache invalidation — the world changes on business timelines, not fixed intervals
- Using embedding similarity alone — embedding drift and factual drift are not the same thing
- Alerting on "no errors" — the only meaningful rot alert is a ground-truth check failure

## Receipt

> Verified 2026-08-12 — VerySmartParrot "Agent Rot" talk (May 2026, updated July 2026) formally names this phenomenon: "the gradual degradation of a deployed agent's output quality as the world drifts away from the assumptions it was built on." Tian Pan (April 2026) documents the stale tool description problem as the concrete mechanism: schema drift turns stale descriptions into silent failure vectors. Trovex (June 2026) documents why embedding retrieval surfaces stale docs: "similarity, not freshness." Vectara/awesome-agent-failures repo (89 commits, Apache 2.0) catalogs tool hallucination and response hallucination as distinct from, but connected to, world-model staleness. MG6 (July 2026): Gartner projects 40% of agentic AI projects cancelled by 2027 due to unclear value and inadequate risk controls — rot is a primary driver. The three-layer architecture is synthesized from practitioner patterns across these sources. Verified against existing handbook entries: S-2388 (Context Rot) covers in-session attention degradation, not world-state staleness; S-2521 (Consistency) covers cross-run variability, not environmental drift; S-818 (Longitudinal Eval) covers capability drift detection, not the root mechanism. This entry is novel.

## See also

- [S-2388 · The Context Rot Stack](/stacks/s2388-the-context-rot-stack-when-your-agent-slowly-forgets-what-you-already-told-it.md) — internal session degradation vs. external world drift
- [S-2303 · The Eval Harness Regression Gate Stack](/stacks/s2303-the-eval-harness-regression-gate-stack-when-your-agent-prometheus-passed-last-week-but-got-worse.md) — ground-truth fixture patterns for regression detection
- [S-2512 · The Production Agent Floor Stack](/stacks/s2512-the-production-agent-floor-stack-when-your-agent-returns-200-but-is-failing.md) — minimum viable production monitoring surface
