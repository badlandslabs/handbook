# S-869 · The Trajectory Blind Spot Stack — When Your Agent Succeeds but Only Once

You ship an agent that works perfectly in demos. You put it in production and it succeeds 60% of the time on a good day, 22% when a tool URL is stale, and 46% when it accidentally calls localhost in a cloud container. Your monitoring says nothing is wrong. The agent is producing outputs — they're just wrong. You have a trajectory blind spot: you are measuring the destination, not the path.

## Forces

- **Outcome metrics are the floor, not the ceiling.** Success/failure at end-of-task hides whether the agent got there by reasoning or by accident. A wrong answer corrected by a downstream step still registers as success.
- **Single-run scores lie about reliability.** Production agents averaging 60% success on individual runs drop to ~25% across 8 consecutive runs — a variance that outcome-only dashboards never surface. (Galileo AI Labs, "Agent Evaluation Framework," Jul 2026 — https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **System failures masquerade as model failures.** An HN practitioner's benchmark run found broken tool URLs (score: 22), localhost calls in cloud containers (stuck at 46), real CVEs flagged as hallucinations (eval design flaw), and Reddit blocking requests — all registered as "agent failures" when the model was working correctly. (Hacker News, "What broke when I tried to evaluate an AI agent in production" — https://news.ycombinator.com/item?id=47416033)
- **The lab-to-production gap is structural, not noise.** AWS research on multi-agent systems found 90% goal success in lab coordination conditions vs. 53-60% for single agents — but the same study documented a 37% performance drop moving to production, driven by task distribution shift, scaffold dependency, and environment contamination. (Amazon/AWS, "Evaluating AI agents: Real-world lessons from building agentic systems at Amazon," Feb 2026 — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Domain-specific agents dramatically outperform general ones.** Empirical evidence shows domain-specific agents achieving 82.7% accuracy vs. 59-63% for general LLMs, at 4.4-10.8x lower cost — but most teams reach for general-purpose eval harnesses that miss this distinction entirely. (Galileo AI Labs, cited research synthesis)

## The move

Build a two-layer evaluation system: trajectory telemetry beneath outcome scoring, and custom domain evals beneath public benchmarks.

**Layer 1 — Instrument the path, not just the result.**
- Log every tool call with inputs, outputs, and latency. Every retrieval with query and top-k results. Every reasoning turn with its preceding state.
- Compute trajectory metrics: tool-call accuracy (did it pick the right tool?), retrieval recall (did it find the right context?), step efficiency (did it converge in minimum turns?), and recovery rate (did it self-correct after a failure?).
- These are leading indicators. A drop in tool-call accuracy precedes a drop in outcome success by 2-3 days.

**Layer 2 — Separate the eval of the model from the eval of the scaffold.**
- The agent framework (LangGraph, CrewAI, OpenAI Agents SDK) is a scaffold. The LLM is the model. Benchmark scores like SWE-bench, WebArena, and GAIA measure the model in a controlled harness — but your scaffold introduces drift that benchmarks cannot detect.
- Run a shadow eval: the same prompt with the same model but without your scaffold's tool-wrapping and state management. If the shadow succeeds and the scaffolded version fails, the scaffold is the problem.
- Public benchmarks are useful for elimination (ruling out clearly unsuitable models) but not for selection (they predict 20-40 percentage points below production performance). (Benchmarking Agents Review, "AI Agent Benchmarks," Apr 2026 — https://benchmarkingagents.com/agent-benchmarks/)

**Layer 3 — Target 0.80+ Spearman correlation for LLM-as-judge, then validate it quarterly.**
- LLM-as-judge (using a stronger model to score agent outputs) is the practical workhorse for production evals. The goal is 0.80+ Spearman correlation with human judgment — below that, the judge introduces more noise than signal.
- Validate the judge against a human-annotated sample every quarter. Model updates shift the correlation; a judge calibrated on GPT-4o may not hold for Claude 4.5.
- Use a rubric. A 7-dimension → 25-sub-dimension → 130-item taxonomy is the recommended depth for production agents with complex tool chains. (Galileo AI Labs, Jul 2026)

**Layer 4 — Build a custom golden dataset for your domain.**
- Public benchmarks saturate at the frontier — top models cluster within 5 points on SWE-bench Lite. For production decisions, a 50-100 example custom dataset drawn from your actual task distribution outperforms any public benchmark.
- Start with 20 examples of known failures (regression cases) and 20 of known successes. Expand with production trace anomalies. This is your eval corpus.
- CI/CD triggers: run evals on every commit touching agent code, on a scheduled cadence (nightly or weekly), and event-driven on model changes.

## Evidence

- **HN Practitioner post:** "What broke when I tried to evaluate an AI agent in production" — systematic breakdown showing 4 categories of non-model failures detected by eval design. — https://news.ycombinator.com/item?id=47416033
- **Amazon/AWS engineering blog:** "Evaluating AI agents: Real-world lessons from building agentic systems at Amazon" — 2-component framework (generic workflow + AgentCore Evaluations library), 90% lab vs. 53-60% production gap, tool selection accuracy and retrieval coherence as first-class eval dimensions. — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon
- **Galileo AI Labs:** "Agent Evaluation Framework" (Jul 2026) — 60% single-run / 25% multi-run reliability gap, 3-tier rubric taxonomy, LLM-as-judge Spearman targeting, 40% project cancellation prediction from Gartner. — https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks
- **Benchmarking Agents Review (Apr 2026):** "AI Agent Benchmarks" — SWE-bench, WebArena, GAIA landscape with pass@1 rates, benchmark-to-production gap (20-40pp), benchmark saturation at frontier. — https://benchmarkingagents.com/agent-benchmarks/

## Gotchas

- **Counting passes ≠ measuring reliability.** pass@1 on a benchmark is not the same as production reliability. The 8-run variance study proves this — a single-run pass rate is a best-case measurement, not a median.
- **Scaffold drift is invisible to model benchmarks.** When you update LangGraph, CrewAI, or your tool definitions, public benchmark scores don't change but your production behavior does. Shadow evals catch this; benchmarks cannot.
- **LLM-as-judge has a correlation decay problem.** Judge calibration is not a one-time setup — model updates, prompt changes, and even temporal drift (the same judge on the same output can score differently weeks apart) degrade correlation. Treat the judge as a system that needs its own CI/CD.
- **Golden datasets rot.** Production task distributions shift. A golden dataset built in Q1 2026 may not represent Q4 2026 workloads. Schedule quarterly refresh from production trace samples, not just manual curation.
- **Overhead manipulation reveals true capability.** One study found a 40% performance drop when removing scaffolding from guidance — meaning the scaffold was doing 40% of the work. If your eval doesn't test the unscaffolded baseline, you don't know how much the scaffold contributes vs. the model.
