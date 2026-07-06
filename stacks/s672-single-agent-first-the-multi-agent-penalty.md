# S-672 · Single Agent First: The Multi-Agent Penalty Is Real

[You reach for multi-agent when the problem feels complex. The research says you're probably wrong — Princeton NLP data shows single agents match or beat multi-agent on 64% of tasks, at roughly half the cost. The question isn't how many agents to deploy; it's what signal tells you to split.]

## Forces

- **The multi-agent tax compounds invisibly.** Each additional agent means another LLM call chain, more latency, more context to manage, and more failure modes to instrument. The accuracy gain from splitting rarely covers the cost — unless you've actually measured the bottleneck.
- **Specifying what you want is harder than building more agents.** Teams add agents when a single agent drifts or produces mediocre output. The real fix is better task specification — clearer goals, tighter constraints, better tools — not more agents to vote on the answer.
- **Benchmark results mask the real threshold.** ChatDev scores 33.3% on real programming tasks. Logistics systems score 27% throughput gains. These are not the same problem class, and conflating them leads to the wrong architectural choice.
- **The 40% failure rate has a known cause.** Multi-agent pilots fail not because coordination is impossible, but because teams pick the wrong orchestration pattern or use it without understanding how it breaks under load.

## The move

**Build the single-agent version first. Measure it. Only add agents when evaluation data shows the work is genuinely parallelizable and the single agent is the proven bottleneck.**

- **Measure before splitting.** Instrument the single agent end-to-end: latency per step, token cost per task, error rate by input type. If the agent spends 80% of time on one step, splitting won't help — fixing that step will.
- **Use task complexity as the primary signal, not gut feel.** If the task requires fundamentally different knowledge domains (e.g., legal + technical + financial analysis), that's a real split. If it's the same domain but "a lot of work," that's a pipeline candidate, not a multi-agent one.
- **Start with sequential pipeline before going concurrent.** A pipeline (A → B → C) is easier to debug, easier to instrument, and produces a single failure point. Parallel execution (orchestrator-workers) only makes sense when subtasks are independent and the orchestrator overhead is smaller than the time saved.
- **Add agents for parallelism, not for quality.** If you can run three agents in parallel on independent subtasks and assemble results, that's a real win. If you're running three agents to critique each other's output on the same task, you're paying 3x for a vote — usually not worth it.
- **Cost the split before building it.** If a single-agent task costs $0.02 and takes 8 seconds, a 3-agent version will cost $0.06–$0.12 and take 3–6 seconds — but only if tasks are truly independent. If they have dependencies, you get neither the cost nor the latency benefit.
- **Evaluate the coordination cost.** Autonomous agents in separate contexts diverge unless the task is specified precisely enough that they don't need to negotiate meaning. Specification quality is the binding constraint on multi-agent systems, not model quality.

## Evidence

- **Research finding:** A single agent matched or outperformed multi-agent systems on 64% of benchmarked tasks when given the same tools and context. Multi-agent adds 2.1 percentage points of accuracy at roughly double the cost. — *Beam.ai / citing Princeton NLP findings*, https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production
- **Production failure data:** 40% of multi-agent pilots fail within six months of production deployment — not because multi-agent systems don't work, but because teams pick the wrong orchestration pattern or pick the right one without understanding how it breaks. — *Beam.ai*, https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production
- **Practical guidance:** "Autonomous agents working in separate contexts diverge unless the task is specified clearly enough that they do not have to negotiate what it means. A better strategy is to build the single-agent version first, measure it, and add agents only when the evaluation data shows the work is parallelizable and the single agent is the bottleneck." — *Tacavar production benchmarks*, https://tacavar.com/blog/ai-agent-frameworks-compared-2026
- **Where multi-agent DOES pay off:** Logistics systems show 27% throughput gains and 22% cost reduction when using multi-agent patterns, because subtasks are genuinely independent and the coordination overhead is dwarfed by parallel execution time. — *Thread Transfer*, https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns

## Gotchas

- **Adding an agent when the prompt is vague.** Multi-agent systems amplify specification problems. If the single agent drifts because the instructions are unclear, adding a reviewer agent makes it worse — now two agents are misaligned.
- **Benchmark envy.** Reading about ChatDev or logistics wins and applying the same pattern to a different problem class. Multi-agent shines on parallelizable, independent tasks; it hurts on sequential, tightly coupled ones.
- **Assuming the orchestrator is free.** The orchestrator in an orchestrator-worker pattern must plan, delegate, wait, and assemble. If your subtasks take 10 seconds each, a 3-agent pipeline might take 30+ seconds just in coordination overhead — worse than a single agent that thinks for 15 seconds.
- **Treating agent count as a complexity proxy.** More agents ≠ more capable system. Teams with 12 agents on average (Gartner, Q1 2024 → Q2 2025 surge data) aren't 12x better — they're 12x harder to debug.
