# S-2276 · The Bounceback Stack — When Your Agent Crashes and Nobody Drew the Fence

Your multi-step agent is 47 steps into a 50-step task when the process dies. Network blip, OOM kill, container restart. When it restarts, it starts over from step 1. This is the default state of most agent code, and it is the most expensive assumption in production AI: that failures are rare enough to ignore. They are not.

## Forces

- **The math of chained steps punishes restarts.** A 10-step chain at 85% per-step reliability has a 20% overall success rate — not because the model fails, but because each step is a fresh opportunity for a network blip, rate limit, or timeout. Without durable state, every failure is total.
- **Agents are assumed to be in-memory loops.** Most agent code is a `while` loop with local variables. When the process dies, the state dies. This works fine in development. It is a production liability.
- **Claude Code's dirty secret.** Only 1.6% of Claude Code is AI decision logic — the other 98.4% is operational infrastructure: checkpointing, retry, observability, sandboxing. The code that makes decisions is a tiny fraction of the code that makes it durable.
- **Retry is not recovery.** Retrying a step re-executes it — including its side effects. If step 17 sent an email, a retry without idempotency sends it twice. Durable execution separates "save state" from "re-execute" so you can resume without re-running.

## The move

Design for bounceback from the start. State survives process death. Work resumes where it left off. Side effects are protected by idempotency keys or guarded re-execution.

- **Checkpoint after every logical step, not every LLM call.** A "logical step" is a user-meaningful action (fetch document, draft email, call API). LLM calls within a step are not separately checkpointed — the step itself is the atomic unit of recovery.
- **Use `thread_id` as the durable identity key.** In LangGraph, the `thread_id` maps to a persistent checkpoint store (SQLite for dev, Postgres for production). Resume is `graph.invoke(None, config={"thread_id": "campaign-42-user-7"})` — the graph rehydrates from disk without re-running the LLM calls.
- **Idempotency guards on all side-effecting tools.** Every tool that writes (email, API POST, database write, file creation) must carry an idempotency key or check "did I already do this?" before executing. This enables safe re-execution from a checkpoint without duplicate side effects.
- **Separate persistence backend by environment.** LangGraph ships SQLite (dev, single-process) and Postgres (production, multi-instance). Cloudflare D1 has a hard limit of 100 bound parameters per statement — batch writes must be chunked under that limit or the checkpointer silently fails.
- **Set `checkpoint_at` boundaries explicitly.** Not every node needs to be checkpointed. Mark only the nodes where "if this crashes, re-running would be expensive or duplicative." This reduces storage overhead and checkpoint latency.
- **Crash the agent on purpose to test.** Wire `enable_logging=True` into the checkpointer so write failures surface immediately instead of silently swallowing them. Then kill the process at step 30 and verify it resumes at step 30 — not step 1.

## Evidence

- **Engineering blog — Vadim's blog on LangGraph durable execution:** Mathematical proof that 10 steps × 85% reliability = 20% overall success; worked example of a month-long email campaign on Cloudflare Workers using `AsyncCloudflareD1Saver` with deterministic `thread_id` as `"campaign-{campaign_id}-{contact_id}"` — [vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off)
- **Research paper — arXiv:2604.14228 (Dive into Claude Code):** Empirical analysis finding that only 1.6% of Claude Code's codebase is AI decision logic, with the remaining 98.4% devoted to checkpointing, retry, sandboxing, and observability infrastructure — [arxiv.org/abs/2604.14228](https://arxiv.org/abs/2604.14228)
- **GitHub repo — AXME agent:** "Your agent crashes at step 47 of 50. LangGraph: write checkpoint code, configure PostgresSaver, manage state manually. CrewAI: start over from step 1. AXME: restart the agent. It picks up at step 47 automatically." — [github.com/eunomia-dev/axme](https://github.com/eunomia-dev/axme) (Apache 2.0)

## Gotchas

- **Idempotency is the forgotten half of durability.** Checkpoint/resume without idempotency guards produces duplicate emails, double payments, and race conditions. Add idempotency keys to every side-effecting tool before you ship.
- **`enable_logging=False` (the default) hides checkpointer failures.** On Cloudflare D1 and other constrained backends, write failures are silently dropped. Set it to `True` in staging and watch the logs for the first two weeks.
- **State size grows with conversation length.** Long-running agents accumulate checkpoint state proportional to context. Periodic snapshot summarization (compress the last 50 checkpoints into a summary) prevents storage bloat in 1000-step workflows.
- **`thread_id` collisions are silent data corruption.** Two requests with the same `thread_id` share the same checkpoint history. Use composable keys (`"user-123-session-456-step-47"`) rather than flat IDs in shared deployments.
