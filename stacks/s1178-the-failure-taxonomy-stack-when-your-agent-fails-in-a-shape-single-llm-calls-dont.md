# S-1178 · The Failure Taxonomy Stack

When your agent loops for 35 minutes making identical failing tool calls, silently degrades for days, or takes an irreversible action before a human can intervene — standard try/catch isn't the tool for the job.

## Forces

- **Agents fail in shapes single-LLM calls don't.** A conventional API crashes and logs a stack trace. An agent may silently loop, spawn redundant subprocesses, accumulate context until the model halts, or take an irreversible action before you notice.
- **Error propagation cascades.** A single failure in one module — planning, memory, or action — cascades through the entire agent. Error handling cannot be modular when the modules share probabilistic reasoning.
- **The worst failures arrive with HTTP 200.** A plausible-but-wrong answer looks identical to a good answer in logs. Code-level exception handling misses semantic failures entirely.
- **Retry storms burn budgets silently.** Naive retry without backoff amplifies load, worsens rate limits, and can run up $437 in API bills overnight without a single alert firing.

## The Move

Layer defenses at four levels — stops, retries, isolation, escalation — and classify failures at each level so the response matches the failure type.

### Hard Stops (always first)

- **Step cap:** Stop after N turns regardless of outcome. `MAX_STEPS = 12` in LangGraph's `recursion_limit`, or a for-loop guard. If the agent hasn't finished in N steps, stop, document, escalate.
- **Cost circuit breaker:** If a single trace exceeds a cost or turn-count threshold, halt and hand off to a human. One developer woke to a $437 overnight bill from a retry loop running 8 hours.
- **Validation gate:** After any tool call, verify the response structure before passing it back to the model. A tool returning an error in a `success` wrapper fools naive error checks.

### Retries (with discrimination)

- **Transient failures → retry with exponential backoff + jitter:** Rate limits (429), server errors (503), brief timeouts. Base delay × 2^attempt + random jitter. 3–5 attempts max.
- **Persistent failures → do not retry:** Provider outage, exhausted quota, invalid API key. Retry amplifies the problem.
- **Bad input → correct, don't retry:** Malformed requests, content policy violations, context window exceeded. Modify the request or route differently — retrying unchanged fails identically.
- **Adaptive classifiers** can predict transient vs. permanent failure before retrying, reducing wasted API calls by up to 40% (2025 research).

### Isolation (circuit breakers)

- **Per-service circuit breakers:** If a dependency fails N times consecutively, stop calling it entirely. In distributed multi-agent systems, AWS recommends circuit breakers between agent clusters, not just individual connections, to contain fault propagation.
- **Fail-closed vs. fail-open policy:** Explicitly choose whether a tripped breaker returns an error or degrades gracefully. For high-risk actions, fail closed.
- **Supervisor pattern:** A lightweight parent agent monitors child agents, kills stalled subprocesses, and restarts from checkpoint. Used in AutoGen group chat and multi-agent orchestration systems.

### Escalation

- **Checkpoint-and-resume:** LangGraph's `MemorySaver` and persistent checkpointers let workflows resume from any node after failure. Treat checkpoint state as first-class, not an afterthought.
- **Human-in-the-loop for high-risk actions:** Irreversible operations (payments, deletions, external sends) require explicit human approval. Anthropic introduced circuit-breaker-style safety mechanisms that monitor agent behavior and identify high-risk actions before execution.
- **Severity classification:** P0/P1/P2 failure taxonomy tied to automated recovery policy — different recovery strategies for "web search timed out" vs. "agent is looping on auth error."

## Evidence

- **Research synthesis:** Specification failures account for ~42% of multi-agent failures; coordination breakdowns for ~37%. Multi-agent system failure rates range 41–86.7% across repeated runs. — [Zylos Research, 2026-05-06](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)
- **HN post-mortem:** A developer documented waking to a $437 overnight API bill from a nightly document-summarization agent that entered a retry loop at 11 PM and ran until 7 AM with zero alerts firing. The fix took 20 minutes. — [Waxell, 2026-05-01](https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern)
- **arXiv production framework:** Evaluating Agentic AI in the Wild (Pandey, 2026) identifies seven production-specific failure modes from billion-event-scale systems, including tool failure cascades, compounding decision errors, and non-deterministic output drift that existing lab benchmarks (HELM, MT-Bench, AgentBench) don't capture. — [arXiv:2605.01604](https://arxiv.org/abs/2605.01604)
- **Framework guidance:** LangGraph's recursion limit, AutoGen's custom termination conditions, and CrewAI's role-limited agents all provide first-class failure boundaries — but teams still ship agents without them. — [StackPulsar, 2026](https://stackpulsar.com/blog/ai-agent-reliability-monitoring/)
- **Show HN — autonomous recovery:** TensorPool Agent auto-recovers distributed training GPU jobs from checkpoints, with explicit progress health checks to prevent "silent stalls" where a zombie job appears running but is stuck. — [Hacker News, 2026-01-29](https://news.ycombinator.com/item?id=46812909)
- **GitHub triage tool:** `agent-triage` (converra) analyzes production agent traces to pinpoint the exact step, turn, and agent where a conversation broke, with multi-agent cascade analysis. — [GitHub converra/agent-triage](https://github.com/converra/agent-triage)

## Gotchas

- **Don't retry on everything.** Persistent failures (provider outage, bad auth) retry identically and amplify cost. Classify first.
- **Step caps without logging are black boxes.** When the agent hits MAX_STEPS and stops, you need the full trace to understand *why*. Instrument step counts, tool responses, and token usage per step.
- **Semantic failures are invisible to code.** The agent produces a confident, plausible-but-wrong answer. No exception is thrown. You need output validation (verifier agents, expected-schema checks) to catch these.
- **Distributed agents need circuit breakers between clusters, not just at the edge.** A failure in one agent can propagate silently through a shared orchestration layer before any single-service breaker trips.
- **Checkpoint state can itself be corrupted.** If you checkpoint an agent mid-failed-tool-call and resume without clearing that failure state, you reproduce the failure. Validate checkpoint integrity on resume.
