# S-2759 · The Silent Trajectory Failure Stack — When Your Agent Succeeds But Goes Nowhere

Your agent ran for 35 minutes, exited cleanly, and produced an answer that is subtly wrong. No exception. No crash. No signal that anything went wrong — until someone reads the output and notices the agent edited the same function six times, each iteration making it slightly worse. This is the failure mode that kills production agents: not a crash, but a trajectory that converges on nothing, burning tokens the whole way.

## Forces

- **Agents fail by completing, not by crashing.** A conventional service that breaks throws an exception. An agent that is going wrong keeps returning tool results, keep calling the LLM, keeps producing output — all of it invalid. The absence of a crash removes the natural forcing function that would otherwise surface the problem.
- **`max_iterations` is a blunt instrument, not a solution.** Setting `N` iterations either kills a loop too early (when it was still improving) or lets it spin indefinitely (when it passed its useful limit and kept going anyway). The cap is a budget knob, not a convergence signal.
- **Side effects compound under retry.** When an agent fails and retries without an idempotency guard, it re-runs steps that already succeeded — sending duplicate emails, placing duplicate charges, writing conflicting database rows. The failure was silent; the duplication is silent too.
- **There's no crash to surface the problem.** Logs look healthy. The agent is busy. The human who handed it a task is not watching every token. By the time someone notices, the agent has either produced wrong output, wasted significant compute, or committed irreversible side effects.

## The move

Layer five deterministic controls around the probabilistic model:

- **Replace `max_iterations` with loop-gain detection.** Instead of counting iterations, measure whether the loop is still improving. Compute the ratio of current error to previous error (the loop's empirical gain). Stop when gain ≥ 1 — the loop has converged or is degrading. LoopGain's benchmarks (2,000 paired trials) show 92.8% API spend reduction and ~15× speed improvement vs. fixed caps, with quality preserved on both natural and engineered-failure workloads.
- **Make every retryable side effect idempotent.** Before executing any operation that has already succeeded in a prior attempt (email send, database write, API call), check completion status via an idempotency key. A retry that re-runs a step that already succeeded is not a retry — it is a double-execution. This is not optional for agents with financial or communications side effects.
- **Checkpoint state at every boundary.** On crash, interrupt, or context overflow, the agent must resume from the last completed step, not restart from scratch. LangGraph's `checkpointer` and Microsoft Agent Framework's checkpoint/resume primitives handle this at the graph level.
- **Route failures to a verifier, not back to the same agent.** After a tool call error or malformed output, send the failure to a dedicated grading node — a smaller, faster model whose only job is to assess whether the output actually answers the query. If the verifier says no, trigger a self-correction loop with a specific error signal, not a blind retry.
- **Instrument trajectory observability.** Track: unique tool-call signature count (repeating the same call with the same args is a loop), state entropy (is the context growing without the answer improving?), and step-level cost. failproof and similar tools surface loops as call-count spikes with no progress delta — visible in traces, not in crash logs.

## Evidence

- **Open-source library with benchmark data:** LoopGain (loopgain-ai) — control-theoretic loop termination replacing `max_iterations`, adapters for LangGraph/CrewAI/AutoGen, 92.8% API cost reduction, ~15× speed improvement across 2,000 trials. Benchmarks published on GitHub README.
  — [GitHub: loopgain-ai/loopgain](https://github.com/loopgain-ai/loopgain)
- **HN discussion (284 points) on loop design:** Simon Willison's "Designing agentic loops" — HN consensus that agents fail by completing without improving, not by crashing; tool design as the primary lever; YOLO mode risks.
  — [HN: Designing agentic loops](https://news.ycombinator.com/item?id=45426680)
- **Show HN on loop detection (31 points):** LoopGain launch thread — real developer discussion of the `max_iterations` problem, loop-gain math, rollback-before-degradation pattern.
  — [HN: Show HN — LoopGain](https://news.ycombinator.com/item?id=48919562)
- **Real-world production failure:** Asynq.ai candidate evaluation agent — hallucinated tool parameters, contradicted own reasoning, cost 3× budget before explicit verification nodes + cost caps were added.
  — [Harsha Rastogi: Agentic AI in Production](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Framework-level checkpointing:** LangGraph persistence/checkpointing — canonical approach for crash-resilient agent state, referenced in Microsoft's agent system design guide.
  — [GitHub: ai-system-design-guide — Error Handling and Recovery](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

## Gotchas

- **Loop-gain measurement requires a quantifiable error signal.** For open-ended tasks where "error" is subjective, you need a proxy metric (e.g., cosine similarity to a reference answer, RAG relevance score) — this is non-trivial to define and calibrate.
- **Idempotency across service boundaries is a coordination problem.** If your agent calls three external APIs, each one needs to be idempotent-aware. Partial idempotency (only the first service has idempotency keys) still leaves the others exposed.
- **Checkpoint snapshots of LLM state grow with context length.** Long-running agents that checkpoint frequently will accumulate large state blobs. Prune or summarize intermediate checkpoints to avoid turning checkpoint storage into another bottleneck.
- **Self-correction loops have a budget problem.** An agent that self-corrects three times and fails again has burned 4× the cost of a single pass. Cap total correction attempts and escalate to human review when the budget is exhausted — otherwise resilience and runaway spend look identical from the outside.
- **The line between "still improving" and "compounding the mistake" is hard to draw in real time.** A verifier agent can catch semantic failures, but it cannot always tell whether a slightly different approach will succeed. Build in a hard cap on total attempts even when loop-gain signals suggest the loop is still running.
