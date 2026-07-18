# S-1297 · The Reliability Arithmetic Problem — When Your "Reliable" Agent System Only Works 20% of the Time

A 10-step agent pipeline where each step succeeds 90% of the time delivers reliable output 35% of the time. A 10-step pipeline where each step succeeds 85% of the time — which feels respectable in isolation — delivers reliable output only 20% of the time. Most teams discover this arithmetic only after the first $47,000 incident.

## Forces

- **Reliability compounds inversely.** Every agentic workflow is a pipeline of probabilistic steps. Traditional software reliability assumes independent, near-certain steps. Agent steps have independent probabilities that multiply. Teams that build a 7-step pipeline where each step feels "mostly reliable" often ship a system that works end-to-end less than half the time.
- **Partial success is invisible at the dashboard level.** HTTP 200 means the LLM responded. It does not mean the pipeline completed. Multi-agent systems with shared state and no coordination layer can accumulate partial states — tasks claimed, resources reserved, calls made — without any agent knowing the full picture.
- **Failure isolation is non-obvious.** When a sub-agent times out mid-pipeline, you don't get an exception — you get partial state. The caller gives up, the sub-agent keeps running, and both sides believe the other handled it. Recovering cleanly requires architecture designed before the incident.
- **The 85% step reliability is a fiction.** Edge cases break "reliable" steps: null values, Unicode names (O'Brien, 北京), empty fields, concurrent requests, rate limit responses. Each of these collapses the per-step reliability estimate retroactively.

## The Move

Model your pipeline reliability explicitly. Treat it as a reliability budget, not a feature.

**1. Compute the compounding failure rate up front.** A 10-step pipeline with 85% per-step reliability has 0.85^10 ≈ 20% end-to-end reliability. Before you ship, run this math. If the result is unacceptable, reduce steps, increase per-step reliability, or add checkpoints that allow partial results to be salvaged.

**2. Design checkpoints at natural boundaries.** Write intermediate state to durable storage after each major step — not as part of the agent's reasoning, but as a side-effect of the pipeline controller. When a step fails, the controller can resume from the last checkpoint rather than from scratch. This converts a full pipeline retry into a step retry.

**3. Make every step idempotent and every output parseable.** An idempotent step can be safely retried without side effects. A parseable output can be validated before the next step receives it. Non-deterministic outputs that look like valid JSON but aren't are a primary cause of cascade failure — the next step receives what appears to be a result and acts on it.

**4. Implement a circuit breaker on the pipeline level.** When a step fails N times in a row, the pipeline enters a paused state rather than continuing to spend budget on a degraded system. Three-state machines (closed → open → half-open) adapted from distributed systems are the standard pattern. For AI services specifically, monitor for cost accumulation during outages — runaway loops can generate thousands of dollars in API calls before a human notices.

**5. Route to a human reviewer at defined failure thresholds.** When the pipeline confidence drops below a threshold — e.g., a step retried twice, or a tool call returned an unexpected error type — escalate rather than continuing. This is the agentic equivalent of a circuit breaker combined with a dead man's switch.

**6. Treat partial outputs as first-class artifacts.** When a sub-agent produces a partial output (timeout, truncation, error-in-text that looks like success), the pipeline controller must decide: retry, skip, degrade gracefully, or escalate. Build this decision tree explicitly. Don't leave it to the orchestrator's judgment at 2 AM.

## Evidence

- **Gartner (2025):** Over 40% of AI agent projects will fail by 2027. The primary cited reason is not model capability — it's system reliability and integration failure.
  — Gartner AI Adoption Survey 2025, via [Towards AI production guide](https://pub.towardsai.net/building-production-grade-ai-agents-in-2025-the-complete-technical-guide-9f02eff84ea2)

- **ARF (Agentic Reliability Framework) — Show HN:** Built by a former NetApp reliability engineer after observing 60+ critical incidents per month. ARF uses three specialized agents (Detective, Diagnostician, Predictive) with FAISS vector memory for anomaly detection. Result: 2-minute MTTR versus 45-minute manual recovery, 15–30% revenue recovery per incident.
  — [Show HN: Agentic Reliability Framework](https://news.ycombinator.com/item?id=46207273)

- **Real incident (January 2026):** A multi-agent pipeline processing refunds processed a $47,000 fraudulent transaction via prompt injection. Root cause: four agents in one shared workflow, no shared memory, no global state, no guardrails between them. Each agent performed its narrow task correctly. The system as a whole was wrong.
  — Abhishek, via [Reddit r/OpenAI discussion](https://www.reddit.com/r/OpenAI/comments/1iksf40/ai_agents_are_booming_in_2025/)

- **Microsoft (2025):** Six failure categories unique to AI agents: tool misuse, context poisoning, goal drift, cascade failure, resource exhaustion, and silent corruption. The cascade failure category maps directly to compounding reliability arithmetic.
  — [Zylos Research synthesis](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery), citing Microsoft 2025 whitepaper

- **AI Codex / production engineering consensus:** Five failure modes that actually happen in production: timeout mid-pipeline, partial output (truncated JSON or error-in-text masquerading as success), cascading failure (orchestrator doesn't know what to do with remaining sub-agents), silent degradation (low-quality outputs that pass validation but are wrong), and state corruption (shared state modified in incompatible ways by concurrent agents).
  — [AI Codex: Multi-agent failure handling](https://www.aicodex.to/articles/multi-agent-failure-handling)

## Gotchas

- **Adding more agents improves capability but multiplies the failure surface.** A pipeline that adds a "reviewer agent" to catch errors also adds two more failure points. The reviewer can fail, or it can approve something the primary agent got wrong.
- **Retry logic without idempotency makes things worse.** Retrying a non-idempotent step (e.g., "send email", "charge card") on timeout doesn't recover — it double-executes. Every tool call that has side effects must be idempotent by design (e.g., idempotency keys on API calls), or the retry logic must verify state before re-executing.
- **Monitoring per-step latency and cost is more useful than monitoring end-to-end.** By the time you see end-to-end degradation, the pipeline has already failed multiple steps. Per-step cost anomalies (sudden 10x increase in API calls) often signal a loop before the loop completes.
