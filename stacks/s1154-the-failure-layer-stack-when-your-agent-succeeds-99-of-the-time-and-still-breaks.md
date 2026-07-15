# S-1154 · The Failure Layer Stack — When Your Agent Succeeds 99% of the Time and Still Breaks

Your agent works great in demos. Ten steps, each 99% reliable — that's a 90% overall success rate. Ten steps, each 85% reliable — that's 20%. The math compounds quietly until production shows you a $4,000 API bill and an agent still running the same failed search for the sixth time. The failure layer is the set of mechanisms you build *before* the failure, not after.

## Forces

- **Reliability compounds against you.** A 10-step workflow where each step succeeds 85% of the time finishes ~20% of the time without durability. Better models don't fix network failures.
- **Agents fail in shapes single-LLM calls don't.** Hallucinated tool parameters (correct tool, fabricated values), tool crashes, cyclic graph execution, state corruption at parallel merges, and silent degradation where the agent produces wrong-but-plausible output.
- **The divide is reversibility, not severity.** A failed API call and a data deletion may both "fail," but one is recoverable and one isn't. Systems that treat severity as the escalation criterion get it wrong.
- **Output validation is not optional.** Bad LLM outputs crash downstream code. The agent produces malformed JSON, the next tool chokes, and the entire graph collapses because no guardrail validated the output between nodes.

## The Move

Build a three-layer failure architecture: hard guardrails stop the runaway, self-correction fixes the recoverable, and durable execution makes recovery actually possible.

### Layer 1: Hard Guardrails

- **Step caps are non-negotiable.** Set a hard `MAX_STEPS` (LangGraph: `recursion_limit=12`). An agent that doesn't finish in 12 steps is telling you something broke — stop it, capture the state, escalate. A single decorator like AgentCircuit's `Fuse` kills infinite loops before they drain your wallet; CircuitBreaker.dev enforces cost caps per run with hard-stop hooks that trigger before runaway costs. Reported cases of $200+ in API spend before loop detection fires.
- **Timeout contracts per tool call.** Rate limits clear in 30 seconds; permanent hangs don't. Attach timeouts to every external call, not just LLM invocations.
- **Output schema validation at every node boundary.** Validate tool outputs, LLM JSON, and parameter shapes *before* passing them downstream. An agent that passes garbage to the next node snowballs the error across the whole graph.

### Layer 2: Self-Correction

- **Instruct the agent to critique itself before acting.** A reflection node reviews the current output, identifies specific failure modes (wrong format, missing field, contradicted earlier result), and revises. This is the "Reflexion" pattern — a specialized critique head that grades agent outputs and feeds the grade back as revision guidance.
- **Distinguish recoverable from non-recoverable errors.** Recoverable: bad tool parameters, API timeouts, rate limits, JSON parse failures. Strategy: validate inputs before calling, retry with exponential backoff, fall back to a simpler tool, switch to a cheaper model. Non-recoverable: irreversible actions (data deletion, payment execution), output that contradicts a hard constraint. Strategy: interrupt and escalate to human.
- **LoopGain-style convergence tracking.** Measure the error shrink ratio (Aβ) across iterations. If Aβ < 1, the loop is improving. If Aβ ≥ 1, the loop is stalled or worsening — stop and roll back to the lowest-error output so far. The trajectory classifier labels the loop state (FAST_CONVERGE / CONVERGING / STALLING / OSCILLATING / DIVERGING) and decides whether to continue, stop here, or rollback.

### Layer 3: Durable Execution

- **Checkpoint after every logical step, not every LLM call.** LangGraph's `MemorySaver` (in-memory) or Redis checkpointer (persistent) saves a `StateSnapshot` after each graph node. On crash or restart, the agent resumes from the last checkpoint — not from scratch. The agent becomes a row in a checkpoint store, not a stack frame in a living process.
- **Schema changes break checkpoint deserialization.** When you change your state schema, all historical checkpoint conversations fail to resume. Version your schema and migrate checkpoints, or accept that the upgrade resets in-flight agents.
- **Parallel branch merges can corrupt state.** When `Send` operations return from parallel tool calls, inconsistent values land in shared state before downstream nodes consume them. Use deterministic merge logic, not "last write wins."

## Evidence

- **GitHub system-design guide:** Taxonomy of agent failures — hallucinated tools, hallucinated parameters, cyclic graph execution, state corruption at parallel merges, checkpoint deserialization failures. Frameworks like LangGraph and Microsoft Agent Framework provide native checkpoint/resume primitives. — [github.com/ombharatiya/ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **Engineering blog:** At Asynq.ai, a candidate evaluation agent hallucinated tool parameters, got stuck in loops, produced contradictory evaluations, and cost 3x budget — resolved with parameter validation, step caps, and output validation layers between nodes. — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Engineering blog:** Durable execution math — 10 steps at 85% reliability = ~20% full completion without checkpointing; with durable execution, each failure resumes from the last checkpoint instead of from scratch. LangGraph checkpointing makes state "a row in a checkpoint store, not a stack frame." — [vadim.blog](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off/)

## Gotchas

- **Hard step caps stop the bleeding but don't restore progress.** If your agent hits the cap and you just restart from step 1, you're back where you started. Step caps must pair with checkpointing to be useful.
- **Human-in-the-loop interrupts can be bypassed by conditional routing.** If a conditional edge routes around the human-approval node, the agent makes the decision anyway. Verify that interrupt nodes can't be skipped by any conditional path.
- **Silent degradation is worse than loud failure.** A tool that returns 200 OK but with subtly wrong data is more dangerous than one that throws an exception. Instrument for output quality signals, not just error codes.
- **Retry logic without backoff amplifies rate-limit failures.** If a tool returns a 429 and you retry immediately 3 times, you've guaranteed yourself a longer wait. Use exponential backoff starting at 30 seconds.
- **Checkpoint schema drift after deployment.** Prod deploys that change the state schema break all in-flight agent sessions. Version your schema or design the checkpointer to handle migrations.
