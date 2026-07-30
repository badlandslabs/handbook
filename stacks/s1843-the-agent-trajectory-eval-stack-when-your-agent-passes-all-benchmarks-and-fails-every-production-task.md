# S-1843 · The Agent Trajectory Eval Stack — When Your Agent Passes All Benchmarks and Fails Every Production Task

Your agent scored 94% on your internal benchmark. It was shipped to production. Three weeks later, it is failing silently on 40% of real tasks — generating plausible wrong answers, calling the wrong tools, and burning $5/task on work that should cost $0.10. The benchmark was measuring the wrong thing. The agent is not broken. Your eval was measuring a proxy.

This is the agent eval gap: the systematic mismatch between what benchmarks measure and what production requires. The teams breaking out of eval purgatory — deploying agents that hold up under real distribution, real latency pressure, and real cost constraints — share a common approach: they measure trajectories, not just outcomes; they gate on reliability, not just pass rate; and they run evals in CI, not in a spreadsheet.

## Forces

- **Single-run pass rate is a lie.** τ-bench (Sierra AI / Stanford) showed GPT-4o achieves ~65% pass¹ on retail tasks — but drops to ~25% at pass⁸ (8 independent attempts on the *same* task). A single-shot benchmark overstates reliability by 2–3x. A 94% accuracy number means nothing if the agent fails the same task every third time. — *[Sierra AI, τ-bench benchmark, June 2024](https://sierra.ai/blog/benchmarking-ai-agents)*

- **Cost and accuracy are a Pareto frontier, not a tradeoff you can ignore.** A 2025 enterprise evaluation study (arXiv:2511.14136) found **50x cost variation** ($0.10 to $5.00 per task) between agents achieving similar accuracy. Complex reflection-based architectures can make 2,000+ API calls per task. A 2-point accuracy improvement can cost $50,000 additional spend per 10,000 tasks. Teams that only track accuracy are flying blind on their actual economics. — *[arXiv:2511.14136, "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems", 2025](https://arxiv.org/html/2511.14136v1)*

- **Lab-to-production degradation is 37%.** The same study found agents degrade **37% in performance** moving from benchmark to production, because benchmarks preserve requirement ambiguity and multi-agent complexity that test sets don't. Your eval must replicate production conditions, not textbook conditions. — *[arXiv:2511.14136, 2025](https://arxiv.org/html/2511.14136v1)*

- **The 80% failure rate is mostly eval failure.** RAND (2025) estimated 80.3% of enterprise AI projects fail to deliver business value. Most practitioners attribute this to "the model wasn't good enough" — but the more accurate diagnosis is that teams confused demos with evidence. A demo proves the agent *can* do the task once. An eval proves it does the task reliably across the real distribution of inputs. — *[RAND, via GrowthEngineer.ai, May 2026](https://growthengineer.ai/blog/how-to-evaluate-ai-agents)*

## The Move

The evaluation stack that works in production has five layers, run continuously — not as a one-time gate.

- **Define one narrow task scope first.** Do not evaluate "is the agent good?" — evaluate "does the agent complete this specific task correctly?" Scope creep in eval definition produces meaningless aggregate scores. Start with task-level evaluation; aggregate only after individual task reliability is established. — *[GrowthEngineer.ai, "How to Evaluate an AI Agent", May 2026](https://growthengineer.ai/blog/how-to-evaluate-ai-agents)*

- **Build a 50–200 trace golden set from production, not hand-crafted examples.** Mine real failure cases, real edge cases, and real user inputs. Diversity of scenario matters more than volume. Add new cases weekly. A static golden set is a snapshot of yesterday's requirements — it rots. — *[Confident AI, "Definitive AI Agent Evaluation Guide", April 2026](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)*

- **Score four axes, not one: task completion, tool selection accuracy, trajectory quality, and cost.** Task completion (did it solve the problem?) is necessary but insufficient. Tool selection accuracy (did it call the right tool with the right arguments?) catches a distinct failure mode. Trajectory quality (did it take a reasonable reasoning path?) catches over-engineering and loop behavior. Cost per task keeps the business case honest. — *[GrowthEngineer.ai, 2026](https://growthengineer.ai/blog/how-to-evaluate-ai-agents)*

- **Run pass^k, not pass¹.** Execute each eval case 3–8 times and measure consistency. A pass¹ of 80% that drops to 40% at pass⁸ tells you the agent is unreliable — it will fail your users unpredictably. Gate on pass^k consistency, not single-run pass rate. — *[Sierra AI τ-bench, 2024](https://sierra.ai/blog/benchmarking-ai-agents); [arXiv:2511.14136, 2025](https://arxiv.org/html/2511.14136v1)*

- **Gate merges on eval pass thresholds in CI.** Every PR that touches prompts, tools, or orchestration should run the golden eval suite. A score that drops below threshold blocks the merge. This is the only way to catch regressions before production — a 94% score last month means nothing if today's change broke 12 edge cases. — *[Confident AI, 2026](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)*

- **Calibrate LLM-as-judge with human review on a 5% sample.** LLM-as-judge scales evaluation but drifts — it is notoriously poor at numeric scoring and has positional biases (prefers the first or last answer in pairwise comparison). Run human rubrics on a small random sample of traces monthly. If human-judge correlation drops below 80%, recalibrate the judge prompt or switch the judge model. Ensemble judging (multiple judge models, weighted consensus) stabilizes scores further. — *[Confident AI, 2026](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide); [Reddit r/LocalLLaMA, "Exploring the Limitations of LLMs-as-a-Judge", 2024](https://www.reddit.com/r/LocalLLaMA/comments/1afu08t/exploring_the_limitations_of_llmsasajudge/)*

## Evidence

- **Research paper (τ-bench):** GPT-4o achieves <50% pass¹ and <25% pass⁸ on retail customer-service tasks with real API tools and policy constraints. All tested models (including Claude) showed significant reliability degradation across multiple attempts. — *[Sierra AI / Stanford, "τ-Bench: A Benchmark for Tool-Agent-User Interaction", June 2024](https://arxiv.org/abs/2406.12045)*

- **Enterprise research (CLEAR framework):** Agents optimized purely for accuracy cost 4.4–10.8x more than Pareto-efficient alternatives. The CLEAR evaluation framework (cost-efficiency, reliability, accuracy, operational stability) correlated at ρ=0.83 with production success vs. ρ=0.41 for accuracy-only metrics. — *[arXiv:2511.14136, "Beyond Accuracy", 2025](https://arxiv.org/html/2511.14136v1)*

- **Practitioner framework:** GrowthEngineer.ai's 5-step framework (define scope → build golden set → score 4 axes → run in CI → gate on threshold) is deployed in production at multiple SaaS companies. The core principle: "Skip any step and you are shipping vibes-based evals into production." — *[GrowthEngineer.ai, May 2026](https://growthengineer.ai/blog/how-to-evaluate-ai-agents)*

## Gotchas

- **Benchmarks measuring task completion ≠ measuring production reliability.** τ-bench pass¹ of ~65% for GPT-4o looks borderline acceptable until you see pass⁸ drops to ~25%. Always run multi-attempt consistency checks — production users will retry, and inconsistent agents erode trust faster than consistently-wrong agents.

- **Golden sets rot.** A golden set that isn't updated weekly becomes a liability — it measures whether the agent matches old requirements, not current ones. Build the data pipeline to add production failures to the golden set automatically.

- **LLM-as-judge has known biases that will silently corrupt your eval.** Position bias (favoring first or last answer), length bias (longer answers score higher), and numeric range insensitivity are well-documented. Calibrate against human judgment before trusting the scores to gate production.

- **Cost is the eval metric nobody tracks until the bill arrives.** A 50x cost variation for equivalent accuracy is common in agentic stacks. Track cost per task in the same trace you use for quality — not in a separate FinOps dashboard where it won't influence eval decisions.
