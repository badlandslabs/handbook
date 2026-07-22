# S-1469 · The Pattern Paradox Stack

When your agent hits the capability ceiling and you reach for orchestration — and suddenly your system is more capable and more fragile at the same time.

## Forces

- **More agents, more capability** — a single agent can't hold enough context or specialize deeply enough for complex tasks. Multi-agent systems unlock what no individual can do.
- **More agents, more coordination debt** — every new agent is a new failure mode. Handoff failures, cascading hallucinations, and context thrashing compound non-linearly.
- **The right pattern depends on the task graph** — sequential workflows, parallel branches, supervisor hierarchies, and evaluator loops each have a performance profile. Picking wrong costs 2–6× in latency or accuracy.
- **Orchestration is where enterprise agents actually fail** — sources consistently report that individual agents work; the coordination layer is where production systems break down.
- **The orchestrator itself becomes a single point of failure** — as orchestration complexity grows, the supervisor/router accumulates enough intelligence that its own errors propagate to every downstream agent.

## The move

The six patterns form a complexity spectrum. Pick the simplest that fits the task graph, not the most powerful.

**1. Sequential Chain** — Fixed pipeline, deterministic, easy to debug. Model A output feeds Model B input. Best for: linear transformation tasks where each step has a clear dependency on the prior. Compounds latency but zero coordination overhead.

**2. Router / Classifier Dispatch** — A lightweight model classifies input and routes to the right specialist. Best for: intent classification, multi-topic queries, and any system where a single entry point must fan out to different handlers. Keeps the routing logic simple and inspectable.

**3. Parallel Fan-Out with Merge** — Concurrent execution of independent subtasks, results merged at a synchronization point. Best for: tasks with no interdependencies — multiple document sections, parallel research branches, concurrent API fetches. Latency drops 1.8–3.7×; cost drops up to 6× versus sequential execution of the same work.

**4. Supervisor / Worker** — A single orchestrator creates execution plans, delegates to specialists, monitors progress, and assembles the final output. Best for: complex tasks with multiple phases but a clear single point of coordination. The supervisor owns state; workers are stateless and stateless-by-design scales better.

**5. Hierarchical Delegation** — Multi-level supervisors where a top-level agent dispatches to mid-level supervisors, which dispatch to specialists. Best for: enterprise-scale workflows that mirror organizational structures. Microsoft's multi-agent reference architecture and arxiv benchmarks (500 config × 10K documents) both confirm this offers the best cost-accuracy Pareto frontier — 97.7% of reflexive accuracy at 60.9% of the cost.

**6. Evaluator-Optimizer Loop (Reflexive)** — Agent produces output, evaluator agent critiques it, original agent revises, loop until quality threshold. Best for: high-stakes outputs where quality matters more than speed. Achieves the highest accuracy (F1 0.943 on financial document extraction) but costs 2.3× sequential baseline.

Production systems combine 2–3 patterns: parallel fan-out for independent research, sequential chaining for dependent transformation steps, and an evaluator loop for final quality gate.

## Evidence

- **Benchmark (arxiv, March 2026):** 500 configurations across 10,000 SEC filings tested 4 orchestration architectures. Hierarchical supervisor-worker achieved F1 0.921 at 1.4× baseline cost — the best cost-accuracy Pareto frontier. Reflexive self-correcting loops reached F1 0.943 but cost 2.3× baseline. Sequential pipeline served as the accuracy and cost baseline. — [arXiv:2603.22651](https://arxiv.org/abs/2603.22651)

- **OpenSwarm production deployment:** A CLI-based orchestrator running multiple Claude Code instances in Worker/Reviewer pairs. Each pipeline step logs iteration count and cost to Linear for full audit trail. Failed jobs stay "in progress" rather than auto-closing. Escalation from Haiku → Sonnet on retry exhaustion. Long-term memory via LanceDB vector embeddings. — [Hacker News Show HN](https://news.ycombinator.com/item?id=47160980) · [ZHC Institute Field Notes](https://www.zhcinstitute.com/research/openswarm-multi-agent-orchestrator)

- **Guardrails benchmark:** An 8B local model scored 53% on multi-step agentic tasks. Adding a reliability layer (retry nudges, step enforcement, ToolResolutionError exceptions for "found nothing" vs "succeeded with empty result", VRAM-aware context budgets) pushed it to 99% — without changing the model. Key finding: no standard benchmark controls for serving backend, and there's no canonical "tool ran but found nothing" exception class in current LLM tool-calling specs. — [Hacker News Show HN](https://news.ycombinator.com/item?id=48192383) · [Forge GitHub](https://github.com/antoinezambelli/forge)

- **Industry survey (jobsbyculture, May 2026):** 94% of production multi-agent failures trace to three failure modes: unbounded loops (agent never stops), hallucination cascades (one agent's error propagates to all downstream), and context overflow (context window exceeded silently). Parallel fan-out achieves 3× latency reduction versus sequential; sequential chains compound latency O(n) with agent count. — [jobsbyculture.com](https://jobsbyculture.com/blog/ai-agent-orchestration-patterns-2026)

- **Microsoft reference architecture:** Multi-agent systems require explicit design for handoff contracts (what data passes between agents), failure modes per agent type, and observability at the orchestration layer — not just per-agent. Guide covers designing for change, balancing extensibility with pragmatism. — [microsoft/multi-agent-reference-architecture](https://github.com/microsoft/multi-agent-reference-architecture)

- **Reddit / LocalLLaMA:** Community consensus: CrewAI works well with OpenAI models but degrades significantly with Mistral or non-OpenAI providers. LangChain has poor documentation for distinguishing chains from agents, leading to over-engineering. AutoGen noted for multi-agent conversation patterns but complexity scales poorly. — [r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1b5n4ci/what_is_the_best_stable_agent_orchestration/)

## Gotchas

- **Reaching for multi-agent when single-agent-with-tools suffices** — the coordination overhead only pays when task complexity genuinely exceeds what one agent can reliably handle. Most teams add agents too early.
- **No handoff contract between agents** — when agents pass context to each other without a typed schema, cascading hallucination is almost guaranteed. Define exactly what data crosses the boundary, not just what the agent "knows."
- **Missing the "tool ran but found nothing" exception** — current LLM tool-calling specs treat "success with empty result" identically to "success with data." Both return HTTP 200-equivalent. Forge coined ToolResolutionError to distinguish these. Without it, garbage data propagates silently downstream.
- **Supervisor becomes the bottleneck** — hierarchical delegation concentrates intelligence in the orchestrator. When the supervisor fails or hallucinates, all downstream work is affected. Budget for supervisor-tier model quality.
- **Evaluating only per-agent, not per-orchestration** — a system where every individual agent works perfectly can still fail at the orchestration layer. Measure end-to-end accuracy, latency, and cost per workflow, not per agent.
