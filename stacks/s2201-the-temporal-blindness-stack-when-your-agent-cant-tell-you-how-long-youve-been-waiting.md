# [S-2201] · The Temporal Blindness Stack

You ask an agent to "remind me in a week" and it confirms — then, seven days later, there is no reminder. You give it a deadline: "finish this by Friday" — and it files a report on Saturday morning without noticing. You set a timer for 30 minutes and check back in four hours; the agent has been running continuously, waiting for a signal that never came because it doesn't know what time it is. These are not separate bugs. They are one bug: **temporal blindness** — the architectural inability of an agentic system to track, remember, or reason about time across the span of its own operation.

## Forces

- **The stateless session assumption.** Most agent runtimes model each conversation as a fresh start. The conversation context window has a beginning but no clock. Time is not a native dimension of the prompt context — it must be explicitly constructed.
- **Token-level generation, continuous-time problems.** LLMs generate tokens in discrete steps with no internal model of elapsed wall-clock time. A task deadline is just another token; "urgently" and "eventually" are equally meaningless without temporal grounding.
- **The annotation gap.** Humans communicate deadlines and schedules in natural language — "by EOD Friday," "check back in an hour," "after the quarterly report is done." These expressions require external parsing and persistent tracking that the model cannot perform unaided.
- **The memory-timeline mismatch.** Agent memory frameworks store *what* happened, not *when* relative to a persistent clock. The agent remembers the task but not the schedule.
- **Deadline blindness under real-time constraints.** arXiv:2601.13206 (Sehgal et al., UPenn, Jan 2026) documents that LLMs achieve near-perfect performance on turn-limited negotiation tasks (≥95% deal closure) but drop to 4% closure under equivalent real-time deadlines — even when the time budget is identical. The failure is not in reasoning. It is in temporal tracking.

## The move

Temporally-aware agents require three architectural layers that most agentic systems are missing: a **persistent clock**, a **structured timeline**, and an **expiration mechanism**.

### Layer 1 — The Persistent Clock

Do not rely on wall-clock time embedded in the prompt. Instead, feed the agent a durable clock signal at every turn:

```
SYSTEM:
The current time is {persistent_clock.iso8601()}.
A persistent deadline tracker is available as tool `check_deadlines`.
After every tool call, inject: "It is now {now}. Active deadlines: {deadlines}."
```

The key is `persistent_clock` — a value that survives across sessions. This can be a file (`.atime` per AgenticTime's `.atime` file format), a database row, or a lightweight time-state service. What matters is that it is external to the session and consulted on every turn, not embedded once at session start.

### Layer 2 — Structured Timeline with Expiration

Replace unstructured "remind me" instructions with structured timeline entries that carry explicit expiration logic:

```
timeline.add(
    id="report-draft",
    description="Draft Q3 financial report",
    deadline=datetime(2026, 8, 15, 17, 0),   # Friday 5 PM
    escalation_after=datetime(2026, 8, 14, 9, 0),  # Thursday 9 AM
    owner="finance-agent",
    notify=["user", "manager"],
    on_expire="escalate_to_manager"
)
```

The agent writes timeline entries. The timeline infrastructure enforces them. The agent's job is to *plan against* the timeline, not to remember it. When the agent queries the timeline on any turn, it gets the current state: what's overdue, what's due today, what's coming up.

### Layer 3 — Duration Feedback and PERT Estimation

Agents chronically underestimate or overestimate how long tasks take. Fix this by tracking actual durations and feeding them back:

```python
# Agent records start of a task
task_id = timeline.start_task("review-pr-4823")
# ... agent does work ...
timeline.complete_task(task_id)  # Records actual_duration

# On next similar task, agent can query:
timeline.get_estimated_duration("review-pr", sample_count=5)
# → PERT(mean=22min, p10=14min, p90=41min, confidence="medium")
```

AgenticTime implements this as PERT (Program Evaluation and Review Technique) with confidence intervals and decay models. The agent incorporates the estimate into its planning — not as a wild guess, but as a statistically grounded range.

### Layer 4 — Decay-Aware Prioritization

Not everything has equal urgency. Apply temporal decay to task priority:

```python
priority = base_priority * decay_factor(elapsed_time / deadline_window)

# Example: a task that was P1 but is 2 days before deadline → still P1
# Same task 3 days after deadline → P0+ (overdue escalation)
# Same task with no deadline → static priority (no decay signal)
```

Without explicit decay, agents treat a week-old task as equivalent to a fresh one. With decay, the timeline naturally surfaces what needs attention *now*.

### Layer 5 — Conflict Detection

Multi-step workflows with temporal constraints create scheduling conflicts the agent cannot see:

```
timeline.add_sequence("quarterly-report", steps=[
    {"id": "collect-data",     "duration_min": 120},
    {"id": "draft-narrative",  "duration_min": 90, "depends_on": ["collect-data"]},
    {"id": "review-draft",     "duration_min": 60, "depends_on": ["draft-narrative"]},
    {"id": "final-submission", "duration_min": 30, "depends_by": deadline},
])
# Returns: "Conflict: sequential steps require 300 min
# but deadline allows only 240 min. Options: parallelize
# collect-data+review-draft (if data is pre-cached), or
# escalate deadline extension."
```

This catches deadline failures *before* the agent starts working, not after the fact.

## Receipt

> Verified 2026-08-05 — arXiv:2601.13206 (Sehgal et al., UPenn, Jan 2026): LLM strategic agents drop from 95%+ to 4% task completion under real-time deadlines vs. turn-limited equivalents, confirming temporal blindness is a systematic architectural failure. AgenticTime (agentralabs/agentic-time, MIT, Feb 2026) provides a reference implementation of the structured timeline + PERT estimation + decay model pattern. The five-layer approach above synthesizes findings from Sehgal, AgenticTime, and production patterns from temporal reasoning engineering teams at Microsoft and Anthropic (per internal references in agent observability documentation).

## See also
- [S-114 · Reasoning Scratchpad Budget](s114-reasoning-scratchpad-budget.md) — related: how to allocate thinking budget over time
- [S-1244 · The Context Fill Cliff](s1244-the-context-fill-cliff-when-your-agent-runs-great-at-message-5-and-terrible-at-message-50.md) — related: agents degrade over long sessions; temporal tracking compounds this
- [S-1189 · The Memory Integrity Gate](s1189-the-memory-integrity-gate-when-your-agents-long-term-memory-is-corrupting-one-fact-at-a-time.md) — related: memory persistence patterns; timeline state should be governed like any persistent memory
