# S-1721 · The Human-in-the-Loop Floor Stack — When Your 74% Human Eval Dependency Becomes a Scaling Bottleneck

You've been shipping agent improvements for three months. Every sprint you tweak prompts, swap models, adjust tool definitions. But you're flying blind — your evaluation is a gut check, a Slack message asking someone to "take a look," and a vague sense that things are better than last week. This is the dominant state of production agent development: **74% of deployed agent systems rely primarily on human evaluation** (MAP study, IBM/Berkeley/Stanford, ICML 2026). It's not a failure of discipline. It's the right instinct — but it hits a wall when agents need to ship daily.

## Forces

- **The benchmark illusion** — MMLU, HumanEval, and other static benchmarks tell you what a model knows, not whether your agent survives a production interaction. Genαi (2026) puts it bluntly: "MMLU tells you what a model knows. It tells you almost nothing about whether your agent will survive production."
- **Human eval doesn't scale** — 74% of teams use it, but human reviewers become the bottleneck when you're iterating daily. The MAP study found reliability is the #1 challenge teams face in production.
- **Synthetic evals hallucinate success** — LLM-as-judge can be gamed and carries the base model's biases. HN practitioners note it works for alignment but "less well for capability improvements."
- **The telemetry gap** — Production telemetry (error rates, cost, step counts) is measurable but doesn't tell you *why* the agent failed. You need behavioral signals.
- **Evaluation drift** — Without a stable eval suite tied to specific features, teams can't distinguish real improvement from noise. One HN practitioner who owned eval for a coding agent: "Less evals tied more closely to specific features and product ambitions."

## The move

Build a **layered eval stack** that starts lean on human judgment and progressively automates it:

- **Smoke tests** — Run a curated set of 10-20 known task cases automatically after every change. These are deterministic enough to pass/fail without judgment. They catch regressions, not capability gaps.
- **Capability benchmarks** — Task-specific test suites (e.g., customer reply quality, code review coverage) that score on defined dimensions. Genαi recommends scoring on: task completion rate, tool call precision, revision rounds needed, cost per task, and error recovery rate.
- **LLM-as-judge** — Use a separate, stronger model to score outputs on defined rubrics. Tie it to specific product dimensions, not generic quality. Effective for catching regressions in alignment; less reliable for capability improvement. Run it on a sampled subset, not every interaction.
- **Human review on sampled traces** — Keep human eval but scope it to a weekly sample of production traces (e.g., randomly sample 5% of agent runs). This gives you signal on what the automated layers miss: tone, context understanding, edge cases. This is your floor, not your ceiling.
- **Production telemetry** — Track step counts, tool call success rates, error types, cost per session, and session length continuously. The MAP study found 68% of production agents execute ≤10 steps before human intervention — use your telemetry to find where your agents consistently stop or loop.
- **Regression guardrails** — Block deploys if key smoke tests fail. Use the eval suite as a gate in CI, not just a report. This is what separates "teams with evals" from "teams whose evals matter."

## Evidence

- **MAP study (ICML 2026 Oral):** First systematic study of agents in production — 20 case studies, 86 deployed systems across 26 domains. Found 74% of production agents rely primarily on human evaluation, 70% use prompting over fine-tuning, 68% execute ≤10 steps before human intervention. — [arXiv:2512.04123](https://arxiv.org/abs/2512.04123)
- **Genαi (June 2026):** Documents layered eval architecture for agents: smoke tests → capability benchmarks → LLM-as-judge → human review on traces. Notes that "86% of agent failures are recoverable" (Gartner) and that reliability is addressed through systems-level design, not model improvements. — [genalphai.com](https://genalphai.com/beyond-llm-benchmarks-evaluating-ai-agent-intelligence-in-2026)
- **HN discussion on production AI agents (128 points):** Practitioners confirm evals are essential: "If you don't have evals, you really don't know if you're moving the needle at all." Key insight: fewer evals tied to specific features beat comprehensive eval suites that don't map to product ambitions. — [HN #44712315](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **Evals drift from product** — An eval suite that doesn't track specific product ambitions becomes theater. Start with 5-10 evals tied to the features you care about; add more only when you have evidence they predict real-world success.
- **LLM-as-judge is not ground truth** — It can be consistent without being correct. Use it to catch regressions in known dimensions, not to discover new failure modes.
- **Telemetry without analysis is noise** — Step counts and cost metrics only matter when correlated with outcome quality. Track whether agents that take more steps actually produce better results.
- **Human eval without structured rubrics is noise** — "Does this look good?" produces inconsistent signals. Use defined criteria (task completion, tone, factual accuracy) with explicit rating scales.
- **Eval coverage ≠ eval quality** — A suite of 200 generic tasks is worse than 15 well-designed domain-specific ones. Quality of signal matters more than volume.
