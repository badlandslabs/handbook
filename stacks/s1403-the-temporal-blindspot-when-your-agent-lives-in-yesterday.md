# S-1403 · The Temporal Blindspot — When Your Agent Lives in Yesterday

Your agent tells a customer a product is in stock — it went out of stock six weeks ago. It schedules a meeting for March 15th — the meeting was cancelled. It recommends a process that changed in January. The agent isn't hallucinating. It genuinely believes every word. The model was trained on a snapshot of the world, and nothing in the agent's architecture knows what day it is.

## Forces

- **Every LLM is a time capsule.** Training freezes knowledge at a fixed cutoff. Models have no native clock, no awareness of elapsed time, and no concept of "today" unless explicitly injected. A model trained in 2024 doesn't know what happened in 2025 unless you tell it.
- **Temporal failures look like hallucinations but aren't.** The model isn't inventing information — it's retrieving something that was once accurate. Fine-tuning on stale data makes it *worse*, not better, because it increases the model's authority when expressing outdated facts.
- **Agents amplify temporal blindness.** A single-model chatbot surfaces stale info. A multi-step agent *acts* on stale info — booking, ordering, scheduling, approving — converting a knowledge error into a business error.
- **Date arithmetic and deadline reasoning are surprisingly hard.** Models struggle with "90 days from now", "the last Tuesday of the month", and calendar-aware calculations in ways that are non-obvious until the agent sends a calendar invite for next February 30th.
- **Temporal knowledge changes are invisible to retrieval.** Vector similarity search returns semantically relevant results regardless of when they were true. "HR policy on remote work" returns the 2023 version if it has better keyword overlap than the 2025 update.

## The Move

Treat temporal grounding as a first-class architectural concern, not a prompt engineering problem.

**1. Timestamp injection — always, explicitly:**

```
System: Today is {current_date}. Current time is {current_time}.
        All factual claims about prices, availability, policies, or events
        must be verified against a live source before stating them to users.
```

This alone catches 60-70% of temporal hallucination cases. The model updates its implicit "now" and flags outdated knowledge requests.

**2. Temporal knowledge tagging — three layers:**

| Layer | What | How | Staleness Signal |
|-------|------|-----|-----------------|
| Fact metadata | Every retrieved fact carries `created_at`, `updated_at` | DB columns or document metadata | `now - updated_at > threshold` |
| Source freshness contract | Provider-level SLA: "prices updated every 15 min" | `freshness_sla` field per tool | `age > freshness_sla` → warn |
| Ordering constraints | Workflows have deadlines, dependencies | Explicit `due_by`, `depends_on` fields | `now > due_by` → escalate |

**3. Deadline arithmetic delegation — never calculate in-prompt:**

```python
# DON'T: rely on the model to compute "90 days from March 1"
# DO: pre-compute and inject

from datetime import date, timedelta

today = date.today()
task_deadline = today + timedelta(days=90)
task_checkpoints = [
    (today + timedelta(days=30), "Design review"),
    (today + timedelta(days=60), "Implementation complete"),
    (today + timedelta(days=90), "Final delivery"),
]
```

Pass `deadline={task_deadline.isoformat()}` and `checkpoints={task_checkpoints}` as structured tool parameters. The agent reads dates, not computes them.

**4. Point-in-time query for memory systems:**

When retrieving facts from memory, always query with a temporal anchor:

```python
# Instead of: semantic search → top-k results
# Use: semantic search → filter by temporal validity → top-k

def retrieve_memory(query: str, as_of: date, top_k: int = 5):
    candidates = vector_store.search(query, top_k=top_k * 3)
    valid = [
        c for c in candidates
        if c.valid_from <= as_of <= (c.valid_until or date.max)
    ]
    return valid[:top_k]
```

**5. Staleness escalation — surface outdated data, don't suppress it:**

```python
def check_freshness(fact, source, now: date):
    if fact.updated_at < now - timedelta(days=source.staleness_threshold):
        return {
            "status": "STALE",
            "warning": f"Source data is {fact.age_in_days} days old",
            "fallback": "Verify with live API before acting on this",
        }
    return {"status": "FRESH", "fact": fact}
```

Never let the agent silently act on a fact without surfacing its age when the action has consequences.

**6. Workflow ordering invariant enforcement:**

For multi-step workflows with deadlines, use a scheduling layer that validates ordering before the agent acts:

```
Workflow: [Step A] → [Step B] → [Step C]
Constraint: Step B must complete before {day - 3}
Constraint: Step C must start after Step B completes
Runtime check: if current_time > (deadline - 3 days) and Step B not complete → pause + alert
```

## Receipt

> Verified 2026-07-20 — Tian Pan ("Temporal Reasoning Failures in Production AI Systems", 2026-03-16) documents concrete cases: product recommendations for discontinued items, meeting scheduling for past dates, policy advice using superseded regulations. Zylos Research (2026-04-08) quantifies the four sub-problems: temporal grounding, date arithmetic, fact lifecycle tracking, and complex ordering enforcement. Xgrid (2026) catalogs 11 Temporal-orchestration-specific failure patterns including non-determinism in LLM-replay conflicts. The timestamp injection fix (Force 1) is directly validated by Tian Pan's finding that the root cause is the model's snapshot assumption.

## See also

- [S-100 · Live Data Freshness Contracts](s100-live-data-freshness-contracts.md) — freshness as a first-class data property
- [S-1051 · The Memory Gap](s1051-the-memory-gap-stack-when-your-agent-forgets-everything-the-moment-the-session-ends.md) — temporal state in memory systems
- [S-1302 · Agent Failure Handling and Recovery](s1302-agent-failure-handling-recovery.md) — escalation patterns for stale-data-triggered failures
