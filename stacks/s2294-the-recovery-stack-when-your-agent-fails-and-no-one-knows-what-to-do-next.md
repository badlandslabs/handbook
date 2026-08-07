# S-2294 · The Recovery Stack — When Your Agent Fails and No One Knows What to Do Next

Your agent is 6 steps into a 10-step workflow. The external API returns a 503. Your retry logic fires 3 times and exhausts itself. The agent receives no signal that anything went wrong — it continues as if nothing happened, producing output that is confident, plausible, and completely disconnected from what actually succeeded. This is the failure handling gap: agents that fail silently, recover blindly, or loop indefinitely with no one watching.

## Forces

- **Agents fail categorically differently than traditional software.** HTTP 500s and timeouts are the easy cases. The hard ones: tool calls that return HTTP 200 with hallucinated data, reasoning chains that produce confident nonsense, and cascading errors where a bad step pollutes every subsequent step. Traditional try-catch blocks handle none of this.
- **Error detection and error recovery are separate problems.** Knowing something went wrong (detection) is not the same as knowing what to do about it (recovery). Most agent frameworks conflate them or skip recovery entirely.
- **The cost of the wrong recovery is asymmetric.** Retry loops on rate-limited APIs can generate $83 OpenAI bills from a single agent run (Reddit r/AI_Agents, 2025). Failing to rollback a bad filesystem write can corrupt state. The wrong recovery action is often worse than no recovery at all.
- **State is distributed across steps and tools.** A 10-step agent accumulates intermediate state across the conversation, tool outputs, and external systems. A crash at step 7 means you need the outputs of steps 1–6 to resume — not just the current prompt.

## The Move

The recovery stack has four layers, each handling a distinct failure class. Layer by layer:

1. **Classify before acting.** Every failure gets categorized before recovery logic runs. Transient errors (network timeout, 429, 503) → retry with backoff. Validation errors (bad API key, malformed request, 4xx) → fail fast, no retry. Semantic errors (tool returned technically valid output that is wrong) → this is the hard case, handled by layer 3. Unknown errors → circuit breaker.

2. **Two-layer defense: orchestration vs. LLM.** The orchestration layer handles silent, infrastructure-level retries for transient failures — the LLM never knows these happened. The LLM layer handles application-level recovery that requires behavioral change: switching tools, re-phrasing a query, pivoting strategy. These are architecturally separate concerns with separate implementations. (n8n blog — "Architectural Guide to Error Handling for LLM Tool Calling," July 2026)

3. **Checkpoint every meaningful step.** For long-running agents, save state at the start of each step: completed outputs, current conversation context, and tool results. On crash or failure, resume from the last checkpoint rather than restarting. The `agent-resume` library (MukundaKatta, PyPI, MIT) implements this as JSONL storage: "Your agent is processing 100 GitHub issues, crashes on issue 47, and the next run picks up at issue 48." (GitHub: MukundaKatta/agent-resume) LangGraph's checkpointing offers step-level replay and time-travel debugging for graph-based agents. (MarkTechPost, August 2025)

4. **Circuit breaker with fail-closed defaults.** When a tool or service fails N times in a row, stop calling it and return a controlled error rather than continuing to hammer a degraded service. FailWatch is a fail-closed circuit breaker for AI agents (Ludwig1827, Show HN, 2025). The fail-closed property is critical: a circuit breaker that fails open lets the agent proceed with no tool, producing hallucinated output. (Tanuj Garg — "Building Reliable AI Agents: Patterns for Failure Recovery," April 2026)

5. **Semantic validation as a gate.** Before a tool result feeds into the next reasoning step, validate it. Check: does the output match the expected schema? Is the result internally consistent? Is it consistent with prior outputs? A hallucinated tool result returning HTTP 200 will pass every syntactic check — only semantic validation catches it. (Vectara awesome-agent-failures, Apache-2.0, August 2025)

6. **Escalation path for irreversible actions.** Actions that touch external systems (email sends, database deletes, payment calls) need a human-in-the-loop gate when confidence is low. Define thresholds explicitly: if confidence < 0.7 and action type is "write," escalate. Tanuj Garg calls this "safe autonomy by design" — autonomy bounded by consequence. (Tanuj Garg, April 2026)

## Evidence

- **GitHub repo:** Vectara's `awesome-agent-failures` documents 89 production failure modes across six categories — tool hallucination, response hallucination, goal misinterpretation, reasoning loops, cascading failures, and context overflow. Each entry includes a real-world example and battle-tested mitigation. (vectara/awesome-agent-failures — https://github.com/vectara/awesome-agent-failures)
- **Engineering blog:** Tanuj Garg's reliability patterns post articulates the core thesis: "AI agent reliability is primarily a systems engineering problem — not a model quality problem. The same principles that make distributed systems reliable (idempotency, circuit breakers, observability, graceful degradation, human oversight) apply directly to agent architectures." (https://tanujgarg.com/blog/ai-agent-reliability-patterns)
- **Orchestration pattern:** n8n's architectural guide maps error handling to two distinct layers: orchestration layer (silent infrastructure retries) and LLM layer (behavioral pivots requiring model reasoning). "Leaving error handling for LLM tool calls entirely to the model itself guarantees automated pipelines will break the moment a connected service drops." (n8n blog — "LLM Tool Calling Error Handling," July 2026)
- **Checkpoint tooling:** LangGraph's step-replay and checkpointing enables mid-task resume. AgentMarketCap's 2026 engineering survey found that durable execution and checkpoint/resume are among the top three production engineering investments for agent teams. (AgentMarketCap — "Agent Checkpoint and Rollback Engineering 2026," April 2026 — https://agentmarketcap.ai/blog/2026/04/11/agent-checkpoint-rollback-engineering-2026)
- **Community-sourced cost data:** A practitioner on r/AI_Agents reported an $83 OpenAI bill from a single agent run caused by an unseen retry loop — the agent's external API timed out ~15% of the time, and simple "retry on failure" logic cascaded into exponential API calls. (Reddit r/AI_Agents, 2025)

## Gotchas

- **Retry loops are not free.** Every retry that reaches the LLM costs a full inference call. Without circuit breakers and error classification, a 15% API failure rate on a naive retry loop can multiply into runaway costs. Classify errors before retrying — only transient errors (5xx, 429, timeouts) deserve retries.
- **HTTP 200 is not success.** Agents can fail semantically and return HTTP 200. A RAG tool can hallucinate a response, a code execution tool can return valid syntax that implements the wrong logic, and a search tool can return plausible but wrong facts. Without output validation, the agent propagates the error downstream with no awareness it happened.
- **Checkpointing alone is not recovery.** Saving state is necessary but not sufficient. You also need a replay mechanism that can reconstruct the agent's continuation from the checkpoint. And checkpoints need to be stored durably — in-memory state dies with the process.
- **Idempotency is the foundation.** Recovery only works if the operation is safe to re-execute. For write operations, use idempotency keys. If your agent sends an email on step 4 and crashes at step 7, the resume must not re-send the email. This is not an optional polish feature — it is the precondition for checkpoint/resume to be safe.
- **The "agent never knows" failure mode.** When the orchestration layer silently retries transient errors, the agent's conversation context never reflects the failure. This means the agent can proceed with an incorrect mental model of what happened. For non-transient errors that require the agent to change strategy, you must surface the failure explicitly into the conversation context — silent retries are only appropriate for fully reversible operations.
