# S-2727 · The Agent Eval Stack — When You Don't Know If Your Agent Is Getting Better or Worse

You've shipped three model upgrades, pushed five prompt changes, and fixed two tool schemas. Revenue is up slightly. But you have no idea if the agent is actually improving, regressing on edge cases, or silently failing in production while looking fine in your head. This is the evaluation gap: the inability to measure what you built.

## Forces

- **Agents are non-deterministic.** Unlike deterministic code, you can't assert `response == expected`. You need metrics that capture semantic correctness, relevance, and trajectory quality — not just exact-match strings.
- **Evals are time-consuming to build and easy to forget.** When under deadline pressure, evals are the first thing to get cut. But without them, you can't tell if the latest "improvement" broke something two layers deep.
- **Standard benchmarks don't map to your domain.** SWE-bench, GAIA, WebArena are useful signals about frontier capability, but your agent does something specific that no benchmark captures.
- **Evaluation is undervalued.** People who can design good evals make more money in post-training roles — so eval teams are perpetually under-resourced, even at companies with production agents.
- **The right eval is somewhere between a unit test and a performance review.** Too simple (exact-match) and you miss what matters. Too complex (full LLM-judge) and you get expensive, noisy signals.

## The Move

Build a layered evaluation system with three tiers, run continuously in CI:

### Tier 1 — Trajectory Metrics (the agent's entire execution trace)

Run every agent task through metrics that inspect the full ordered sequence of reasoning steps and tool calls, not just the final output.

- **`TaskCompletionMetric`** — Did the agent actually complete the assigned task? Checks end state against expected outcome.
- **`StepEfficiencyMetric`** — Did the agent waste steps on redundant operations? Flags unnecessary loops or repeated tool calls with the same arguments.
- **`PlanQualityMetric`** — Given a complex task, did the agent form a coherent plan before acting? Catches agents that react instead of planning.
- **`Tool Call Accuracy`** — Did the agent select the right tool AND pass the right arguments? Agents often pick the right tool but pass malformed arguments — a failure mode unit tests won't catch.

### Tier 2 — Component-Level Metrics (individual spans)

Evaluate specific parts of the agent pipeline independently so regressions can be localized.

- **`AnswerRelevancyMetric`** — Does the final response actually address the user's query? Reject verbose outputs that sound right but dodge the question.
- **`FaithfulnessMetric`** — Does the agent's output stay grounded in its retrieved context? Catch hallucinations that emerge from long context windows.
- **`HallucinationMetric`** — Explicitly detect fabricated claims, references, or data that the agent invented.
- **`ToxicityMetric`** / **`BiasMetric`** — Safety guardrails for agents operating in regulated domains.

### Tier 3 — LLM-as-a-Judge (holistic quality assessment)

Use a separate, typically stronger LLM to evaluate agent outputs holistically — especially useful for open-ended or subjective quality dimensions that rules-based metrics can't capture.

- **Structured rubric** — The judge LLM receives a specific scoring rubric, not open-ended instructions. Vague judge prompts produce unreliable scores.
- **Explainable verdicts** — Require the judge to return reasoning alongside the score so failures can be investigated, not just flagged.
- **Avoid self-judging** — Don't use the same model being evaluated as the judge; this creates circular validation.

### Practical Evals Infrastructure

- **Start broad, then narrow.** Begin with a large diverse eval set (hundreds of cases), then consolidate to a smaller subset tightly tied to your specific features and roadmap milestones.
- **Dual-role: gatekeeper AND signal.** Some evals gate production deploys (hard fail = don't ship). Others are warning lights (soft decline = investigate before shipping).
- **Run in CI, not just pre-release.** Every prompt change, model upgrade, and tool schema modification should trigger the eval suite. This is the only way to catch regressions before users do.
- **Custom > benchmark.** External benchmarks (SWE-bench, GAIA) give you a reference point for frontier capability. Your custom eval set, built from real production failures and user complaints, gives you signal about your specific agent.

## Evidence

- **HN discussion, "Principles for production AI agents" (Jul 2025, 128 pts):** A former eval suite owner described evals as "non-negotiable" — a prompt tweak that passed a vibe check failed the full eval suite every time. Teams without robust evals "don't know if they're moving the needle at all." — [HN #44712315](https://news.ycombinator.com/item?id=44712315)
- **Cleanlab "AI Agents in Production 2025" survey (n=95 engineering leaders, Aug 2025):** 63% of teams with production agents plan to improve observability and evaluation in the next year — the most-cited investment priority. Only 5% of all respondents had agents live in production. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **NVIDIA Technical Blog, "AI Agent Evaluation" (May 2026):** Contrasts model eval (MMLU, GSM8K, HumanEval) with agent eval (Task Success Rate, Tool Call Accuracy, Trajectory Efficiency). Notes that agent eval benchmarks include GAIA, SWE-bench, and WebArena — each with distinct strengths and known reproducibility limitations. — [developer.nvidia.com](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)
- **Thomas I. Liao, "Why Are There So Few Independent Eval Startups?" (May 2025):** Documents that eval talent asymmetry means people who can design good evals generate orders-of-magnitude more value in post-training roles. Frontier eval performance doesn't transfer across domains — the same model leading on DeepSWE trails on FrontierCode. — [thomasliao.com/eval-startups](https://thomasliao.com/eval-startups)
- **DeepEval open-source framework (17.6k stars, Apache-2.0):** Provides 50+ research-backed metrics specifically for agentic evaluation, including trajectory-level (PlanQuality, StepEfficiency) and component-level (Hallucination, Faithfulness) metrics, with native CI/CD integration via Pytest. — [github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)

## Gotchas

- **Don't rely on exact-match assertions.** This is the beginner mistake. If you write `assert response == "..."`, your eval suite will fail on every paraphrasing, even when the answer is correct. Use semantic metrics that compare meaning, not tokens.
- **Don't self-judge.** Using the same model being evaluated as the judge is circular — it will always rate itself generously. Use a separate, typically stronger model.
- **Don't skip the eval on deadline.** This is the most common failure mode. The eval you skip before a deploy is the one that would have caught the regression. Gate production deploys on eval pass/fail, not just human review.
- **Benchmarks are a floor, not a ceiling.** A high SWE-bench score means your coding agent is competitive on GitHub issues — it says nothing about whether your agent handles your specific tool schema, your domain edge cases, or your users' actual failure modes. Build custom evals from your production logs.
- **Judget prompts drift.** An LLM-as-a-judge that scores 8/10 today might score 6/10 next month if the judge model's behavior changed (model update, temperature shift). Anchor judge rubrics to concrete behavioral descriptions, not abstract quality concepts.
