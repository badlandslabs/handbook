# S-1485 · The Eval Gap — When Your Agent Passes All Tests and Still Fails in Production

Your agent scores 94% on your internal eval suite. You ship it. Two days later, a user reports that the agent stopped handling refund requests correctly. Most of the next day goes to bisecting changes to figure out which edit broke it. Your eval suite gave you a green score and zero signal about what actually broke.

The eval gap is real: standard benchmarks measure task completion, not reliability, cost efficiency, safety, or long-horizon competence. Teams that deploy agents without a behavioral eval layer are flying blind.

## Forces

- **Task success ≠ production quality.** An agent can "complete" a task by doing it the wrong way — skipping steps, hallucinating outputs, or crashing gracefully and returning nothing. Static pass/fail scores miss all of this.
- **Agents are stochastic systems.** Given the same input, an LLM-powered agent may produce different tool calls, different reasoning chains, and different outputs. Traditional unit tests assume determinism.
- **Benchmarks are exploitable.** UC Berkeley researchers examined eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all eight could be gamed to near-perfect scores without genuinely solving the underlying tasks.
- **Eval engineering is its own discipline.** The same skills needed for good evals — dataset curation, rubric design, judge calibration — are valuable elsewhere. Teams often underinvest until something breaks in production.
- **Calibration drift compounds.** LLM-as-judge models are updated over time, causing evaluation scores to shift even when the evaluated agent hasn't changed.

## The move

Treat eval engineering as load-bearing infrastructure, not an afterthought. Build a multi-layered eval system that combines end-to-end behavioral checks, component-level tool verification, and continuous trace monitoring.

**Structural layers:**

- **Behavioral evals (end-to-end):** Run the agent through realistic scenarios and measure outcomes — not just "did it call the right tool" but "did it produce a correct, safe, useful result." Use LLM-as-judge for open-ended quality and deterministic checkers (schema validators, compilers, test suites) wherever possible — deterministic checkers are always preferred over LLM judges when available.
- **Component-level checks (tools, arguments, handoffs):** Verify that each tool call has correct arguments, correct ordering, and handles errors gracefully. This catches the "agent silently skips a refund when the API returns an unexpected error" failure class.
- **Trajectory analysis (step count, token budget, cost):** Track operating envelopes alongside quality. An agent that solves a task in 47 steps when 8 would suffice is a cost and latency liability.
- **Continuous trace monitoring in production:** Evals run once in CI are necessary but not sufficient. Monitor a sample of live traces, surface regressions automatically, and route "metric green, user red" cases to human review.
- **Human calibration loop:** Score a sample of traces by hand to calibrate LLM-as-judge rubrics. Judges trained on human-labeled data dramatically outperform raw judges on edge cases.
- **Regression suite as first-class artifact:** Encode critical scenario definitions as version-controlled eval cases. Re-run them on every change. Treat flaky passes (stochastic systems) by running the same scenario multiple times and tracking pass rate, not just pass/fail.

**Tooling choices in evidence:**

- MLflow (v3.0+) for experiment tracing and built-in LLM judge capabilities
- TruLens for pluggable feedback functions with OpenTelemetry integration
- LangChain Evals for task-specific evaluation chains
- DeepEval for CI-integrated component and end-to-end metrics
- AWS Agent Evaluation (awslabs/agent-evaluation, 370 stars) for production agent testing harnesses
- Confident AI for trace-level analysis and online evaluation

## Evidence

- **Research paper:** UC Berkeley examined eight prominent agent benchmarks and found all eight could be gamed to near-perfect scores without genuinely solving the underlying tasks — [arXiv:2507.21504, "Evaluation and Benchmarking of LLM Agents: A Survey"](https://arxiv.org/abs/2507.21504) (KDD '25, July 2025)
- **Research blog:** 57% of surveyed production agent teams now rely on judge LLMs at runtime for quality gating, hallucination defense, and tool-call verification; intrinsic self-correction (agent correcting itself without external feedback) is empirically unreliable across all tested architectures — [Zylos Research, "LLM-as-Judge in Production"](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/) (April 2026)
- **Engineering blog:** Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring rather than model capability gaps — [Thinking Inc, "AI Agent Evaluation in Production"](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/) (March 2026)
- **Engineering post:** MLflow (v3.0+), TruLens, LangChain Evals, and DeepEval each occupy distinct roles in a mature eval stack; eval-driven development (EDD) — encoding quality definitions as evaluations and using eval scores as the oracle — replaces bisecting by hand — [InfoQ, "Evaluating AI Agents in Practice"](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned) (March 2026)
- **GitHub:** AWS Labs agent-evaluation framework (370 stars, Apache-2.0) provides production-grade eval harness for virtual agents — [github.com/awslabs/agent-evaluation](https://github.com/awslabs/agent-evaluation)
- **HN post:** Benchmark-style evaluation failed in production in unexpected ways — an agent "completed" a task while doing it incorrectly, and trajectory analysis (step count, token usage) was the signal that caught it — ["What broke when I tried to evaluate an AI agent in production"](https://news.ycombinator.com/item?id=47416033) on Hacker News

## Gotchas

- **Verbal reinforcement learning (Reflexion-style self-correction) is unreliable as a sole safety mechanism.** Agents instructed to reflect on and correct their own errors improve on simple cases but regularly fail on complex or ambiguous ones. Treat self-correction as a useful heuristic, not a guarantee.
- **LLM-as-judge has known failure modes:** It biases toward longer outputs, struggles with factual recall, and can be gamed by prompt injection in the agent output. Calibrate judges against human-labeled samples before trusting them at scale.
- **Static benchmarks decay.** As frontier models improve, benchmark difficulty baselines shift. Re-evaluate whether your benchmarks still distinguish capable agents from capable models — this is an open research problem with no clean solution yet.
- **Operational metrics are first-class, not afterthoughts.** Latency, cost per task, token efficiency, and tool reliability determine whether a technically capable agent is viable at enterprise scale. Track them in the same traces as quality metrics.
- **Golden datasets go stale.** User behavior, API contracts, and business rules shift. Eval cases that aren't refreshed become echo chambers — measuring whether the agent still handles last quarter's scenarios, not this quarter's.
