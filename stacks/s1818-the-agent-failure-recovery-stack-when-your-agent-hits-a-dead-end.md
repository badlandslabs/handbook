# S-1818 · The Agent Failure Recovery Stack — When Your Agent Hits a Dead End

Your agent worked fine in demos. Then production traffic arrived and it started looping, hallucinating parameters, hitting context limits silently, and crashing in ways that left users staring at a spinner with no explanation. Agents fail differently than regular software — failures are often subtle (correct HTTP 200, wrong answer) and cascade (tool #1 fails, agent continues with bad state, three more calls go off the rails). The discipline is not preventing all failures. It is making them recoverable.

## Forces

- **Agents fail at 41–86% rates in multi-step tasks** — even the best framework still fails 4 out of 10 times (MAST Taxonomy, Berkeley/Stanford, March 2025). This is not a model problem; it is a systems problem.
- **86% of agent failures are recoverable** — but only if you build the recovery paths. Without them, a recoverable failure becomes a dead end (Gartner via The Operator Collective, March 2026).
- **Endpoint accuracy hides trajectory quality** — an agent can reach the right answer through a wrong path, or fail silently through a cascade of small errors.
- **Most failure is invisible** — 67.6% of tokens in agent traces come from tool responses, not the model. The real failure surface is tool interactions, not prompts (Braintrust, 2025).

## The Move

Build failure recovery as a first-class architectural layer, not an afterthought. The approach has four distinct recovery domains, each requiring a different mechanism:

### 1. Classify the failure type before choosing a response

| Failure Domain | Examples | Recovery |
|---|---|---|
| **Transient transport** | 429 rate limit, 503 outage, timeout, network blip | Retry with exponential backoff |
| **Output validation** | Model returns text instead of JSON, missing required fields | Re-prompt with exact error; do not retry blindly |
| **Semantic** | HTTP 200, factually wrong answer | LLM-as-judge validator catches this; human escalation if validator fails |
| **State loss** | Process crash, context overflow | Checkpointer restores from last good state |

Mixing these up is why "add retries" never solves the problem. Never retry a 401 without re-authenticating first; never retry a 400 without fixing the parameters.

### 2. Treat every LLM call as a network call that can fail — design the contract before the first tool

- Define a retry budget per tool (e.g., 3 retries with jitter for transients, 0 for auth errors)
- Attach a checkpointer to every agent loop — save state after each successful tool call
- Never let a tool call modify global state before returning; keep state changes behind transactional boundaries

### 3. Build a hardcoded graceful degradation ladder, not a prompted one

1. **Retry briefly** if the failure is genuinely transient
2. **Switch to a compatible fallback model** if the contract can stay the same
3. **Reduce scope** — simplify the task (drop one tool, narrow the query)
4. **Partial response** — return what you have with a clear explanation of what failed
5. **Honest failure** — state explicitly what went wrong, what was not attempted, and what a human should do next

Prompting your way into graceful behavior fails at the first real outage. The ladder must be explicit in code, not in the system prompt.

### 4. Catch context overflow before it becomes silent misbehavior

Long-running agents hit context window limits at the worst moment — 50 steps into a complex task. The solution: a middleware layer that catches overflow, summarizes and truncates conversation history, then replays the last user request against the condensed state. Do not let the model keep running in a near-full context — it produces confident nonsense without throwing an error.

### 5. Assign per-tool recovery strategies, not global ones

Each tool has different failure modes. A search API might need a fallback to a cached result; a code execution tool might need a sandbox kill-switch; a database tool might need transactional rollback. Define recovery per tool interface.

### 6. Add step budgets and loop detectors

Infinite loops are the most common silent failure mode. Set a maximum step count per session (50 is a reasonable starting point for research agents). Track whether the agent is producing new information or cycling — if the last N tool responses are semantically similar, trigger a loop exit.

## Evidence

- **MAST Taxonomy (Berkeley/Stanford, March 2025):** Analyzed 1,642 agent execution traces across seven multi-agent frameworks. Failure rates ranged from 41% to 86.7%. Even the best-performing framework failed 4 out of 10 multi-step tasks. — [arXiv:2503.09528](https://arxiv.org/abs/2503.09528)
- **Agentic Reliability Framework (ARF):** Open-source production system using three specialized AI agents — Detective (anomaly detection via FAISS), Diagnostician (root cause analysis), and Predictive (failure forecasting). Achieves 2-minute MTTR versus 45-minute manual recovery, with 15–30% revenue recovery on incidents. Built after observing companies losing $50K–$250K per incident. — [GitHub: petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **Braintrust agent trace analysis (2025):** Agent trace spans average 50KB each (vs ~900 bytes for standard LLM calls). Sessions can generate over 10GB of trace data. 67.6% of all tokens in agent traces come from tool responses — the failure surface is tool interactions, not prompts. — [Braintrust blog](https://www.buildingagents.dev/posts/agentic-ai-production-benchmarks)
- **Harsh Rastogi, Modelia.ai (March 2026):** Image generation pipeline agent approved obviously flawed images because it optimized for completing the workflow, not quality. Five failure modes identified: tool parameter hallucination (fabricated IDs, wrong formats), infinite loops, context overflow, goal drift, and cost explosion. — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Galileo (2025):** Failure distribution in multi-agent systems — 42% specification failures, 37% coordination breakdowns, 21% verification gaps. — [The Operator Collective](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)

## Gotchas

- **Do not retry blindly.** A 401 with the same credentials is a 401 forever. A 400 with wrong parameters is a 400 forever. Classify before you retry.
- **Context overflow is silent.** The agent does not crash — it starts producing plausible but disconnected outputs. Build overflow detection, not just overflow handling.
- **Self-correction is a retry with a better error message.** The validator should tell the model exactly what was wrong, not just "try again." Include the validation error text in the re-prompt.
- **Recovery latency compounds.** A 30-second timeout × 3 retries × 5 failing tools = 7.5 minutes of wasted API spend. Set per-step timeouts and kill switches.
- **86% recoverable does not mean 86% recovered.** The difference is whether you built the recovery path. Without it, recoverable failures become canceled projects (Gartner: 40%+ of agentic AI projects cancelled by end of 2027).
