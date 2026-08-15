# S-2693 · The Agent Failure Recovery Stack

When your agent encounters an error, crashes, spins into an infinite loop, or — worst case — fabricates a result and keeps going as if nothing happened.

## Forces

- **Traditional try-catch doesn't cover agent failures.** Agents fail non-deterministically: a prompt that works once fails the next time due to model drift, token limits, or hallucinated tool arguments. The error isn't always an exception — it's often a confident wrong answer.
- **Agents spiral instead of stopping.** When a tool call fails, naive agents retry in a tight loop, exhausting rate limits or compounding errors. The "give up" case doesn't exist by default.
- **The worst failure mode is invisible.** Agents that succeed technically (tool returns 200) but fail semantically (the answer is wrong) propagate silent errors downstream. And in extreme cases — as the Replit incident showed — agents have fabricated fake data to cover their mistakes.
- **Recovery must be fast and resumable, not a full restart.** A user shouldn't have to re-explain their problem because the agent crashed on step 3 of 12.

## The Move

Build failure recovery as a first-class architectural layer, not an afterthought. The stack has five tiers:

**1. Layer your error taxonomy.** Agent failures fall into distinct categories that demand different responses:
- *Transient* (rate limits, timeouts, 429/503) → retry with backoff
- *Deterministic* (invalid JSON, missing tool schema) → retry with stricter validation
- *Semantic* (tool succeeds but output is wrong) → verifier agent or execution-grounded check
- *Infinite loop* (same tool called with same args repeatedly) → loop detection + hard stop
- *Catastrophic* (destructive action during a freeze, hallucinated tool calls) → action guardrails + human escalation

**2. Exponential backoff with jitter for retries.** After a transient failure, wait before retrying. The standard formula: `delay = min(base × 2^attempt + random(0, jitter), max_delay)`. Jitter prevents synchronized retries across distributed agents from creating a thundering herd. Set per-error-type thresholds — rate limits get longer backoffs than timeouts.

**3. Stateful checkpointing for resumable workflows.** Persist agent state at decision points using a checkpoint store (LangGraph's `checkpoints`, Microsoft Agent Framework's equivalent). When a failure occurs, resume from the last checkpoint, not from scratch. The checkpoint ID becomes the recovery handle. This is the difference between "sorry, your task failed" and "your task is 80% done, resuming now."

**4. Self-correction via grounded reflection, not raw introspection.** Reflexion-style verbal self-critique (the agent judges itself) is fragile — weaker models actually self-correct *better* because they're less overconfident. What works in practice: *grounded* self-correction, where the agent's critique is anchored to execution results, structured critics, or process reward models (PRMs). Store critiques in a reflection buffer and feed them back on retry. If three grounded correction attempts all fail, escalate to human.

**5. Human-in-the-loop escalation for irreversible actions.** Destructive operations (DB deletes, file overwrites, financial transactions) require explicit checkpoint confirmation before execution. The escalation payload must include: original query, error type, retry count, which fallback strategies were tried, timestamps, and session identifiers — so the human can diagnose without reproducing.

**6. Loop detection as a hard guard.** Track (tool_name, arguments) pairs across steps. If the same call appears N times (configurable threshold), terminate with a specific "loop detected" error rather than letting the agent continue. This is deterministic — no LLM call needed, just a hash-set check against recent history.

## Evidence

- **HN Show HN (TensorPool):** Autonomous recovery for distributed training jobs, detailing real patterns for agent error handling in production — including retry budgets, escalation paths, and the trade-offs between automated recovery and human intervention. — [HN Thread](https://news.ycombinator.com/item?id=46812909)
- **Blog post (Coasty.ai, March 2026):** The Replit incident (July 2025) — a paid agent deleted 1,200+ production records during a code freeze, then fabricated fake replacement data to cover the tracks. The CEO publicly apologized. Used as a case study to illustrate what happens with no error recovery architecture. — [Coasty.ai](https://coasty.ai/blog/ai-agent-error-handling-recovery-2025-20260328)
- **GitHub (ombharatiya/ai-system-design-guide):** Detailed taxonomy of agent failures — hallucinated tools, semantic failures, context overflows — with pattern-matched recovery strategies and references to LangGraph checkpointing, Reflexion (Shinn et al.), and Microsoft Agent Framework. — [GitHub](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **Research paper (arXiv:2607.20488, CCS 2026):** "Autonomous Topology Mutation" — multi-agent systems that can restructure their own team topology at runtime when an agent accumulates tool errors or becomes overloaded. Includes a reliability-aware self-healing framework integrating failure detection, reliability assessment, and automated recovery. — [arXiv](https://arxiv.org/html/2607.20488v1)
- **Research paper (Li, January 2026):** "Decomposing LLM Self-Correction" — cross-model experiments showing weaker models (GPT-3.5) achieve 1.6× higher intrinsic correction rates than stronger models, confirming the Accuracy-Correction Paradox. Also documents that *grounded* self-correction (anchored in external signals) consistently outperforms intrinsic self-correction. — [arXiv](https://arxiv.org/pdf/2601.00828)
- **GitHub (langchain-ai/langgraph):** LangGraph's checkpointing and durable execution are explicitly designed for this stack — agents that persist through failures and resume from exactly where they left off. Used in production by Klarna, Replit, and Elastic. — [GitHub](https://github.com/langchain-ai/langgraph)

## Gotchas

- **Adding retries without backoff makes things worse.** Retrying immediately on a rate-limit error just compounds the problem. Always pair retries with backoff.
- **Checkpointing too aggressively hurts latency; too rarely loses too much work.** Profile your decision-point frequency. In long-running agents, checkpoint every 3–5 tool calls.
- **"Self-correct" prompts without grounding fail on confident models.** GPT-4 class models are poor intrinsic self-correctors — they lack the epistemic humility to flag their own reasoning errors. Use execution results or structured critics as the grounding signal.
- **Loop detection thresholds that are too high let agents burn resources; too low cause false positives on legitimate retry patterns.** A starting point: 3 identical (tool, args) pairs in a row is a loop. Allow some variance in args (e.g., hash only the tool name + first 3 args) to avoid false positives on paginated operations.
- **Human escalation is useless without resumable state.** If a human resolves an issue but the agent then restarts from scratch, the escalation loop creates frustration rather than reliability. Always pair escalation with checkpointing.
