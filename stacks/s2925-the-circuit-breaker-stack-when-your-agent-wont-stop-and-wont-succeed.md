# S-2925 · The Circuit Breaker Stack — When Your Agent Won't Stop and Won't Succeed

Your candidate evaluation agent is three hours into a task that should take five minutes. It has called the resume parser tool 847 times. It is not stuck in an error state — it is generating tokens, making tool calls, producing output — but every iteration compounds on a wrong assumption from step one. There is no exception, no timeout, no signal that anything is broken. Just an agent doing exactly what it was designed to do, to completion, on the wrong answer. Infinite Agentic Loops (IALs) don't look like crashes. They look like productivity.

## Forces

- **Agents are designed to keep trying** — The core loop is "observe → act → observe." Without an explicit termination bound, the loop condition is always true. The model has no internal sense of diminishing returns.
- **Individual step success masks aggregate failure** — A 20-step workflow with 95% per-step reliability succeeds only 36% of the time overall. Each step looks fine. The failure is invisible until the output is garbage.
- **IALs consume resources invisibly** — Token costs, API rate limits, external side effects, and context window growth compound silently. By the time a circuit breaker trips, the damage is done.
- **Traditional retry logic doesn't classify errors** — Retrying a 401 is different from retrying a 429. Hammering an endpoint that returned a semantic failure (wrong schema, hallucinated parameter) just wastes tokens and amplifies the failure.
- **State loss on interruption is catastrophic** — If a long-running agent crashes at step 18 of 20, starting over from scratch means re-running all 18 steps with the same failure modes, potentially landing on the same wrong answer.

## The Move

Build three concentric layers of termination and recovery around every agent loop.

### Layer 1 — Hard Bounds (non-negotiable)

- **Set `MAX_STEPS`** before the loop runs, not inside it. For most agentic workflows, 8–15 steps is the practical ceiling before token costs dwarf task value. `recursion_limit=12` in LangGraph is the canonical threshold.
- **Budget a cost circuit breaker** — track cumulative token spend per run. A hard cap in dollars (e.g., $2.00 per task) prevents runaway costs from a single stuck agent.
- **Classify errors before retrying.** Four categories: **transient** (429, timeout, DNS) → retry with backoff; **semantic** (malformed JSON, wrong schema) → re-prompt with corrective context; **resource** (token overflow, context full) → reduce payload or switch model; **fatal** (401, revoked key, policy violation) → abort immediately, alert, log. Never apply the same retry strategy to all error types.

### Layer 2 — Loop Detection

- **Track action repetition at the infrastructure level**, not the model level. Hash each `(tool_name, tool_input)` pair. If the same pair appears N times in a row (e.g., N=3), interrupt and escalate. The model may generate slightly different tokens each iteration while calling the same broken tool with the same wrong parameters.
- **Detect context growth rate** — if `len(context_tokens)` increases monotonically without producing a terminal output for 3+ steps, the agent is likely filling context with redundant reasoning. Snapshot and interrupt.
- **Use a smaller "verifier" model** to validate tool outputs at critical decision points — pipe tool results to a fast, cheap model that answers: "Does this actually address the query?" If the verifier says no, trigger a self-correction path rather than continuing.

### Layer 3 — Checkpointing and Recovery

- **Save checkpoints after every node** using a persistent checkpointer (LangGraph `MemorySaver`, `SqliteSaver`, or PostgresSaver depending on durability needs). Tag each checkpoint with a monotonic ID and `thread_id`.
- **Resume from the last checkpoint**, not from scratch. In LangGraph, calling `invoke(None, config={"configurable": {"thread_id": "task-123"}})` resumes from the last saved state — the agent picks up mid-graph without re-executing completed steps.
- **Rewind to an earlier checkpoint** when a recovery attempt fails. If resuming from step 8 lands the agent in the same failure mode, rewind to step 3 and inject a corrective hint before replaying.
- **Snapshot on human-in-the-loop gates** — any decision point requiring human approval should snapshot state before pausing. Resume from that exact state after approval, not from the last auto-save.
- **Verify persistence survives container restarts.** Teams frequently ship on `MemorySaver`, watch a pod restart kill in-flight agent threads, and then scramble to migrate to `SqliteSaver` in production. Test this explicitly.

## Evidence

- **arXiv / Huazhong University of Science and Technology:** IAL-Scan, a static analyzer for Infinite Agentic Loops, detected **68 confirmed IAL failures across 47 projects** from 6,549 repositories with **91.9% precision**. Key finding: IALs arise from interaction between agent logic, framework semantics, runtime observations, and termination mechanisms — not from any single source. They cause cost exhaustion, model denial of service, context growth, and repeated external side effects. — [arXiv:2607.01641](https://arxiv.org/abs/2607.01641)

- **Latitude blog (March 2026):** AI agents fail on **63% of complex multi-step tasks** in production. The compounding failure rate is invisible at the individual step level — a 20-step workflow with 95% per-step reliability succeeds only 36% of the time overall. Four failure clusters: reasoning drift, tool call failures, context window saturation, and goal misalignment. — [latitude.so](https://latitude.so/blog/why-ai-agents-break-in-production)

- **Harper Labs / HN Ask thread:** Built a testing framework after observing that a prompt injection in a customer support agent processed a $47,000 fraudulent refund. Core failure modes include: hallucination under unexpected inputs, edge case collapse on null values and Unicode names (O'Brien, 张伟), state inconsistency across tool calls, and reward hacking — the agent optimizing for workflow completion signals rather than task correctness. — [Hacker News #47325105](https://news.ycombinator.com/item?id=47325105)

- **Harsh Rastogi / Modelia.ai & Asynq.ai (March 2026):** Their candidate evaluation agent hallucinated tool parameters, got stuck in loops, and cost 3x budget in production. An image generation pipeline approved obviously flawed images because the agent was optimizing for completing the workflow (no error raised) rather than meeting quality criteria. Key production insight: "The problem is almost never the LLM. It's the infrastructure around the LLM." — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **LangGraph persistence docs:** LangGraph's checkpointer saves state after every node, tagged with a `thread_id`. Recovery patterns include resuming interrupted long-running nodes, rewinding to an arbitrary earlier checkpoint, and manually updating past state to create forked trajectories. Passing `None` as input to `invoke()` tells LangGraph to continue from the last checkpoint rather than starting fresh. — [docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/persistence)

- **ExplainX.ai (updated August 2026):** Production loop architecture built on four primitives: **Trigger** (task_id as idempotency key), **Loop body** (bounded with hard MAX_STEPS), **Checkpoint** (after every step to durable storage), **Terminator** (enforced by infrastructure, not by model self-assessment). Key insight: the terminator that relies on the model to decide it's done is not a terminator — it's a suggestion. — [explainx.ai](https://www.explainx.ai/blog/ai-agent-loop-architecture-triggers-retries-checkpoints-2026)

## Gotchas

- **A hard step cap alone is not a circuit breaker** — it stops the loop but doesn't save state. You still lose all work on interruption. Cap + checkpoint is the minimum viable pattern.
- **`MemorySaver` is not production-ready** — it lives in RAM. A single pod restart wipes all in-flight agent threads. The migration path is painful because you also need to audit which `thread_id` values were active.
- **Retry without classification amplifies failures** — hammering a 401 endpoint or retrying a semantically wrong tool call (wrong schema, hallucinated parameter) wastes tokens and can trigger rate limits that cascade to other agents.
- **The verifier model adds latency but catches silent failures** — teams often skip it to reduce latency, then spend days debugging a failed agent run that looked like success from the outside.
- **Context growth is a stealth loop** — the agent's reasoning trace grows with each step. If no terminal output appears within 3–4 steps and tokens are increasing, the agent is likely generating reasoning that doesn't advance the task. Snapshot and interrupt.
- **Human-in-the-loop without checkpointing creates a new failure mode** — pause for approval, lose the pod, resume with no state. Always snapshot on pause, not on resume.
