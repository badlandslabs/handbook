# S-1792 · The Circuit Breaker Stack — When Your Agent Won't Stop Failing

The agent loops. The tool errored. The model retries the same failed call with the same bad arguments. You come back to find 47,000 tokens burned and nothing accomplished. This is the default state of an agent with no failure controls — and the fix is a set of circuit breaker patterns borrowed from distributed systems, adapted for LLM loops.

## Forces

- **Agents fail non-deterministically.** A prompt that works once fails the next time due to model drift, token limits, or hallucinated tool arguments. Traditional try-catch blocks are insufficient — the failure modes are behavioral, not code-level.
- **Loops compound silently.** LangGraph's checkpointing system persists loop state across invocations, causing memory growth and escalating costs. A stuck agent doesn't crash — it grinds until the context window fills or the bill does.
- **Context pressure makes failures worse.** As context fills, model reasoning quality degrades. A looping agent becomes progressively less capable of self-correcting — you need the brake before the window fills, not after.
- **Recovery from a dead state requires checkpoint history.** Resuming from a mid-crash state is only possible if checkpoints were being written. Teams that skip checkpointing lose the ability to resume cleanly.

## The Move

Build circuit breakers into the agent harness as first-class constraints. The circuit breaker pattern for agents has five distinct stopping signals, layered from weakest to hardest:

1. **Iteration limit (`max_iterations` / `max_turns`).** Hard cap on steps per run. OpenAI Agents SDK raises `MaxTurnsExceeded` at the boundary. LangChain exposes `max_iterations` with a warning that disabling it risks infinite loops. This is the floor — every agent needs it.
2. **Repeated failure detection.** Track N consecutive tool errors or validation failures. After threshold, break the loop rather than retry with the same approach. CrewAI's Loop Detection Middleware (GitHub #4682, filed March 2026) explicitly addresses this: agents in autonomous loops execute the same action sequences without making progress.
3. **Semantic loop detection.** Not just identical calls — detect when the agent is re-researching the same information, re-writing the same output, or re-attempting a task with no state change. Pattern-match against recent tool call signatures and their results. This catches the case where `max_iterations` hasn't fired but the agent is clearly stuck.
4. **Exponential backoff with jitter on retry.** When a tool fails transiently, retry with `delay = base * 2^attempt + random_jitter`. Cap the maximum delay and maximum retry count. LangGraph's `RetryPolicy` supports `max_attempts`, `initial_interval`, `backoff_factor`, and `jitter` — configured per node. Don't retry immediately; flakiness often resolves itself.
5. **Hard timeout at the harness level.** Wall-clock timeout independent of step count. A 60-second task that takes 10 minutes is a failure regardless of iteration count.

Below the breakers, add a **self-correction loop** for recoverable failures: the agent evaluates its own output against a validator node. If validation fails, it receives a graded error signal and re-attempts with different reasoning — not just the same prompt again. This is the self-correcting agent loop pattern, where explicit routing edges create state-machine-style retry with reflection rather than blind re-execution.

For state durability: use **checkpoint-based recovery** instead of stateless restart. LangGraph's checkpointing lets you `aget_state_history(thread_id)` and reconstruct the agent's trajectory. When the service crashes mid-run, resume from the last checkpoint without recomputing earlier steps. Production teams report that testing the resume path — kill the process, verify recovery to correct final state using the same `thread_id` — catches bugs that unit tests miss.

## Evidence

- **GitHub (agentpatterns-ai):** The circuit breaker pattern is catalogued as "adopted" maturity, with five distinct stopping signals defined. LangGraph's cycle detection in graph-based agent flows and `max_iter` parameter are referenced as the canonical baseline. — [agentpatterns-ai/website — Circuit Breakers for Agent Loops](https://github.com/agentpatterns-ai/website/blob/main/observability/circuit-breakers.md)
- **GitHub (crewAI #4682):** "Agents that run for extended periods (100+ iterations) inevitably encounter states where they repeat without progress — and without detection, they burn tokens and time." The feature request for a Loop Detection Middleware to detect and break repetitive behavioral patterns in autonomous agents with `allow_delegation=True` was filed March 2026 and closed completed. — [crewAIInc/crewAI #4682](https://github.com/crewAIInc/crewAI/issues/4682)
- **Coasty Blog / industry survey (Kore.ai, June 2026):** 72% of enterprises say their AI agents operate with unmanaged risk; 40% of enterprises have seen a single agent failure cascade across multiple systems; production agent failure rates run 70–95% (Fiddler AI). — [Coasty Blog — AI Agent Error Handling Crisis (May 2026)](https://coasty.ai/blog/ai-agent-error-handling-recovery-2025-20260505)
- **LangGraph docs:** `RetryPolicy` configuration with `max_attempts`, `initial_interval`, `backoff_factor`, `jitter` — attached per node. Checkpointing enables recovery from interrupts, timeouts, and service restarts by resuming from the last saved state. — [LangGraph Error Handling and Retry Policies](https://deepwiki.com/langchain-ai/langgraph/3.8-error-handling-and-retry-policies)
- **AI System Design Guide:** Taxonomy of agent failures includes hallucinated tools, tool errors, permission gaps, and workflow drift. Error handling has shifted from try-catch to agentic self-correction and stateful rollbacks. — [ai-system-design-guide — Error Handling and Recovery (Dec 2025)](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

## Gotchas

- **Disabling `max_iterations` "just for testing" is how demos become incidents.** One disabled guard in a long-running agent creates unbounded risk. Keep limits in production; lower them if they fire too often, but never remove them.
- **Checkpointing without retention policies causes unbounded storage growth.** Purge completed threads older than your audit window. The checkpoint table grows indefinitely if you don't manage it.
- **A retry loop that re-executes the exact same failing prompt is not error handling — it's token burning.** The retry must carry different context: a graded error signal, changed parameters, or a different tool choice. Blind retry amplifies cost without improving outcome.
- **Tool result hallucination is a failure mode that circuit breakers don't address.** An agent can call a tool, receive a hallucinated response (from a misbehaving tool or a simulated result), and proceed confidently on bad data. Validators and ground-truth checks are a separate layer from loop detection.
