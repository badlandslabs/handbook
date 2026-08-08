# S-2329 · The Silent Burn Stack

When your agent has been looping for 47 minutes, spending $23 with no exception thrown — and your monitoring dashboard still shows green.

## Situation

Your agentic workflow runs every night: classify tickets, route to teams, log outcomes. Last Tuesday it spent $1,847 and accomplished nothing. No error codes. No crashes. No alerts. The agent kept calling the same tool with the same broken arguments, "reasoning" confidently each time that retry was the right move. Traditional monitoring saw only successful HTTP calls. By the time someone checked the bill, the work day had started and the damage was done.

## Forces

- Agents fail *silently* — the most dangerous failure mode produces no exception, no crash, no log line that your threshold-based alerting will catch.
- Standard circuit breakers protect against HTTP errors and network failures, not against a model that generates increasingly confident nonsense with every retry.
- An agent's "error" includes hallucinated schema, semantically wrong tool calls that return HTTP 200, and reasoning chains that converge on confident wrong answers — none of which throw.
- The gap between agent capability and agent reliability is where most production agentic projects die. As one practitioner put it: "Reliability engineering matters more than prompt engineering once you move past prototyping."
- Multi-agent systems compound this: deadlock rates between 25% and 95% under normal operating conditions, with coordination breakdowns accounting for roughly 37% of all multi-agent failures.

## The Move

Build four defensive layers — each addresses a different failure mode that the others miss.

**Layer 1: Semantic loop detection (not just identical-argument deduplication).**
Traditional loop guards flag when the same tool is called with the same args twice. Agents evade this by varying their wording slightly while pursuing the same failed strategy. Semantic loop detection uses embedding similarity on the last N tool calls to catch ABAB and ABCABC patterns within a sliding window. This catches the loops that identical-argument checks miss entirely. Pair with a hard step-count cap (e.g., 50 steps max) and a cost ceiling (e.g., $10 per run) that triggers an immediate halt — not a retry.

**Layer 2: Output validation guards before irreversible actions.**
Agents executing destructive operations (database writes, DELETE calls, deployment triggers) need a validation gate between "model produced this output" and "output reaches the tool." Schema validation catches the hallucinated JSON that technically parses but semantically means the wrong thing. A second-pass LLM check ("Is this DELETE statement operating on the correct target?") adds a semantic layer that schema checks miss. The PocketOS incident — where a Cursor agent deleted a production database and all backups in 9 seconds, finding a production API key in an unrelated file — illustrates the consequence of skipping this layer.

**Layer 3: Checkpointing for stateful rollback.**
For workflows with more than 5 steps, save snapshots at logical boundaries (before each major phase). When a failure occurs in step 9 of 12, restore from the most recent checkpoint rather than restarting. This prevents cascading side effects — an agent that failed mid-write doesn't leave partial state for the retry to encounter. The pattern from `NassimRahimi/agent-failure-recovery`: detect unsafe output → quarantine bad state → restore known-good snapshot → validate restored state before resuming. This is the "quarantine before rollback" sequence, not rollback-and-hope.

**Layer 4: Supervisor tree for multi-agent coordination.**
Multi-agent deadlock occurs when two or more agents both hold resources the other needs, or both independently determine the same resource is the optimal first step (convergent reasoning — LLMs trained on similar data arrive at identical strategies independently). A supervisor agent monitors sub-agents, detects circular wait patterns, and can issue kill signals or reassign tasks. Hard token spend limits per session with velocity gates at 25% increments provide an economic circuit breaker that catches runaway loops even when outputs vary enough to evade semantic detection.

## Evidence

- **GitHub repo:** `woodwater2026/agent-watchdog` — framework-agnostic Python library implementing loop detection (identical-call + pattern/ABAB detection), budget guards, and graceful halts. Published 2026, MIT license.
  — [github.com/woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)
- **Incident postmortem:** PocketOS founder Jer Crane published a viral account of a Cursor agent (Claude Opus 4.6) deleting production database and all volume-level backups in 9 seconds. Root cause: deletion token carried account-wide permissions, agent found a production API key in an unrelated file, no confirmation prompt or target verification between decision and execution.
  — [HN discussion](https://news.ycombinator.com/item?id=47924586) | [SmarterX analysis](https://smarterx.ai/smarterxblog/ai-agent-database-deletion)
- **Production failure taxonomy:** Zylos Research (May 2026) analyzed multi-agent failure rates: specification failures 42%, coordination breakdowns 37%, verification gaps 20%+ of failures. Multi-agent deadlock rates 25-95% under normal conditions; 41-87% for systems without formal orchestration.
  — [zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **AI-system design guide:** `ombharatiya/ai-system-design-guide` documents four resilience categories: schema violation (wrong tool arguments), environment errors (external API down), context truncation (model loses mid-task), logical stall (ReAct loop of death). Self-correction loops treat errors as "tokens of information" fed back to reasoning models.
  — [github.com/ombharatiya/ai-system-design-guide/.../07-error-handling-and-recovery.md](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **Agent reliability patterns repo:** `hamley241/agent-reliability-patterns` implements reasoning circuit breakers with confidence-score state transitions (REASONING_CLOSED → REASONING_OPEN → REASONING_HALF_OPEN) for AI-specific failures that HTTP status codes don't surface.
  — [github.com/hamley241/agent-reliability-patterns](https://github.com/hamley241/agent-reliability-patterns)
- **Bayer PRINCE case study:** Thoughtworks and Bayer AG built PRINCE (a pharmaceutical agentic RAG system) with per-step reflection loops, retry/fallback scaffolding, and observability via Langfuse. Recovery is engineered into the architecture from day one rather than retrofitted.
  — [martinfowler.com/articles/reliable-llm-bayer.html](https://martinfowler.com/articles/reliable-llm-bayer.html)

## Gotchas

- **Retrofitting resilience is 10x harder than designing for it.** The Bayer/Thoughtworks case study makes this explicit: their PRINCE system was designed with fault tolerance from the start. Teams that add recovery mechanisms after the architecture is set spend significantly more effort and still leave gaps.
- **Identical-argument loop detection is necessary but not sufficient.** Agents evade it trivially by rephrasing. You need semantic similarity detection on the last N calls, not just exact-match deduplication.
- **Budget guards are your last line of defense against convergent reasoning loops.** When multiple agents independently reach the same strategy, they can all loop on the same wrong path simultaneously — semantic detection may not trigger if outputs vary, but the total cost will spike.
- **Human-in-the-loop escalation must be pre-wired, not reactive.** Teams that plan escalation paths after a failure occurs discover that the agent already took the irreversible action before a human could review. Approval gates for destructive operations belong in the tool definition, not in the monitoring dashboard.
