# S-2550 · The Golden-Set Stack — When Your Agent Looks Great on Benchmarks and Terrible in Production

*You shipped a 95 on SWE-bench. Your customers report it opens the wrong Jira ticket, bills the wrong client, and does everything right except what they actually asked. Public benchmarks are not your evaluation. Your evaluation is a closed set of scenarios that represent what your agent is supposed to do — built from your own production data, owned by your own team, run every time you change anything.*

## Forces

- **Research benchmarks don't predict your domain.** SWE-bench, WebArena, and GAIA measure general agent capability on curated tasks. They tell you whether a model got better at agents in the abstract. They tell you nothing about whether your agent correctly handles your specific workflow, your edge cases, or your users' actual failure modes.
- **"It feels good" is not a regression test.** Manual vibe checks — chatting with the agent and judging by feel — are subjective, non-repeatable, and prone to confirmation bias. A prompt that feels right on 5 examples may regress silently on 500.
- **LLM non-determinism makes diffs unreliable.** The same prompt with the same model can produce different tool selections, reasoning paths, and outputs. You cannot compare two runs by eyeballing them; you need a structured rubric that produces comparable scores.
- **Synthetic benchmarks measure the research problem, not your problem.** AlphaEval (GAIR-NLP, 2026) evaluated 94 production tasks across 7 companies and found that research benchmarks have near-zero correlation with production task success — because real production tasks have implicit constraints, fragmented multi-modal inputs, and success criteria that evolve over time.
- **Evaluation is where agents actually fail in production.** Teams build the agent fine. They discover the agent doesn't work when they try to measure whether it works — and by then, they've already shipped.

## The move

Build a **tiered evaluation pipeline** with three layers, each answering a different question:

### Tier 1 — Golden Set (the floor)
A curated, labeled dataset of representative scenarios with known expected outputs or behaviors. This is your regression suite.

- **Source it from production**: mine support tickets, user feedback, and error logs for failure patterns. Add these as test cases before they become customer calls.
- **Include positive and negative cases**: both correct completions and known failure modes. A golden set that only tests happy paths is a false floor.
- **Run it in CI/CD**: every prompt change, model swap, or tool modification triggers a full golden-set run. A golden set that isn't automated is a golden set you'll forget to run.
- **Accept stochastic noise**: re-run critical tests 3–5 times and track pass rates, not single-run pass/fail. A 70% pass rate on a critical path is a 30% failure rate in production.

### Tier 2 — LLM-as-Judge (the mid-layer)
An automated judge model evaluates agent outputs against a structured rubric, scoring dimensions like accuracy, task completion, and tool selection.

- **Use 3–5 dimensions, not a single score**: aggregate scores hide which dimension failed. A score of 7/10 could mean mediocre everywhere or catastrophic in one dimension — you need to know which.
- **Calibrate against human judgment regularly**: LLM-as-judge achieves 70–85% agreement with human reviewers on well-defined rubrics (comparable to human-human agreement at 80–85%). But the judge drifts. Re-run calibration on a human-labeled sample monthly.
- **Pick judges from different model families**: combining Claude Sonnet, Nova Pro, and Nemotron judges reduces self-preference bias. A judge from the same family as the agent being evaluated will score it 10–15% higher than cross-family judges.
- **Apply to a sample of production traffic**: you cannot run LLM-as-judge on 100% of production calls economically. Sample 5–10% and track score distributions over time for drift detection.

### Tier 3 — Continuous Production Monitoring (the signal)
Real-time behavioral tracking that surfaces regressions before users report them.

- **Track behavior-level metrics, not just infrastructure metrics**: tool call success rates, step counts per task, fallback frequency, and context retrieval precision. A 99.9% API uptime means nothing if the agent is calling the wrong tool 40% of the time.
- **Build the forensic loop**: production failure → trace capture → root cause analysis → generate new golden case → add to regression suite. Every outage is a test case gift.
- **Distinguish Discovery mode from Defense mode**: during development, use 1–10 inputs with human evaluation ("does this feel right?"). Before shipping, switch to Defense mode: 50–10,000 automated runs with automated scoring. The same eval stack serves both modes; the configuration changes.

## Evidence

- **AWS/Amazon Bedrock (2026):** Principal architects describe a 4-layer eval pyramid: unit/component → integration → end-to-end → production monitoring. Teams at Amazon using Strands Evals systematically evaluate agents before and after every change. Emphasize that traditional LLM benchmarks are insufficient for agentic systems — the eval must cover tool selection accuracy, multi-step reasoning coherence, memory retrieval efficiency, and end-to-end task completion. — [AWS Blog — Real-world lessons from building agentic systems at Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Google Cloud (Feb 2026):** Engineers describe the transition from manual "vibe checks" (chatting with the agent, subjective judgment) to continuous automated evaluation. Discovery Mode uses 1–10 inputs with human evaluation; Defense Mode uses 50–10,000 automated runs. "Relying on vibe checks is a recipe for disaster in production." — [Google Cloud Blog — From "Vibe Checks" to Continuous Evaluation](https://cloud.google.com/blog/topics/developers-practitioners/from-vibe-checks-to-continuous-evaluation-engineering-reliable-ai-agents)
- **AlphaEval / GAIR-NLP (2026):** Evaluated 94 production tasks sourced from 7 companies across 6 occupational domains. Found near-zero correlation between research benchmark scores (SWE-bench, WebArena, GAIA) and production task success. Production tasks contain implicit constraints, fragmented multi-modal inputs, and success criteria judged by domain experts whose standards evolve. — [AlphaEval on arXiv](https://arxiv.org/html/2604.12162)

## Gotchas

- **A golden set you built once and never updated is a lagging indicator.** If your agent now handles a new workflow but your golden set doesn't test it, you're flying blind. Treat golden set maintenance as a first-class engineering task, not a one-time setup.
- **LLM-as-judge self-preference inflates scores by 10–15%.** If your judge model is from the same family as the agent, the scores are systematically inflated. Always use cross-family judges or explicitly calibrate for this bias.
- **Token cost of evaluation can exceed token cost of the agent.** Running LLM-as-judge on 1,000 production samples with a 3-dimension rubric can cost more than the agent itself. Budget evaluation cost as part of agent cost — not as a rounding error.
- **Coverage ≠ quality.** A golden set with 500 scenarios covering the happy path tells you nothing about the 3 edge cases that cause 80% of your support tickets. Prioritize representative failure modes over scenario count.
