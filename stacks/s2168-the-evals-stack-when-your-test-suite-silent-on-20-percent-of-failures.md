# S-2168 · The Evals Stack — When Your Test Suite Is Quiet on 20% of Failures

You ran the benchmark. The suite passed. You shipped. Three weeks in, a class of failures nobody caught shows up in production: the agent that loops on a particular tool, the one that hallucinates an API parameter and nobody noticed because the API returned a 200, the one that solves the right problem three different ways with wildly different cost profiles. The offline test suite never saw any of it. The gap between lab evaluation and production behavior runs 37% in some deployments — and the most common cause is evaluating the output, not the system.

## Forces

- **Final-answer checks hide the path.** Two agents can both "succeed" — one called three tools in order, one called fifteen tools after retrying twice with hallucinated parameters. Pass/fail is identical. The cost and risk profiles are not.
- **Offline benchmarks miss the distribution that kills you.** Lab benchmarks use clean inputs and predictable tool responses. Production serves ambiguous requests, flaky APIs, rate-limit surprises, and data drift. Industry reports cite 20–40% of regressions missed by output-only scoring.
- **LLM-as-judge has its own failure modes.** Judges are convenient but unreliable without calibration. Documented failure modes include overconfidence (judges score outputs higher than human labels would), positional bias (prefers first or last option regardless of content), length bias (longer responses score higher), and self-preference (preferring outputs from the same model family). A judge that has never been validated against human labels is not a reliable evaluator.
- **Eval tooling fragmentation is real.** LangSmith, DeepEval, AWS agent-evaluation, AgentDiagnose, RAGAS, TruLens, Braintrust, Promptfoo, Arize Phoenix, Langfuse, and custom harnesses each optimize for different surfaces. Choosing one means accepting gaps.

## The Move

Evaluate on three layers, not one. Then wire the whole thing into CI so regressions fail the build.

**Layer 1 — End-to-end outcome (did it solve the problem?)**
- Binary success/fail on the user's stated goal. The minimal starting point.
- Use production traces as the primary signal source, not synthetic test data.
- Aggregate across N runs per task to catch non-determinism.

**Layer 2 — Trajectory quality (did it get there sensibly?)**
- Check the sequence of tool calls: correct tools, correct arguments, reasonable order.
- LangGraph's `trajectory_match` does this deterministically (no LLM calls, fast, CI-friendly).
- Flag wasteful loops, unnecessary retries, hallucinated parameters, and dead ends.
- Score path efficiency: optimal steps vs. actual steps.

**Layer 3 — Per-turn correctness (was each step defensible?)**
- Score each individual step against a rubric: tool selection, argument construction, state update, error response.
- Per-turn classifiers can run at <90ms latency (one forward pass) when architected as binary or categorical models, separate from the agent's own inference.
- LangFuse and LangSmith both support per-turn annotation with span-level scoring.

**Validate your evaluator**
- Calibrate LLM-as-judge against a human-labeled golden dataset before trusting it at scale. LangChain provides `AlignEvals` for this.
- Compare judge verdicts against human labels on a held-out set. If the judge disagrees >20% of the time, do not deploy it as a gate.
- Re-calibrate periodically: evaluation drift is real as production traffic shifts.

**Wire into CI/CD, not just manual runs**
- AWS agent-evaluation explicitly targets CI integration, treating evaluation as a gate on every deploy.
- DeepEval treats evals as unit tests that run in CI and fail the build on regression.
- Set cost-per-task and latency thresholds alongside accuracy thresholds — operational constraints are first-class evaluation targets.

## Evidence

- **Engineering blog:** InfoQ's "Evaluating AI Agents in Practice" (March 2026) lays out the five-pillar framework (intelligence, performance, reliability, responsibility, user experience) and explicitly calls out that single-turn accuracy and classical NLP metrics (BLEU, ROUGE) don't capture agent failure modes — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Research paper:** An arxiv paper (2508.06225) on "Overconfidence in LLM-as-a-Judge" (2025) documents systematic overconfidence across 11 judge models including GPT-4.1, Claude Sonnet 4, and DeepSeek-R1 — finding that judges consistently inflate perceived performance by double-digit margins when not calibrated against human labels — [https://arxiv.org/html/2508.06225v2](https://arxiv.org/html/2508.06225v2)
- **Primary source:** QASkills.sh's "Agent Trajectory Evaluation Guide" (2026) describes the three-layer evaluation model (outcome + trajectory + per-turn) with specific tooling guidance for LangSmith and LangGraph, noting that offline benchmarks routinely miss 20–40% of regressions caught by trajectory analysis — [https://qaskills.sh/blog/agent-trajectory-evaluation-guide-2026](https://qaskills.sh/blog/agent-trajectory-evaluation-guide-2026)
- **Open-source tool:** Microsoft Research's Agent-Framework-Samples repo includes a dedicated evaluation module (`08.EvaluationAndTracing`) showing how DevUI and structured observability integrate into the agent development loop — [https://github.com/microsoft/Agent-Framework-Samples/blob/main/08.EvaluationAndTracing/README.md](https://github.com/microsoft/Agent-Framework-Samples/blob/main/08.EvaluationAndTracing/README.md)
- **Open-source tool:** AWS Labs `agent-evaluation` (v0.4.1) is designed from the ground up as a CI/CD-native evaluation harness for agent targets including Amazon Bedrock and Amazon Q, treating evaluation as a deployment gate — [https://awslabs.github.io/agent-evaluation/](https://awslabs.github.io/agent-evaluation/)
- **HN discussion:** "Evaluating Agents" thread on HN (Sept 2025, 42 points) surfaced practitioner consensus that starting with end-to-end success criteria (binary yes/no per task) is the minimum viable eval, and that human trace review remains irreplaceable — [https://news.ycombinator.com/item?id=45121547](https://news.ycombinator.com/item?id=45121547)

## Gotchas

- **Golden datasets expire.** Production traffic shifts, user intent drifts, and tool behavior changes. A golden dataset from six months ago may not reflect the distribution your agent actually faces. Refresh test sets from live production traces, not static seed data.
- **Synthesized test cases miss distribution.** Teams often write happy-path test cases and call it coverage. Real production failures cluster at edge cases, tool combinations, and error recovery paths — all of which require failure-mode-first test design, not success-path-first.
- **Tool-call verification is structural, not semantic.** A regex match on tool names catches typos but not logical errors: the agent calls the right tool with the wrong parameters. For that you need semantic validation — does the argument structure match what the tool schema expects? Does the value fall in the expected range?
- **Cost and latency are evaluation targets, not afterthoughts.** An agent that solves 90% of tasks but costs $4.50 per task (when a 92% solution costs $0.12) is a production failure. Track cost-per-task and token efficiency as first-class metrics, not post-hoc analysis.
