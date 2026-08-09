# S-2383 · The Failure Handling Stack

Your agent hits a rate limit, retries 30 times, burns $80, and returns nothing. It enters a tool-call loop clicking the same button. Its context overflows mid-session and starts dropping earlier constraints. The model is down and it surfaces a cryptic error instead of falling back. These are all the same underlying problem: the system has no structured response to failure. This is the failure handling stack — the layered resilience architecture that production agents need before they hit production.

## Forces

- **LLM failures are probabilistic, not deterministic.** A rate-limit 429 is not a NullPointerException — it has a recovery path. An LLM that returns valid JSON with a semantically wrong tool call won't throw any exception at all. Traditional try/catch covers neither.
- **A single agent step involves 5-6 failure points.** Intent parsing, vector retrieval, external API call, LLM inference, response validation, output formatting. Cascading failures across this chain can amplify a brief outage into a token-budget hemorrhage.
- **Agents fail in ways that look like progress.** A loop that re-phrases the same wrong conclusion every turn is syntactically fine. Loop detection cannot rely on error codes.
- **Fixing failures requires knowing which kind you have.** Retrying a fatal auth failure wastes resources. Re-prompting a transient timeout wastes time. The taxonomy determines the response.

## The Move

Layer four distinct failure-handling mechanisms, ordered by specificity:

**1. Taxonomy before response.** Classify every failure on receipt:
- **Transient** — rate limit (429), timeout, DNS, 503. Retry with backoff.
- **Semantic** — valid JSON but wrong tool, malformed arguments, schema violation. Re-prompt with corrective context.
- **Resource** — token budget exceeded, context overflow, cost cap hit. Summarize and compact or reduce payload.
- **Fatal** — auth failure, revoked API key, policy violation. Abort immediately, log, escalate to human.

This taxonomy (Neel Mishra's framework, 2025) maps error types to recovery strategies. Without it, teams apply the same blunt retry logic to every failure.

**2. Hard guards before retries.** Don't rely on retries to stop loops — set pre-conditions:
- **Budget ceiling** — hard cap on total spend per run (e.g., $2.00). Monitor token growth: linear is expected, quadratic means the full conversation is being re-sent each turn.
- **Wall-clock timeout** — 300s cap per run. Catches hung tools, slow networks, long model responses.
- **LoopBuster-style state stasis guard** — detect ExactRepeat (same output twice), FuzzyRepeat (similar output), CycleDetection (oscillation between states), and OutputStagnation (no progress signal over N turns). Tighten or relax thresholds based on action diversity.

**3. Control-theoretic loop termination instead of max_iterations.** Fixed iteration caps fail in both directions — too low clips still-improving loops, too high wastes budget after convergence. LoopGain (Show HN, 2025) replaces `max_iterations=N` with real-time loop-gain measurement using the Barkhausen criterion: classify `E(n)/E(n-1)` ratio. Benchmark on 2,000 paired trials across 10 workload cells: 92.8% API spend reduction ($27.05 → $1.94), ~15× speedup (30.9s → 2.1s median), quality preserved (judge win-rate 0.50–0.95 across workloads).

**4. Fallback chains over hard failures.** Route to progressively simpler handlers on persistent failure:
- Primary model → secondary model → cached knowledge-base query → template response
- Tool call fails → summarize partial results → return what exists
- Circuit breaker between agents: orchestrator tracks sub-agent failure rate; after 3 failures in 5 minutes, route to fallback rather than continuing to dispatch.

**5. Grounded self-correction, not intrinsic self-correction.** Reflexion-style verbal self-critique (stored in memory, retry with context) achieves 91% pass@1 on HumanEval but breaks down on reasoning errors — LLMs cannot reliably correct their own reasoning without external signals. The fix: anchor corrections in execution traces (`TypeError at line 14: unsupported operand type`) or verifier agents, not in the model's own confidence. Use a separate, smaller verifier model to check tool outputs before accepting them.

**6. Deterministic human escalation signals, not sentiment.** Route to human on four deterministic triggers (Zylos, 2025):
1. Fatal error detected (auth failure, policy violation)
2. Resource exhaustion after all recovery attempts
3. Confidence threshold breached on high-stakes action
4. N failed recovery cycles reached
Do not route on "agent seems uncertain" — sentiment is not a reliable signal.

## Evidence

- **GitHub repo + Show HN:** LoopGain — open-source control-theoretic loop terminator. Benchmarks: 2,000 paired trials, 92.8% spend reduction, 15× speedup, zero quality degradation. Adapters for LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents, Claude Agent SDK. — [https://github.com/loopgain-ai/loopgain](https://github.com/loopgain-ai/loopgain) + [https://news.ycombinator.com/item?id=48919562](https://news.ycombinator.com/item?id=48919562)
- **GitHub repo:** LoopBuster — framework-agnostic anti-dead-loop toolkit. 93 stars. Detection: ExactRepeat, FuzzyRepeat, CycleDetection, OutputStagnation. Guards: BudgetCeiling, RepeatCallGuard, StateStasis. Circuit breaker with pre-flight checks. Async support with hung coroutine detection. — [https://github.com/liuchunwei732-cmyk/loopbuster](https://github.com/liuchunwei732-cmyk/loopbuster)
- **Blog post (2025):** Agent Error Handling taxonomy — four error types mapped to recovery strategies. Core insight: "Production agents need layered error handling: retries for transient failures, fallbacks for persistent ones, circuit breakers for cascading failures, and validation for semantic errors." — [https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Research article (2025–2026):** Graceful Degradation Patterns — LLM failures are probabilistic not deterministic; tiered context architecture (anchored vs compactable); circuit breakers between agents in orchestrator/worker architectures. — [https://zylos.ai/en/research/2026-05-30-graceful-degradation-patterns-ai-agent-systems](https://zylos.ai/en/research/2026-05-30-graceful-degradation-patterns-ai-agent-systems)
- **Research article (2025–2026):** Agent Self-Correction — Reflexion achieves 91% pass@1 on HumanEval but fails on reasoning errors without external signals; grounded self-correction outperforms intrinsic. — [https://zylos.ai/en/research/2026-05-12-agent-self-correction-reflexion-to-prm/](https://zylos.ai/en/research/2026-05-12-agent-self-correction-reflexion-to-prm/)

## Gotchas

- **Verifying tool outputs with the same model that generated them is circular.** The model's confidence in a wrong answer doesn't decrease on reflection. Use a separate verifier grounded in execution traces, or accept that self-correction only works for concrete execution errors (TypeErrors, API rejections), not reasoning errors.
- **Retrying on transient errors without exponential backoff creates thundering herds.** A 429 that clears in 5 seconds will be re-triggered immediately if you retry without backing off. Apply jitter + exponential delay.
- **Context overflow mid-session drops early-session constraints.** The original task definition, user preferences stated once, and constraints established in turn 1 are the most likely casualties. Use a tiered context architecture: anchored context (never compacted) vs. compactable working context.
- **max_iterations is not a loop detector — it's a budget cap with side effects.** It stops at N regardless of whether the loop was still improving. If you're using it to prevent infinite loops, you're using the wrong tool.
- **Circuit breakers need reset logic.** A circuit that stays open forever never recovers. Implement half-open state (test with one request before fully reopening) and time-based reset.
