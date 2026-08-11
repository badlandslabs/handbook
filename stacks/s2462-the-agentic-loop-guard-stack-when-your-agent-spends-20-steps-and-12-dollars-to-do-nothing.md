# S-2462 · The Agentic Loop Guard Stack — When Your Agent Spends 20 Steps and $12 to Do Nothing

Your agent has been running for 15 minutes on a task worth $0.08. The logs show a polite, well-intentioned machine executing the same plan → tool → analyze cycle 60 times without ever converging. No crash, no exception, no dramatic failure. Just a quiet drain of tokens, time, and money. This is the most common production failure mode for tool-using agents, and the default mitigations (iteration caps alone) just make it fail politely 32 times instead of 100. The fix is a layered loop guard system: hard bounds outside the model, no-progress detection across the state, and structured recovery when the agent genuinely cannot proceed.

## Forces

- **Iteration caps alone don't solve the problem.** A hard limit of 32 steps still burns tokens and cost when the agent loops through all of them. The cap must coexist with progress detection that actually identifies stagnation, not just counting attempts.
- **Loops look like progress.** The agent is executing tools, getting responses, and updating its state. Unlike a crash or exception, nothing signals "this is failing." You cannot detect loops by watching for errors — you have to watch for sameness.
- **The model doesn't know it's looping.** Each iteration feels like a new plan to the agent. Without an external signal, it has no reason to believe it should stop or try a different approach.
- **Recovery is different from detection.** Catching a loop and knowing what to do about it are separate problems. The guard must trigger a structured response — a prompt rewrite, a handoff, or a clean exit with partial results — not just a stop.

## The move

A layered loop guard system that enforces hard bounds, detects stagnation, and recovers gracefully.

### Layer 1 — Hard bounds (outside the model's control)

- Set a **maximum iteration count** (e.g., 20–50 depending on task complexity) enforced by the outer driver, not the model prompt. This is a floor, not a ceiling.
- Set a **wall-clock time budget** (e.g., 5–10 minutes) enforced at the infrastructure level. A 30-minute timeout on a 3-minute task is not a safety net — it's a delay.
- Set a **cost budget per task** and fail when it's exceeded. Track cumulative token cost and stop before the bill exceeds the task's value.
- All three bounds must live outside the agent process: shell script, scheduler wrapper, or infrastructure policy. A model cannot be trusted to enforce limits on its own behavior.

### Layer 2 — No-progress detection

- **Tool call signature tracking**: instead of comparing plan text, track the last N (function_name, normalized_args) pairs. Plans can vary at the surface level while the actual tool calls repeat identically. A deduplicated set of signatures smaller than expected progress = loop.
- **Verification fingerprinting**: run a lightweight verifier (often a smaller, faster model) after each tool call to confirm whether the result actually advances toward the goal. A stable or regressing fingerprint across N consecutive steps = loop.
- **Identical or near-identical output detection**: if the last M tool outputs are semantically equivalent (or byte-identical), the agent is re-reading the same data. This catches semantic loops that tool-signature tracking alone misses.
- Detection runs on every step alongside the model inference, not after a timeout fires.

### Layer 3 — Structured recovery

When a loop is detected, do not simply halt. Inject a recovery action:

- **Prompt rewrite**: inject a one-shot example of the correct approach into the next turn. "You've been searching for X three times. The answer was in the second result. Here's the pattern: …"
- **Strategy handoff**: escalate to a different agent role or prompt strategy. If the research agent is looping, hand off to a summarization agent with the accumulated state.
- **Checkpoint resume**: if the agent maintains persistent checkpoints (e.g., PostgresSaver in LangGraph), roll back to the last meaningful state and attempt a different path. Don't lose partial work.
- **Clean exit with partial results**: if no recovery path exists, return what was accomplished with a structured "incomplete" flag and diagnostic metadata (iteration count, last tool called, cost incurred).

### Layer 4 — Observability

- Per-agent execution traces are not optional. Every loop guard must emit a structured event: loop type, iteration count at detection, recovery action taken, outcome.
- Monitor the **loop rate** (% of tasks that trigger loop detection). A spike indicates a downstream change — a model update, a shifted API response format, or a changed page structure — not a user behavior change.
- Track the **cost-per-task distribution**. A long tail of high-cost tasks (even if they eventually succeed) reveals loops that the guard caught but shouldn't have needed to.

## Evidence

- **GitHub repo (brandondocusen/agentic-loops):** Zero-dependency best practices — hard limits on iterations, wall-clock time, and cost enforced outside the model's control; no-progress detection via hash or normalized summary of verification output; loop must leave usable state even on external termination. — [github.com/brandondocusen/agentic-loops](https://github.com/brandondocusen/agentic-loops)
- **Blog post (AgentPatterns.tech):** Detailed taxonomy of loop failure modes — hard loops (identical tool calls), soft loops (same tool with jittered args), semantic loops (re-reading the same data via different tool names), retry storms (same failure repeated). Key mitigation: track tool call signatures (function name + normalized args) rather than plan text to catch jittered repetition. — [agentpatterns.tech/en/failures/infinite-loop](https://www.agentpatterns.tech/en/failures/infinite-loop)
- **DEV Community post (AgentForge / Albert Zhang):** Six months of production multi-agent deployment lessons. Failure modes multiply: Agent A succeeds but takes 30s → Agent B times out; Agent A returns malformed JSON → Agent B crashes. Core principle: "Design your orchestration around 'what breaks' first." — [dev.to/albert_zhang_f468830cf0e6/open-source-multi-agent-orchestration-lessons-from-agentforge-5c3b](https://dev.to/albert_zhang_f468830cf0e6/open-source-multi-agent-orchestration-lessons-from-agentforge-5c3b)
- **YC W26 launch (Sentrial):** Founded by former SenseHQ engineers building agents at scale. Core insight: "When agents fail, choose wrong tools, or blow cost budgets, there's no way to know why — usually just logs and guesswork." Sentrial detects loops, hallucinations, tool misuse, and user frustrations via semantic pattern analysis on every session. — [news.ycombinator.com/item?id=47337659](https://news.ycombinator.com/item?id=47337659)
- **LangGraph error handling guide (ai-system-design-guide):** For critical steps, pipe tool output to a "Verifier Agent" (smaller, faster model) that checks whether the result actually answers the query. If the Verifier says "No," it triggers a self-correction loop as if it were a hard error. Reflexion architecture stores self-reflections in episodic memory for learned self-correction. — [github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

## Gotchas

- **Iteration caps are a band-aid, not a solution.** They reduce the damage of a loop but don't prevent it. You still need no-progress detection to know whether the cap fired because of a genuine hard task or a loop.
- **Plan-level deduplication misses soft loops.** The agent's natural language plan varies between iterations, but the actual tool calls (with slightly jittered arguments) are identical. Track tool signatures, not plan text.
- **Checkpoints without durable storage don't survive infrastructure failures.** MemorySaver and SqliteSaver are fine for development. Production LangGraph deployments must use PostgresSaver — a pod OOMKilled event wipes SQLite mid-run.
- **Monitoring loop rate is more useful than monitoring loop count.** A stable number of loop detections per day is acceptable; a 3x spike is a production incident requiring root cause investigation, not just a log entry.
- **The verifier agent itself can loop.** If you chain a verifier that calls tools, it needs its own loop guard. Keep verifiers stateless and prompt-simple to avoid recursive failure.
