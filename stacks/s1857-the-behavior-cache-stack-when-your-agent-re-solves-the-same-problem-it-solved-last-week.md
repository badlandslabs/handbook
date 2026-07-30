# S-1857 · The Behavior Cache Stack

When your agent encounters a task it has solved before — same type, same tools, different data — and recomputes the entire tool-call sequence from scratch, burning tokens and latency, instead of replaying what it already figured out.

## Forces

- **Repetitive automation is economically punishing.** LLM-based agents cost $0.01–$40/hr in token spend. For repetitive tasks (legacy app automation, form workflows, API pipelines), the LLM is doing work that a script could do for free.
- **Agents at steady state are predictable.** Once an agent has successfully executed a task type, subsequent encounters with that task type follow the same tool-call trajectory — except the LLM re-derives it every time.
- **Deterministic replay is faster and cheaper than re-reasoning.** A cached trajectory runs in milliseconds at near-zero cost. The LLM takes seconds to minutes and costs money.
- **Edge cases still need the LLM.** The cache must gracefully fall back to agent mode when the task exceeds what was recorded, without knowing in advance that it will.
- **Recording the right thing is hard.** Capturing "task identity" — when two inputs are the same task type — requires careful design of the cache key (checksum, semantic hash, task signature).

## The move

**Record successful agent trajectories as deterministic replays, falling back to LLM mode only for edge cases.**

1. **Instrument your agent to emit tool-call traces** with inputs, outputs, and a task signature (the semantic essence of what the task is, not the raw data). Store these in a durable cache.
2. **On task receipt, compute a cache key** from the task signature. On a hit, **deterministically replay the stored trajectory** — same tool calls, same order, with the new data substituted into the parameter positions.
3. **Run a lightweight verifier** on the replay output to confirm the replay still works. On failure, fall back to live agent mode and record the new trajectory.
4. **Treat the cache as a living layer, not a static optimization.** Evict trajectories that have a replay-failure rate above a threshold. Annotate trajectories with metadata (tool version, environment version) to invalidate when dependencies change.
5. **Scope the cache conservatively at first.** Start with high-repetition, low-stakes task types. Expand only after measuring that the hit rate and replay success rate justify the infrastructure.
6. **Separate the cache from the agent framework.** The cache should be a plugin into your existing agent, not a replacement for it. This keeps the agent's logic clean and makes the cache easy to swap or disable.

## Evidence

- **GitHub / Open-source SDK:** Muscle-Mem (pig-dot-dev/muscle-mem) — a Python SDK that implements exactly this pattern. Agents record tool-calling sequences as they solve tasks, then deterministically replay them on cache hits, falling back to agent mode on misses. Built at Pig.dev for automating legacy Windows applications (healthcare, lending, manufacturing) where pure-vision agents at $40/hr were economically unviable for repetitive automations. — [github.com/pig-dot-dev/muscle-mem](https://github.com/pig-dot-dev/muscle-mem)
- **HN Show:** Dexto (truffle-ai/dexto, 41 points) — an open-source agent harness that positions itself as "the operating system for your agent," providing session management, tool orchestration, memory, and recovery. Treats the LLM as CPU, context window as RAM, and Dexto as OS-level orchestration, noting that stateful recovery is essential for real-world agents. — [news.ycombinator.com/item?id=45734696](https://news.ycombinator.com/item?id=45734696)
- **Primary source / Engineering blog:** Anthropic's "Building Effective Agents" (Dec 2024) identifies that the most successful agent implementations use composable patterns rather than complex frameworks, and emphasizes that the core loop is "augmented LLM → tools → memory." The behavior cache pattern extends this by caching the tool-call *decisions* across invocations. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **Cache key design is the hardest part.** A too-coarse key produces false hits (wrong trajectory replayed). A too-fine key produces zero hits. Semantic/hybrid hashing beats raw input hashing for task types that vary in data but not structure.
- **Stale trajectories will fail silently.** If the underlying API, UI, or tool interface changes between recording and replay, the replay will produce wrong outputs with no error. Always verify replay output against an expected schema or assertion.
- **Recording production traces requires consent and safety.** Capturing tool-call trajectories that may contain PII, credentials, or sensitive data requires careful handling. Treat traces as sensitive unless explicitly anonymized.
- **The fallback loop must be bounded.** If the cache hit rate is too low or the fallback keeps failing, you get an expensive retry spiral. Track cache hit rate and fallback success rate as first-class metrics.
- **Not all tasks are cacheable.** Tasks that require novel reasoning, multi-hop judgment, or context-dependent planning cannot be replayed. The cache works for repetitive structured tasks, not exploratory ones.
