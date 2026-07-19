# S-1366 · The Silent Loop Stack — When Your Agent Hits an Error It Cannot See

Your agent is running a 47-step task. Step 31 loops back to step 28. The context window fills with retries. The model keeps generating confident next actions. No exception is raised. No alert fires. It runs for 35 minutes before someone notices. This is the failure mode that makes agents fundamentally different from traditional software — and the one most teams discover only in production.

## Forces

- Agents are the logic layer: they can behave incorrectly without raising exceptions. A tool call that succeeds technically can fail semantically (wrong data returned, partial result, silently truncated output).
- Error propagation cascades. A failure in the planning module corrupts the memory module's state, which then produces bad inputs for the action module — chain reaction, not a single point of failure.
- Retry logic that works for transient network errors actively harms semantic failures: the agent retries the same broken reasoning with the same broken context, burning tokens and compounding the failure.
- Traditional circuit breakers (open/closed/half-open) were designed for deterministic failures. AI agents introduce non-deterministic failure modes that require modified versions of the same pattern.
- The agent cannot reliably detect its own failures — you cannot trust a failing agent to know it is failing.

## The Move

Build a layered failure-recovery architecture with four concentric rings, from outermost (cheapest, fastest) to innermost (most expensive, most capable):

**Ring 1 — Hard Stops (cost ceilings)**
- Set maximum iteration/step limits enforced by the harness, not the agent. When the limit is reached, halt and surface the partial result with a status flag.
- Set maximum token budgets per session. When the context window approaches the limit, checkpoint the state and close the session gracefully.
- Set maximum cost thresholds in dollars. For billed API calls, this is the only universal failure bound that works across all failure modes.

**Ring 2 — Loop Detection (semantic repetition)**
- Track file-edit frequency per path within a session. When the same file is edited N times (typically 3-5), inject a prompt nudge: "You have edited this file N times without it passing tests. Describe what you believe is failing, then choose a different approach or escalate."
- Track action repetition: if the agent calls the same tool with the same arguments N times consecutively, inject a re-plan prompt before the Nth iteration.
- Track trajectory similarity: compute embedding distance between the last K reasoning states. If similarity exceeds a threshold, the agent is looping semantically even if taking different surface actions.

**Ring 3 — Structured Error Taxonomy and Recovery Paths**
Define six failure categories with explicit recovery strategies, drawn from production post-mortems:

| Category | Description | Recovery |
|---|---|---|
| Transient tool failure | API timeout, 429, network blip | Exponential backoff + jitter, retry up to N times |
| Semantic tool failure | Tool returns success code but wrong/no data | Detect via output schema validation, re-call with corrected parameters or different tool |
| Planning failure | Agent generates incoherent or impossible plan | Inject a structured re-planning prompt with a fresh task description |
| Infinite loop | Agent revisits same state | Trigger loop detection (Ring 2), force re-plan |
| Context overflow | Token budget exhausted mid-task | Compress context, checkpoint state, resume from checkpoint |
| Coordination failure | Multi-agent system deadlocks or produces conflicting outputs | Supervisor agent intervenes, resolves conflict, retries sub-tasks |

**Ring 4 — Supervisor Agent (expensive fallback)**
- A meta-agent monitors task-level progress and intervenes when lower-ring mechanisms fail. It can see the full trajectory, not just the current step.
- Supervisor actions: kill and restart the agent with a simplified task, escalate to human review with full trajectory log, or apply a corrective patch to the agent's instructions and resume.
- This is expensive — use only when the first three rings have all fired and failed.

## Evidence

- **Research synthesis (Zylos Research, May 2026):** The central bottleneck in robust agent systems is error propagation — a single failure cascades through planning, memory, and action modules. Teams combining layered defenses (retries → fallbacks → circuit breakers), self-healing runtimes, and explicit error taxonomies report **24%+ improvement in task success rates**. Production failure distribution: 42% specification failures, 37% coordination breakdowns, 21% verification gaps. — [Zylos Research](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **Loop detection benchmark result (AgentPatterns.ai, 2026):** Loop detection middleware — tracking repeated file edits and injecting re-plan prompts when repetition crosses a threshold — moved LangChain's agent from rank 30 to rank 5 on Terminal Bench 2.0 **without changing the underlying model**. The improvement came purely from preventing wasted context on non-progressing iterations. — [AgentPatterns.ai](https://agentpatterns.ai/observability/loop-detection/)

- **Error taxonomy framework (Preporato, May 2026):** Traditional error-handling paradigms (try-catch, HTTP status codes) do not map to agentic failure modes. Agent "errors" include hallucinations returning HTTP 200, tool calls that succeed technically but fail semantically, and reasoning chains producing confident nonsense. Effective recovery requires categorizing each failure type separately and mapping each category to a distinct recovery strategy. — [Preporato](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

## Gotchas

- **Setting max iterations too low kills valid long tasks.** A reasonable research agent may need 60+ steps for a complex task. Tune the threshold per task type, not globally. The goal is to catch loops, not legitimate extended tasks.
- **Naive retry loops amplify cost on semantic failures.** If a tool returns malformed data, retrying the same call with the same parameters produces the same failure. Add output validation between retry attempts — validate the tool's response schema before deciding whether to retry or switch to a fallback.
- **Agents can mask their own failure.** A confident failure is worse than an honest "I don't know." Build output validation into tool return handlers: check schema, check semantic plausibility, check null/empty guards. Do not pass tool results directly to the agent without validation.
- **Context compression mid-loop loses recovery state.** If you compress context to recover from overflow, you must first checkpoint the session state (trajectory, tool results, partial outputs). A compressed session without a checkpoint cannot be resumed — you lose both the progress and the ability to understand what went wrong.
