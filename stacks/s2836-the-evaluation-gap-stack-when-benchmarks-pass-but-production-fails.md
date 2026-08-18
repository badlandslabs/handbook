# S-2836 · The Evaluation Gap Stack — When Benchmarks Pass but Production Fails

When your agent scores 87% on standard benchmarks but destroys a production database: you built the wrong measurement system.

## Forces

- **Task completion ≠ quality** — an agent that finishes a task may have done so for the wrong reasons, at the wrong cost, with the wrong side effects
- **The benchmark crisis** — UC Berkeley researchers found all 8 prominent AI agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) could be exploited to achieve near-perfect scores without solving the underlying task; one team gamed 890 tasks with a single character change
- **37% lab-to-production performance gap** — agents behave differently in the wild than in eval environments
- **50x cost variance** — two agent implementations can achieve similar accuracy but differ by 50x in per-task cost
- **Multi-turn compounding errors** — a single bad decision in step 3 of a 20-step task can propagate silently; single-turn eval frameworks miss this entirely

## The Move

Measure the agent-as-system, not the agent-as-model. Build a multi-dimensional eval stack that tracks:

- **Trajectory scoring** — rate the full execution path, not just the final output. Did the agent take unnecessary steps? Waste tokens? Make recoverable errors it should have recovered from?
- **Cost-per-task tracking** — set and enforce a cost ceiling per task. If a task exceeds the budget, it fails even if it produces correct output.
- **Regression pipeline** — run every code commit or prompt change against a golden dataset of known failures. Teams report 20–40% regression rates on agent behavior from minor prompt tweaks.
- **Multi-dimensional pass/fail** — require the agent to pass on accuracy AND cost AND safety AND latency simultaneously. Any single-dimension pass does not count.
- **Failure mode clustering** — group failures by root cause (tool misuse, context overflow, infinite loops, hallucinated calls) rather than by task. One fix can resolve an entire class.
- **Evals as CI** — gate deployments on eval results. Do not let agent behavior degrade silently between releases.

## Evidence

- **UC Berkeley RDI (2025–2026):** All 8 examined agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) could be gamed to near-perfect scores without solving real tasks. Teams achieved 100% on multiple benchmarks while solving zero genuine problems. — [Berkeley RDI: Trustworthy Benchmarks](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/)
- **Hacker News "Ask HN" (2026):** Practitioners described identical failure modes: no step-by-step visibility, surprise LLM bills from untracked token usage, risky outputs going undetected, no audit trail. Tools like AgentShield (2-line LangChain/CrewAI integration) and Lucidic (YC W25) emerged to address the observability gap — [HN: How are you monitoring AI agents in production?](https://news.ycombinator.com/item?id=47301395)
- **BenchGen / Culture Jobs Research (2026):** Found 37% lab-to-production performance gap and 50x cost variance between agent implementations of similar accuracy. Teams achieving strongest production quality connect eval output directly to model improvement loops, treating evals as a continuous signal rather than a periodic check — [BenchGen: State of AI Agent Evaluation 2026](https://benchgen.com/blog/state-of-ai-agent-evaluation-2026) and [AI Agent Evaluation Guide 2026](https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026)
- **Zylos Research (2026):** Documented the benchmark crisis formally, noting that static task-completion scores fail to capture reliability, cost efficiency, safety, and long-horizon competence. Good eval engineering is now as important as good prompt engineering — [Zylos: AI Agent Evaluation and Benchmarking](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)
- **GitHub LangChain Issues (#33504, 2025):** A high-severity bug in `create_agent` caused silent agent failures when LLMs generated complex content strings that failed JSON parsing. No recovery mechanism triggered; agents failed silently. Demonstrates how even framework-level parsing errors compound in production without eval coverage — [langchain-ai/langchain#33504](https://github.com/langchain-ai/langchain/issues/33504)

## Gotchas

- **Single-turn evals miss multi-turn failure** — a 20-step agent that fails on step 17 can still produce "good" output if you only score the final response. Score the trajectory.
- **Accuracy is the wrong primary metric** — cost-per-task, failure recovery rate, and safety boundary adherence often matter more in production. A 95%-accurate agent that costs $4/task is worse than a 90%-accurate agent at $0.40/task for most use cases.
- **Eval datasets rot** — golden datasets built from production traces become stale as the domain evolves. Treat evals as living artifacts that require ongoing maintenance, not one-time setup.
- **Human eval is not scalable** — relying on human raters for every agent version creates a bottleneck. Use human-labeled eval datasets for calibration, then use LLM-as-judge or structured checks for iteration speed.
