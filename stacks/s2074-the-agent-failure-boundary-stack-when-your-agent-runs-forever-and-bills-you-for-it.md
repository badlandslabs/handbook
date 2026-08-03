# S-2074 · The Agent Failure Boundary Stack — When Your Agent Runs Forever and Bills You For It

When your agent loops, times out, or cascades into a cost spiral — and you have no guardrails to stop it.

## Forces

- Agents are non-terminating by nature — the loop is the feature, until it isn't
- Token burn is silent and linear; failure is sudden and non-linear — the gap between them is where budgets die
- Existing loop guards (max_iterations) are arbitrary caps that stop too early or too late, and often ship the worst output from the last iteration
- Retry logic without budget math creates cascading failure: one slow tool triggers retries, which trigger more load, which makes the tool slower
- Framework defaults (CrewAI, LangChain) ship without timeouts or circuit breakers — "it works in the demo" is the only guide
- The failure modes are architectural, not model-related — the model isn't wrong, the plumbing is

## The Move

Build explicit, layered guardrails that enforce termination, cost, and quality bounds independently:

- **Budget before retries.** Define the hard deadline first (e.g., 30s per step, 120s total), then allocate retry budget within that ceiling. Cordum's rule: "Deadline first, retries second." Every retry attempt spends time, queue capacity, and dependency headroom — if you don't pre-define the ceiling, retries will spend it all and then some.

- **Use circuit breakers, not backoff.** Backoff delays wasted calls; circuit breakers prevent them entirely. Wrap each external tool (search API, code executor, web scraper) in a per-tool three-state machine: CLOSED (normal), OPEN (fail-fast after N failures), HALF-OPEN (probe whether the tool recovered). AgentFuse and the agent-patterns.ai circuit breaker pattern both implement this. When a tool is OPEN, the agent should fail the step immediately rather than retry into a degraded dependency.

- **Measure loop convergence, don't cap iterations.** LoopGain (loopgain-ai) replaces `max_iterations=N` with a control-theory approach: measure the ratio of current error to previous error (loop gain, Aβ). If Aβ > 1, the agent is degrading — roll back to the best-so-far state and exit. In 2,000 paired trials, this cut API spend by 92.8% versus a fixed cap of 20 iterations ($27.05 → $1.94) and was 15× faster wall-clock.

- **Detect loops at multiple granularities.** LoopBuster uses three complementary signals: fuzzy string similarity (catches repeated tool arguments), state stasis detection (catches unchanged working memory across steps), and cycle detection (catches A→B→C→A patterns). No single detector catches all loops — embedding-based similarity misses fuzzy variants, string matching misses semantic cycles.

- **Build a fallback chain, not a single dependency.** For any AI-dependent feature, define an ordered sequence: primary LLM → cached result (with TTL) → smaller/faster model → rule-based heuristic. Cordum documents a 4-level fallback chain for search. Each level should be independently monitored — if the primary fails 20% of the time, the fallback chain is already stressed before you hit it.

- **Timeout every external call with explicit budget allocation.** Cordum applies two safety timeout layers: a 2s inner guard in the SafetyClient and a 3s outer guard in the scheduler engine. Agentfuse caps at the session level (e.g., $5/hour per agent). The BSWEN blog notes that in CrewAI, the default agent has no timeout — a hanging first agent blocks all downstream agents in a pipeline, cascading the failure across the entire crew.

## Evidence

- **HN Discussion (475 pts):** "12-factor Agents" — Dex (@dexhorthy) documents that most production agents are "not all that agentic" — they are well-engineered software with LLMs at key decision points. Key principle: wrap every external call in a timeout, and every tool in a circuit breaker. — [HN Thread](https://news.ycombinator.com/item?id=43699271) · [Repo](https://github.com/humanlayer/12-factor-agents)

- **GitHub / Benchmark:** LoopGain open-sourced 2,000-paired trial results showing 92.8% cost reduction over fixed iteration caps using loop-gain convergence detection. Supports LangGraph, CrewAI, AutoGen, and Claude Agent SDK adapters. — [LoopGain Repo](https://github.com/loopgain-ai/loopgain) · [HN Thread (31 pts)](https://news.ycombinator.com/item?id=48919562)

- **ArXiv / Research:** "When Agents Do Not Stop" (arXiv:2607.01641) formally defines Infinite Agentic Loops (IALs) as structural execution failures arising from feedback paths without effective termination bounds. Proposes IAL-Scan, a static analysis tool for framework-aware IAL detection across agent frameworks. — [arXiv](https://arxiv.org/html/2607.01641v1)

## Gotchas

- Setting `max_iterations` doesn't prevent the last bad iteration from being shipped as output — the loop stops, but at the worst possible moment. You need best-so-far rollback, not just iteration caps.
- Exponential backoff without jitter causes synchronized herd effects: when a provider recovers, all backed-off clients retry simultaneously and re-trigger the rate limit.
- A single agent timeout blocking a multi-agent pipeline is a silent killer — instrument every agent boundary with its own timeout so cascading hangs are visible, not invisible.
- Loop detection purely by string matching misses semantically identical actions with different surface text. Use state-based or embedding-based similarity as a complement.
- Budget enforcement at the session level (e.g., $5/hour) doesn't prevent a single expensive call within the budget. You need per-step and per-call budget guards, not just session-level caps.
