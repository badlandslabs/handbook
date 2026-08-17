# S-2766 · The Convergent Recovery Stack — When Your Agent Keeps Trying After It Already Won

Your agent has the right answer. It found it at iteration 6. Then it ran 14 more times, degrading the output, burning $47 in API calls, and finally returned a worse result than it had already produced. Nobody noticed because the system only checks the final output. This is the convergent-recovery problem: agents that lack the structural machinery to detect when they've succeeded and stop.

## Forces

- **max_iterations is a blunt instrument, not a solution.** A high cap wastes compute after convergence. A low cap clips loops that are still improving. Neither position is right — the agent needs to know when to stop based on whether it is making progress, not a fixed counter.
- **The model can't see its own pattern from inside the loop.** Each turn is dominated by the most recent error or result. The signal that would detect a loop — repetition across turns — is not visible to the model at decision time. The thing that detects loops is not the model reasoning inside the loop. It is a watcher outside the loop, counting.
- **Errors cascade, and each recovery layer has its own cost.** Tool calls fail 3–15% per call in production (paperclipped.de, 2026). An 8-step workflow with 5% per-call failure has a 34% chance something breaks. Retry, circuit-break, replan, and rollback each carry different token costs, latency, and risk of causing the next failure.
- **The final output is not the best output.** In iterative agent loops (code generation, research synthesis, multi-draft writing), the output often peaks before the final iteration. Returning the last output means returning a degraded one.

## The move

Build a three-layer recovery infrastructure around the agent loop: **detect** loop states from outside the model, **classify** the failure mode, and **act** with the cheapest sufficient response.

**Layer 1 — Loop-gain detection (outside the model).** Measure error or a proxy signal at each iteration. Calculate the loop gain: `Aβ = E(n) / E(n-1)`. When Aβ < 1, the loop is improving. When Aβ ≥ 1, it is stalling or diverging. This replaces `max_iterations = N` with a convergence signal the system acts on directly. (LoopGain, GitHub, 2026 — 92.8% API spend reduction vs. fixed cap in 2,000 paired trials, 15× median speed improvement.)

**Layer 2 — Trajectory classification.** Feed recent Aβ values into a classifier that labels the loop state: `FAST_CONVERGE | CONVERGING | STALLING | OSCILLATING | DIVERGING`. Each state maps to an action. STALLING or DIVERGING triggers rollback to the lowest-error output produced so far — not the final (degraded) one.

**Layer 3 — Failure-mode-specific recovery (inside the model).** Three structural failure modes drive most agent failures:

1. **Retry without backoff** — tool fails, agent retries immediately, fails again, infinite loop. Fix: classify the error. Idempotent failures (network timeout, 503) → retry with exponential backoff. Semantic failures (wrong tool, bad schema) → don't retry the same action; re-route or break.
2. **Undetected task completion** — agent finishes but doesn't recognize success. Fix: explicit success-condition checks in the reflection step of the observe-plan-act-reflect loop. If the goal is satisfied, exit immediately regardless of iteration count.
3. **Dependency deadlock** — agent waits on a subtask that is itself waiting. Fix: timeouts on all await operations; propagate partial results rather than blocking indefinitely.

**Layer 4 — Structured output validation with self-correction.** Use Pydantic models or JSON schema to validate tool outputs and model responses. On validation failure, the system automatically retries the same step with a corrected prompt — not a full replan. This catches the most common "succeeds technically, fails semantically" class of silent failures.

**Layer 5 — Fallback chains and graceful degradation.** For critical capabilities, maintain a fallback stack: primary tool → secondary tool → rule-based heuristic → human notification. Never let a single failure mode return a hard error to the user when a degraded response is possible.

## Evidence

- **GitHub + HN:** LoopGain — open-source library replacing `max_iterations` with real-time loop-gain (Aβ) convergence detection and best-so-far rollback. Adapters for LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Claude Agent SDK. Benchmarked: 92.8% less API spend vs. fixed cap, 0.92–0.95 judge win-rate preserved on engineered tasks. — [LoopGain GitHub](https://github.com/loopgain-ai/loopgain) · [HN Show](https://news.ycombinator.com/item?id=48919562)
- **Blog post / research:** "Why Most AI Agents Fail in Production" — three structural failure modes (retry without backoff, undetected completion, dependency deadlock) consistently observed across real deployments. Tool calling failure rate 3–15% per call; cascading to 34%+ failure probability in 8-step workflows. — [zealx / AI](https://zhaoyiming.top/posts/ai-agent-failure-modes-production-2026/) (2026)
- **Blog post:** "AI Agent Stuck in a Loop" — the structural reason loops are inevitable: each model turn is dominated by the most recent error; the model cannot see repeated attempts across turns. Observability pattern: detect loops as a spike in call count with no matching progress signal. — [failproof.ai](https://befailproof.ai/agent-stuck-in-a-loop/)
- **Blog post:** Agent reliability engineering — retry at the step level (smallest retriable unit), not the agent level; enforce idempotency for any step with side effects; circuit breakers with per-tool failure thresholds (critical tools trip on first failure). — [Let's Build](https://letsbuildsolutions.com/blog/ai-ml/ai-agent-reliability-engineering-retry-semantics-fallback-chains-and-graceful-degradation/) (March 2026)
- **Hugging Face paper:** Graph-based self-healing tool routing — hybrid approach using graph algorithms for routine recovery decisions, LLM only for novel reasoning. Reduces control-plane LLM calls by 93% (9 vs. 123 aggregate across 19 scenarios) while matching ReAct correctness. — [Hugging Face Papers](https://huggingface.co/papers/2603.01548)

## Gotchas

- **Naive retry wastes the most expensive resource.** Re-sending full conversation history re-runs all prior reasoning and pushes you closer to context limits. Cache the conversation state at each step; retry with a truncated context that includes only the failed step's inputs.
- **Rollback is counterintuitive to implement but essential.** The natural instinct is to return the last output. In iterative loops, the last output is often the worst. You need to track the best-so-far output separately and return it when the loop degrades.
- **Per-call circuit breakers trip too aggressively if you treat all failures equally.** Rate-limit 429s and timeout 504s are transient and retryable. Schema mismatches and permission errors are not — retrying them wastes a call and risks an infinite loop of a different shape.
- **Fallback chains must be tested under failure conditions, not success conditions.** The secondary tool often has different input formats, different error codes, and different latency profiles. The chain needs failure-mode simulation to verify it actually degrades gracefully rather than failing at the fallback step.
