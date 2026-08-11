# S-2452 · The Eval Gap Stack — When Your Agent Succeeds on Benchmarks and Fails in Production

Your agent scores 87% on SWE-bench. Your integration tests pass. You ship to production and discover it hallucinates ticket IDs on empty inputs, loops on null values, and approves a $47K fraudulent refund via prompt injection. The benchmark told you the agent was good. Production told you it was lying.

## Forces

- **Research benchmarks are retrospective; production is emergent.** Benchmarks like SWE-bench, WebArena, and OSWorld curate tasks from completed artifacts with well-specified requirements. Production tasks emerge from evolving business needs with implicit constraints that benchmarks never encode. A 2025 survey of 27 AI product companies found 63% have low confidence that model updates actually improve their products — they lack the signal to know.
- **Outcome metrics miss the process.** Traditional evals score the final output. But agents think step-by-step, and a wrong intermediate step can produce a plausible-sounding correct answer. A score of "refund approved" doesn't distinguish between a correct decision and a hallucinated one that happens to look right.
- **LLM-as-judge has a circularity problem.** When the judge model is the same family as the evaluated model, it tends to reward patterns typical to that family rather than actual correctness. Practitioners on HN have noted they have never seen empirical evidence that LLM-as-critic actually correlates with real-world performance.
- **Most teams evaluate as a side task.** 70.4% of companies rely on developers doing evaluation as a secondary responsibility. Only 25.9% have explicit evaluation criteria. Without a structured eval system, you don't know if a prompt change helped or hurt until production breaks.

## The move

Build a production-grade eval system that evaluates process, not just outcomes, using a three-layer approach:

- **Layer 1 — Outcome traces with trajectory recording.** Instrument every agent run to capture the full execution trace: tool calls, intermediate outputs, decision points, and final outputs. Store traces alongside ground-truth outcomes. This is the raw material for all downstream eval. AWS Labs' Agent Evaluation framework (370 stars, Apache-2.0) provides an open-source harness purpose-built for this, with adapters for LangChain, LangGraph, AutoGen, CrewAI, and custom agents.
- **Layer 2 — Process-aware evaluators.** Move beyond final-answer scoring. Evaluate each step of the agent's reasoning. The Agent-as-a-Judge paradigm (Zhuge et al., ICML 2025) equips the evaluator with tool use and multi-step reasoning so it can provide intermediate feedback throughout the task-solving process — evaluating how the agent thinks, not just what it outputs. CourtEval (Kumar et al., 2025) structures this further with three roles: Grader (Judge), Critic (Prosecutor), and Defender, so the evaluation process itself is adversarial and multi-perspective.
- **Layer 3 — Failure-mode test suites.** Run targeted test cases for the specific failure modes that production exposes: Unicode edge cases (O'Brien, José, 北京), null/empty field handling, concurrent request races, context window exhaustion behavior, silent tool errors that return 200 OK with empty data, and prompt injection vectors. The Ask HN thread on testing AI agents (harperlabs, 2026) identified 7 core failure modes with a 50+ test case suite covering categories most teams never systematically test.

## Evidence

- **Survey:** 27 AI product companies — 63% low confidence in model update signal, 25.9% no explicit eval criteria, 70.4% eval as developer side-task. — AlphaEval (arXiv:2604.12162, Lu et al., SII/MiraclePlus/SJTU/GAIR, 2026) — [https://arxiv.org/pdf/2604.12162](https://arxiv.org/pdf/2604.12162)
- **Research benchmark vs production gap:** Existing benchmarks (SWE-bench, WebArena, OSWorld) use retrospective task curation with deterministic metrics. AlphaEval tested 94 real-world tasks across 7 partner companies and found the best result (Claude Code + Opus 4.6) at 64.41/100 — with economic value range of $154K–$231K USD. — AlphaEval (arXiv:2604.12162) — [https://arxiv.org/pdf/2604.12162](https://arxiv.org/pdf/2604.12162)
- **Agent-as-a-Judge outperforms LLM-as-Judge:** ICML 2025 paper benchmarks three top code-generating agentic systems using Agent-as-a-Judge. The framework dramatically outperforms LLM-as-a-Judge and reaches reliability comparable to human evaluation baseline. — Zhuge et al., ICML 2025, Meta FAIR / Amazon / Nankai University / AGI Reeves — [https://proceedings.mlr.press/v267/zhuge25a.html](https://proceedings.mlr.press/v267/zhuge25a.html)
- **Real-world failure mode data:** Prompt injection in a customer support agent processed a $47,000 fraudulent refund (January 2026 incident, cited in Ask HN thread). Most teams test hallucination and prompt injection but almost none systematically test context limits, cascade failures, or data integration drift. — harperlabs, Ask HN thread on AI agent testing — [https://news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **Production eval infrastructure:** AWS Labs Agent Evaluation — framework-agnostic eval harness with 370 GitHub stars, CI/CD integration, built-in evaluators for Amazon Bedrock, Bedrock Knowledge Bases, Amazon Q Business, and SageMaker endpoints. — AWS Labs (Apache-2.0, 276 commits) — [https://github.com/awslabs/agent-evaluation](https://github.com/awslabs/agent-evaluation)

## Gotchas

- **Benchmark scores are ceiling estimates, not production predictions.** An 87% SWE-bench score means the agent solves 87% of curated historical bugs. It says nothing about how it handles your specific business logic, your data quirks, or your users' adversarial inputs.
- **LLM-as-judge is better than nothing but worse than it sounds.** The HN practitioner debate on this was clear: it's useful for rapid iteration but lacks empirical correlation with real-world performance. Treat it as a smoke test, not ground truth.
- **Silent failures are the worst failures.** A tool call that returns HTTP 200 with an empty result is structurally identical to a successful call. Your monitoring must distinguish between "the API worked" and "the API returned correct data."
- **Eval is not a one-time gate.** Production agents evolve with prompts, tools, and model versions. Your eval suite must run continuously in CI/CD, not just at deployment time. AWS Labs' framework explicitly targets CI/CD pipeline incorporation.
