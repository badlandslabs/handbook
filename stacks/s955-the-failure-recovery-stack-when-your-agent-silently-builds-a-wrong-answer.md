# S-955 · The Failure Recovery Stack — When Your Agent Silently Builds a Wrong Answer

The moment your agent returns a clean 200 OK after confidently routing a customer to the wrong department, sending a refund to the wrong account, and filing a ticket under the wrong priority — all without throwing a single exception — is the moment you understand why traditional try/catch does not cover agent failures. Agents fail softly, progress confidently, and cascade wrong conclusions across steps that each look fine in isolation. This is the failure recovery problem, and it is not a model quality problem — it is a systems engineering problem.

## Forces

- **Agents fail with 200 OK.** The LLM returns valid JSON. The API calls succeed. The pipeline continues. The answer is wrong. Traditional error handling assumes failures are loud; agentic systems fail quietly and the real error surfaces three steps later as a downstream symptom.
- **"One more step" is the default.** LLMs are trained to continue. They reason between every tool call. A task that should cost 500 tokens of actual work costs 5,000 because the agent keeps "refining." Hard caps exist but agents work around them by rephrasing the same action differently.
- **Recovery without state is impossible.** Multi-step agents complete steps 1–4 of 8, then fail. Without checkpoints, retrying means starting over and burning tokens. With checkpoints, you can resume from the failure point — but most production agents have neither.
- **Safety and autonomy are in tension.** Overly cautious guardrails make the agent useless. Under-cautious ones let it burn money, loop forever, or take irreversible actions. The threshold is domain-specific and often non-obvious.

## The Move

Classify failures by type and route each to the appropriate recovery mechanism. Layer guards from cheapest (hard caps) to most expensive (human escalation).

### Error taxonomy — five types, five responses

| Type | Example | Recovery |
|------|---------|----------|
| **Transient** | Rate limit (429), timeout, network hiccup | Retry with exponential backoff |
| **Persistent** | Auth expired, API key revoked, tool unavailable | Switch to fallback tool or model |
| **Semantic** | Valid JSON, wrong content, misclassified intent | Retry with explicit format correction in prompt |
| **Budget** | Cost ceiling or token limit hit | Pause, notify orchestrator, await top-up |
| **Fatal** | Unrecoverable state (e.g., corrupted checkpoint) | Mark task failed, return partial results + error receipt |

Source: Anthropic SDK Python Discussion #1341, GitHub — 2026

### Hard step caps with intervention, not just termination

The naive approach — `MAX_STEPS = 12, stop if not done` — loses all the work done so far. Better:

- **Step counting with soft intervention.** At 70% of cap, inject a summary into context: "You have N steps remaining. Consolidate your approach." This uses the LLM's own reasoning to redirect before the hard stop.
- **Cost circuit breakers.** At $X spent or N tokens consumed on a single task, stop regardless of step count. This prevents runaway loops that consume tokens without progress.
- **LangGraph `recursion_limit` + stateful checkpointing.** Checkpoint state at each step so retry resumes from the last good state, not from scratch.

Source: LLM Agent Error Recovery in 2026, blog.rajpoot.dev — May 2026

### Loop detection — track behavioral patterns, not just step counts

Step caps alone don't catch A→B→A→B loops where each step looks different. Two proven approaches:

- **Edit frequency tracking.** Track edits per file path per session. When the same file is edited N times without a passing test, flag as a micro-loop and inject a redirect prompt. LangChain credits this pattern with moving their agent from rank 30 to rank 5 on Terminal Bench 2.0 without changing the model.
- **Sequence matching with drift detection.** Detect A→B→A→B behavioral cycles in real-time via sequence matching on tool-call history. The `drift-detector-agent` library (MIT, <10ms per check) integrates as middleware with CrewAI and reports loop statistics to the orchestrator. KinthAI, running 221 production agents, uses loop detection as a core operational control.

Source: Loop Detection for AI Agents, agentpatterns.ai — 2026; Agent Loop Detection Middleware, crewAI GitHub Issue #4682 — April 2026

### Semantic validation — catch wrong answers before they cascade

Output validation catches syntax errors (malformed JSON, missing fields). Semantic validation catches the more dangerous case: the output is well-formed but wrong.

- **Content smoke tests.** After each tool call, run a lightweight LLM check: "Does this result actually answer the original question?" Reject and retry if the result is off-topic, contradictory, or below a confidence threshold.
- **Finalizer step.** Before returning, run the complete output through a "did I actually do what was asked?" check. This is where most hallucinated completions get caught.
- **Read-only verification.** For agents that browse, search, or read: verify the retrieved content actually contains the cited information before acting on it.

Source: Building Reliable AI Agents, tanujgarg.com — April 2026

### Escalation — explicit triggers, not vague confidence scores

"Hand off to a human when confidence is low" is not an escalation policy. Explicit triggers are:

- Two repair attempts failed on the same step
- Required fields missing after all available retrieval attempts
- Action touches money, permissions, or customer-facing sends
- Total runtime exceeds 90 seconds
- Cost or token budget breached
- Agent explicitly requests help (some frameworks surface this via a flag)

Source: AI Agent Fallback Strategy, iamstackwell.com — March 2026

## Evidence

- **Anthropic SDK Python Discussion #1341:** Production engineers classifying agent errors into five types (transient, budget, capability, semantic, fatal) with concrete recovery routing. Real pattern from teams running agents 24/7. — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **LangChain loop detection benchmark:** Edit-frequency tracking moved agent ranking from 30th to 5th on Terminal Bench 2.0 without model change. Quantifies the impact of loop detection as a reliability investment. — [agentpatterns.ai/observability/loop-detection](https://agentpatterns.ai/observability/loop-detection)
- **KinthAI production loop detection:** 221 agents running with drift detection as operational control. drift-detector-agent library with <10ms per check, MIT license. — [github.com/crewAIInc/crewAI/issues/4682](https://github.com/crewAIInc/crewAI/issues/4682)
- **AI Agents Blog: 5 Patterns for Production Reliability:** Checkpoint-and-resume, circuit breakers, escalation queues — all implemented with Anthropic SDK, working across orchestration frameworks. — [aiagentsblog.com/blog/agent-error-recovery-patterns](https://aiagentsblog.com/blog/agent-error-recovery-patterns)
- **I Am Stackwell — Fallback Strategy:** Four failure types with distinct responses; explicit escalation trigger rules (90s, cost breach, money touch). — [iamstackwell.com/posts/ai-agent-fallback-strategy](https://iamstackwell.com/posts/ai-agent-fallback-strategy)

## Gotchas

- **Step caps are necessary but not sufficient.** Agents can work around hard limits by rephrasing the same action. Pair with loop detection that tracks behavioral patterns, not just counts.
- **Retry without backoff is worse than no retry.** A retry loop that hits a rate limit immediately re-triggers that rate limit. Always add exponential backoff (1s, 2s, 4s, …) with jitter for transient failures.
- **Checkpointing at the wrong granularity wastes memory and misses failures.** Checkpoint after each successful tool execution, not after each LLM call. A tool execution is a meaningful unit of work; a reasoning step is not.
- **Silent failure is the default.** If your observability only surfaces exceptions, you will miss the 80% of agent failures that return 200 OK with wrong answers. You need step-level logging with output snapshots.
- **Escalation without context is useless.** When the agent escalates, include the original task, what was attempted, what succeeded, what failed, and the partial result. A human receiving "agent failed" cannot fix anything useful.
