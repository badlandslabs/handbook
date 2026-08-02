# S-1998 · The Agent Evaluation Stack — Measuring What Your Agent Actually Does

*When you ship an agent and have no idea whether it's actually completing tasks, drifting off-goal, or silently failing on step 3 of 7. Model benchmarks pass. Production breaks. You need a way to measure the trajectory, not just the output.*

## Forces

- **Agents fail differently than models.** A model can ace MMLU and still fail a multi-step refund workflow because it loses state after six tool calls or calls the wrong API. Benchmarks test the model; they don't test the system.
- **The output is the last step of a trajectory.** Evaluating only the final answer misses failed tool calls, wrong tool selection, goal drift, silent recovery, and inefficient paths — the modes where agents actually fail in production.
- **Deterministic checks don't generalize.** Exact-match assertions work for tool names and argument formats, but not for reasoning quality, tone, or whether a recovery was appropriate — the things that actually matter for task success.
- **Evaluation without traces is guessing.** Without observability into the agent's execution path, you can't reproduce failures, find regressions, or identify which component broke.

## The Move

Measure agent quality at three levels: end-to-end (did the task complete?), trajectory (was the path sound?), and component (which tool or reasoning step failed?). Combine deterministic checks for exact behavior with LLM-as-judge for qualitative assessment, and always trace every run.

**Trace first.** Instrument every agent run to capture the full execution graph — tool calls, arguments, intermediate outputs, and the final result. Traces are the prerequisite for every other eval. Without them, you can't reproduce failures or find regressions. Tools like LangSmith, Langfuse (open-source), Phoenix (Arize), and Voker provide drop-in SDK instrumentation for this.

**Evaluate at three levels:**
1. **End-to-end** — Did the agent achieve the goal? Binary or graded. This is your primary signal.
2. **Trajectory-level** — How many steps did it take? Was replanning needed? Did it drift from the original goal? Inefficiency here is where cost explodes.
3. **Component-level** — Did it call the correct tool? With correct arguments? Did reasoning chains stay coherent? This isolates failures for targeted fixes.

**Use deterministic checks for exact things.** Tool name, argument types, argument format, output schema. These are fast, reproducible, and don't hallucinate. Run them in CI.

**Use LLM-as-a-judge for qualitative things.** Reasoning quality, recovery appropriateness, response tone, whether a multi-turn conversation stayed on-topic. Chain-of-thought prompting and a separate judge model reduce bias.

**Track operational constraints as first-class metrics.** Latency per span (tool call vs. model response vs. retry loop), cost per task, token efficiency, tool reliability rate. A technically correct agent that takes 45 seconds per task isn't production-viable.

**Use synthetic data for offline evaluation.** Run the agent through simulated scenarios (LLM-generated or rule-based) before shipping. Shopify's Sidekick uses a simulator for offline evals alongside production traffic analysis. Golden datasets — hand-labeled input/output pairs for critical paths — catch regressions in CI.

**Sample human review from production traces.** Automated evals catch known failure modes. Human review catches the ones you haven't thought of yet. Randomly sample 1–5% of production traces for human scoring. A correction event in a trace (user or system overrule) is a high-signal flag for manual review.

## Evidence

- **Company Engineering Post:** Shopify's Sidekick evolved from tool-calling to full agentic loop, using LLM-as-judge for evaluation, a simulator for offline evals, and production trace analysis. Presented at ICML 2025. — [shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **Company Engineering Post:** Klarna's AI assistant handled 2.3M customer conversations in month one (equivalent to 700 full-time agents), reduced response time from ~11 minutes to ~2 minutes, and reported $10M+ annual savings — but rollout challenges surfaced real production gaps. — [prefactor.tech](https://prefactor.tech/blog/agent-evaluation-in-production-what-to-measure-and-how-to-prove-it) citing [Klarna 2024 annual report](https://www.klarna.com/international/press/)
- **Analyst Report:** Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps. — [thinking.inc (2026)](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/) citing Gartner "AI Risk Management Predictions," 2026
- **Open-source Framework:** DeepEval (17K+ GitHub stars) is the most-starred open-source LLM evaluation framework, model-agnostic, CI/CD-native, and built around trace-based evals with LLM-as-judge support. — [github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)
- **Product Launch:** Voker (YC S24) — analytics platform specifically for AI agents, instrumenting sessions/corrections/resolution metrics via drop-in SDK. Surfaced that agents fail differently than stateless API calls: a helpful response on turn 3 that corrects a mistake from turn 2 never surfaces in conventional LLM monitoring. — [HN Launch](https://news.ycombinator.com/item?id=48109962)
- **Industry Survey:** InfoQ analysis of agent evaluation in practice — classical NLP metrics (BLEU, ROUGE) score static text, not agent trajectories. Hybrid evaluation combining automated scoring and human judgment is non-negotiable. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Tooling Ecosystem:** MLflow v3.0+ (experiment tracing + LLM judge), TruLens (pluggable feedback + OpenTelemetry), LangSmith (trace visualization + eval pipelines), Langfuse (open-source tracing), Phoenix + Ragas (agent evaluation metrics). — [infoq.com](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

## Gotchas

- **Golden datasets go stale.** Agent behavior changes with model updates, prompt changes, and tool changes. Re-annotate golden datasets regularly, or they'll give false confidence.
- **Regressions hide in stochasticity.** Models are non-deterministic. A scenario that passed once may fail three runs later. Re-run critical test cases across multiple seeds.
- **Tracing adds latency.** Instrumenting every call in production adds overhead — measure it. Use sampling (e.g., 10% of calls) for high-volume paths and 100% for critical workflows.
- **LLM-as-a-judge has judge bias.** The judge model can be too lenient, too harsh, or systematically biased toward certain response styles. Calibrate against human scores periodically.
- **Single-pass eval misses drift.** An agent can succeed on step 1–6 and fail on step 7. Evaluate every step boundary, not just the final output.
- **Cost per task is a quality signal.** A cheap agent that fails and retries 12 times is worse than an expensive agent that gets it right the first time. Track cost alongside quality.
