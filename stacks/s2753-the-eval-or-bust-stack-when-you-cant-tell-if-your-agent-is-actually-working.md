# S-2753 · The Eval-or-Bust Stack — When You Can't Tell If Your Agent Is Actually Working

When your agent ships to production and nobody can say whether it's succeeding. When "it looks right" is your only signal. When a bug runs silently for three weeks before someone notices.

## Forces

- **Evaluation quality vs. evaluation cost.** Human evaluation is the gold standard (74% of production deployments rely on it per MAP 2026), but it doesn't scale — humans get fatigued, inconsistent, and expensive at volume.
- **Final-output scoring vs. trajectory scoring.** Most teams grade only the final answer, but agents produce multi-step executions where intermediate steps carry independent failure modes that final-output checks never catch.
- **Agent non-determinism.** The same input can produce different trajectories across runs. A single eval run is nearly useless — you need distribution over trials.
- **LLM-as-judge reliability.** Correlation with human scores varies wildly by task type and rubric quality. A bad rubric produces confident wrong scores.
- **What "done" even means.** Task completion, trajectory quality, tool use correctness, and output quality are four distinct dimensions — conflating them leads to agents that optimize the wrong thing.

## The Move

Measure agent quality at the right granularity, with the right methods, at the right stage. The core move is **multi-level grading with production feedback loops**:

- **Grading at the right level of the trace.** Tool-argument validity belongs on individual tool-call observations. Task completion belongs on the root. Don't conflate them.
- **Run multiple trials per task.** Single-run evals are noise — agents are non-deterministic. The MAP study (306 practitioners, 86 deployed systems) found that production agents often produce different trajectories on identical inputs.
- **Trace → test dataset → eval → improvement, continuously.** The fastest teams capture production traces, cluster failure patterns, build targeted test cases, run evals, and use results to drive prompt/model changes.
- **Combine human eval, automated checks, and LLM-as-judge.** No single method is sufficient. Human eval catches semantic failures, automated checks catch regressions, LLM-as-judge scales at 85%+ human correlation when rubrics are detailed.
- **Track four dimensions independently:** trajectory quality (step count, unnecessary calls, loops), tool use correctness (correct tool, valid args, error recovery), task completion (goal achieved), output quality (correctness, safety, coherence).
- **Catch failure at intermediate steps, not just the output.** An agent can reach a correct-sounding conclusion through broken reasoning. Evaluate whether the logic chain holds, not just the final answer.
- **Use shadow monitoring in production.** Sample a percentage of agent outputs for human review alongside automated scoring — catches systematic failures automated checks miss.
- **Set explicit task-completion thresholds before shipping.** Don't define success post-hoc. Define acceptable failure rates per use case (e.g., <5% for customer-facing, <1% for financial transactions).

## Evidence

- **MAP Study (ICML 2026 Oral):** First large-scale systematic study of AI agents in production — 20 case studies, 306 practitioners, 86 deployed systems across 26 domains. Finds 74% of production agents rely primarily on human evaluation, 68% of agents execute ≤10 steps before human intervention, and reliability (consistent correct behavior over time) is the top development challenge. — [arXiv:2512.04123](https://arxiv.org/abs/2512.04123)
- **Anthropic Engineering (Jan 2026):** Distinguishes tasks (test cases), trials (attempts), graders (scoring logic), and transcripts (complete execution records). Recommends grading at multiple levels — final output, intermediate steps, and tool calls — with assertions that fire at the right granularity. — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Langfuse Engineering:** Four evaluation dimensions (trajectory, tool use, task completion, output quality) each require different grading approaches and live at different levels of the trace. Argues intermediate steps carry independent failure modes invisible to final-output-only scoring. — [Langfuse](https://langfuse.com/resources/engineering/ai-agent-evaluation)

## Gotchas

- **Grading only the final output misses loop detection.** An agent can call a broken tool 15 times before giving up — that never surfaces if you only check the final answer.
- **Single-run evals are almost meaningless.** Run at least 5 trials per task to capture variance. Report pass rates, not binary pass/fail.
- **LLM-as-judge correlates well with humans on structured tasks (0.85+), but degrades on subjective or safety-critical outputs.** Don't trust judge scores without spot-checking against human labels on ambiguous cases.
- **Production eval drift.** Model updates, prompt changes, and tool API changes can silently shift behavior. Re-run your eval suite on every significant change — not just on release.
- **Acceptable failure rates depend on consequences.** A 15% failure rate is fine for a draft summarizer; it's catastrophic for a financial transaction agent. Define thresholds per use case before shipping.
