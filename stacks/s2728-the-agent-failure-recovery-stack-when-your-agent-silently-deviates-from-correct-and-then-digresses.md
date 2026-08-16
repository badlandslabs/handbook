# S-2728 · The Agent Failure Recovery Stack — When Your Agent Silently Deviates From Correct and Then Digresses

Your agent has been running for 40 minutes on a task that should take 5. It produced 23 tool calls, none of which made progress. It is not failing loudly — it is failing silently, confidently drifting away from the correct path while appearing to work. By the time you notice, the context window is half-gone and the task cost $14. This is the failure recovery gap: agents that detect errors but can't recover from them, or that never detect the error in the first place.

Traditional error handling (try/catch, HTTP status codes) handles infrastructure failures. Agent failure recovery handles the harder problem: reasoning failures, silent divergences, tool-call loops, and semantically wrong outputs that look valid.

## Forces

- **Agents fail non-deterministically.** A step that worked yesterday can fail today with no error message — the output is just subtly wrong, and downstream steps proceed on false premises. You can't catch it with exceptions.
- **The error and the recovery require different responses.** Retrying a rate-limit error makes sense. Retrying a hallucinated tool call produces a different hallucination. Confusing these categories wastes budget and time.
- **Recovery is time-sensitive.** A stuck agent burning tokens at step 12 is worse than a failed agent that stopped cleanly. The longer an error goes undetected, the more expensive it becomes.
- **Human escalation is real infrastructure.** For high-stakes actions, the right failure handler is not a retry — it is a human with full context and an override interface.

## The Move

Build a layered failure recovery architecture that separates failure detection from failure response, routes each failure type to the appropriate recovery primitive, and includes an escalation ladder that bottoms out in human review.

### 1. Classify before you act

Every agent failure is one of two categories — this determines the entire response:

| Category | Example | Response |
|---|---|---|
| **Infrastructure error** | HTTP 429, 503, 529, timeout, network failure | Retry with backoff + jitter; circuit breaker if persistent |
| **Agentic error** | Hallucinated tool, invalid output schema, wrong reasoning path, loop | Do NOT retry blindly — fix root cause or rollback |

The AI agent guidebook (ai-infra-curriculum/ai-agent-guidebook) codifies this: "Retrying a 429 makes sense; retrying a hallucination usually produces a different hallucination." Surface `context_length_exceeded` as a capacity error (compact + retry), not a model failure.

### 2. Detect the stuck loop separately from step-count limits

LangChain's `max_iterations` caps total steps but does not distinguish a productive 20-step agent from a broken one calling the same tool 20 times. The agentpatterns.ai stuck-loop recovery guide recommends a **progress metric that only increases on real work done** — failing tests resolved, unique sources gathered, checklist items completed — rather than activity metrics like API call counts.

Once detection fires, climb the **recovery ladder** (agentpatterns.ai):

1. **Nudge** — inject a self-correction prompt: "You called this tool 3 times with no meaningful result. Try a different approach."
2. **Replan** — re-prompt with the original goal, the current state, and a constraint to avoid the failing path.
3. **Escalate** — move to a higher-capability model or a supervisor agent for the current step only.
4. **Reset** — rollback to the last checkpoint (discard current session path, restore prior state).
5. **Hand off** — surface to human reviewer with full agent reasoning, proposed action, and context.

### 3. Stateful rollback via checkpoints — not full restart

LangGraph's checkpointing primitives (AI DEV DAY, 2026) allow rewinding to a known-good state without losing user context. A single bad tool call at step 12 should not require restarting the entire 12-step run and wasting tokens already spent. The pattern: snapshot state at every node boundary, then use `state.update(last_checkpoint)` to rewind.

| Checkpointer | Use case |
|---|---|
| **Postgres** | Production durability, multi-writer |
| **Redis** | Low-latency single-node |
| **Memory** | Dev/test only |

Post-checkpoint, the agent resumes from the saved state with the error surfaced explicitly, not re-attempted identically.

### 4. Self-correction loops with explicit validation

The self-correcting loop (LangGraph, CrewAI) is: **act → observe → evaluate → replan**. The critical addition is that evaluation must be a real check, not self-reporting. The ai-agent-guidebook states directly: "Do not let the model self-report success; verify via a real check." If the agent claims it found the right file, actually verify the file exists before proceeding.

### 5. Human-in-the-loop as a first-class component

HITL is not a fallback — it is an architectural tier (Agents.NET, 2026). Design explicit escalation triggers:

- **Confidence threshold**: when internal confidence falls below a tuned threshold, queue for human review instead of proceeding.
- **High-stakes action gates**: financial transactions, irreversible deletions, customer communications — always require human approval before execution.
- **Approval queue interface**: give reviewers the agent's reasoning, the proposed action, and relevant context. Decisions should be possible in seconds, not hours.

The Production AI Institute (2026) adds: version your system prompts and tool definitions the same way you version code — a bad system prompt change causes cascading failures that look like model problems.

## Evidence

- **GitHub (ai-infra-curriculum/ai-agent-guidebook):** Failure taxonomy and response routing — "Two error categories: Errors the AI surfaces vs. errors the AI causes via infrastructure. The two categories require different responses." — [URL](https://github.com/ai-infra-curriculum/ai-agent-guidebook/blob/main/best-practices/error-handling.md)

- **GitHub (agentpatterns-ai/website):** Stuck-loop recovery ladder — "Once detection flags a stuck loop, climb a bounded recovery ladder — nudge, replan, escalate, reset, hand off — until the agent escapes or a human takes over." Progress metrics must distinguish stuck from slow-but-converging. — [URL](https://github.com/agentpatterns-ai/website/blob/main/loop-engineering/stuck-loop-recovery.md)

- **Blog (AI DEV DAY India, May 2026):** LangGraph rollback pattern — "A single bad tool call at step 12 should not require restarting the entire 12-step run. Three lines of checkpoint code can rewind a corrupted execution thread to its last known-good state." Postgres for production durability, Redis for low-latency single-node. — [URL](https://aidevdayindia.org/blogs/ai-agent-observability-agentops-playbook/ai-agent-rollback-checkpoint-pattern-langgraph-production.html)

- **Blog (Agents.NET, Jun 2026):** HITL as architecture — "Human-in-the-loop isn't a fallback — it's a first-class architectural component for production agents. Define a confidence threshold below which the agent surfaces the decision to a human reviewer." — [URL](https://agents.net/blog/ai-agent-debugging-error-handling-production)

- **Blog (DEV Community / Alan West, May 2026):** Real-world stuck loop case — "A ReAct-style customer support triage agent burned through 47,000 tokens in a single session, calling `search_knowledge_base` 73 times with slightly different queries — never stopping." Root cause: no progress metric, no step cap on repeating patterns. — [URL](https://dev.to/alanwest/why-your-ai-agent-loops-forever-and-how-to-break-the-cycle-12ia)

## Gotchas

- **LangChain's `max_iterations` does not stop repeating patterns.** It only stops after N total steps. A productive 15-step agent and a broken one calling the same tool 15 times look identical. Add a repeated-action detector that fires before iteration exhaustion.
- **Retrying hallucinated output produces a different hallucination, not a correction.** Fix the tool schema or re-prompt with constraints — do not loop the same faulty reasoning.
- **Checkpoint rollback discards work since the checkpoint, not just the last step.** If your checkpoint cadence is too coarse (only at major phase boundaries), you may lose minutes of real progress. Set checkpoints at every node boundary.
- **HITL implemented as a modal "approve/reject" button is theater, not engineering.** Real HITL requires tuning confidence thresholds from production data, providing reviewers with agent reasoning and context in seconds-readable form, and an auditable override log.
- **Context window overflow (HTTP 400 `context_length_exceeded`) is an infrastructure error, not an agentic one.** Compact the context (summarize or drop low-value history) and retry — do not treat it as a reasoning failure.
