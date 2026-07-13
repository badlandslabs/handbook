# S-1035 · The Context-Capacity Gap: When Your Agent Reads Everything and Knows Less

Your model has a 200K-token context window. Your agent loads 180K tokens. And it still misses the answer that was in paragraph 3. You are not imagining this — you are hitting the context-capacity gap, and the advertised number is a lie.

The gap between what models claim and what they actually use has been measured at 30-40%. Degradation begins around 130K tokens. A rolling window silently drops the oldest context without error. The agent keeps running — confidently wrong, with no signal that anything went wrong.

## Forces

- **The advertised window is not the usable window.** Models lose effective attention to the middle 40-60% of long contexts (the "lost in the middle" effect — not a bug, an architectural adaptation). A 200K window is a 70K working-memory ceiling, not a 200K one.
- **Silent eviction is the worst failure mode.** When context fills, most agents quietly drop the oldest messages. No error is thrown. No alarm fires. The agent continues answering, citing information from turns ago that no longer exists in context.
- **Context capacity degrades, not cliffs.** The degradation is gradual and content-position-dependent, not binary. Adding more context past the threshold doesn't produce crashes — it produces slow accuracy decay that benchmarks miss and users attribute to "the model having a bad day."
- **The gap compounds in multi-step tasks.** Each step consumes tokens. At step 8 of a 10-step task, you may have 35% of the original context remaining — and the most important grounding information (the user's original request) was evicted at step 5.

## The move

### 1. Treat advertised capacity as a ceiling, not a target

Design for 60-70% of the window as your hard limit:

```
effective_limit = advertised_window × 0.65
```

For a 200K window: plan for 130K. For 1M: plan for 650K. This is not a workaround — it is the measured operating envelope.

### 2. Name the eviction policy explicitly

Every agent must declare its eviction strategy before the first call:

| Policy | Behavior | When to use |
|--------|----------|-------------|
| **FIFO rolling** | Drop oldest turns | Short tasks, stateless interactions |
| **Priority-tiered** | Preserve system prompt + user request; evict middle turns first | Multi-step tasks with known critical anchors |
| **Checkpoint-compress** | Summarize at 60% fill; resume from compressed state | Long-horizon tasks (planner-worker pattern, S-357) |
| **Semantic eviction** | Drop semantically redundant chunks; keep discriminative ones | Research/review tasks over large corpora |

Do not default to FIFO. The user's original request (turn 1) is almost always the most important — FIFO evicts it first.

### 3. Instrument the pressure signal

Track context fill rate as a first-class metric:

```
context_pressure = tokens_in_context / effective_limit
```

- Alert at 60% fill: trigger pre-emptive compression or summarization
- Alert at 80% fill: checkpoint current state before continuing
- At 95%: halt and surface a context-exhaustion event to the orchestrator, not the user

Do not wait for the model to tell you it degraded. Measure the pressure that causes degradation before it manifests.

### 4. Anchor critical information at both edges

The "lost in the middle" effect means attention is highest at the start and end of context. Place irreplaceable grounding at both positions:

```
[System prompt] ... [early context] ... [middle — degraded] ... [recent context] [User request]
                                              ↑ lost                   ↑ remembered
```

Move the user's original request to the end of the context window on each significant step. Move critical task state to the beginning. Do not let the original request sit in the middle of a long conversation.

### 5. Validate after high-pressure turns

After any turn where context_pressure > 0.7, run a lightweight grounding probe:

```
probe: "In one sentence, what is the user trying to accomplish in this session?"
```

If the answer drifts from the ground truth, the context has degraded. Trigger recovery (compress + re-inject) before continuing.

## Receipt

> Verified 2026-07-13 — Supermemory (May 2026) measured effective context at 60-70% of advertised, with degradation onset at ~130K tokens. The rolling-window silent eviction pattern was confirmed across production agent deployments described in MLflow (May 2026) and the 37% production gap documented by Abaka AI. The "lost in the middle" structural explanation was confirmed via arXiv:2510.10276 (Oct 2025), which models it as an emergent property of attention heads trained on memory paradigms, not a fixable bug. Supermemory measured +18% accuracy and 2.5× cost reduction per query when persistent memory retrieval replaced context-window accumulation.

## See also
- [S-342 · Autonomous Context Compression](s342-autonomous-context-compression.md) — the compaction mechanism when pressure hits
- [S-985 · The Tiered Memory Stack](s985-the-tiered-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — cross-session persistence beyond the context window
- [S-357 · Long-Running Agent Orchestration (Planner-Worker)](s357-the-planner-worker-orchestration-stack-when-your-agent-cant-see-the-bigger-picture.md) — checkpoint-compress as part of temporal layer design
- [S-111 · Partial Context Refresh](s111-partial-context-refresh.md) — surgical refresh of stale evidence without full context eviction
- [S-1030 · The Forgetting Stack](s1030-the-forgetting-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — what to write when you do remember, not what to keep
