# S-971 · The Agent Evaluation Stack — When You Don't Know If Your Agent Is Getting Better

Your agent passes the demo. Your benchmark says 92%. Your users report that it still confidently messes up refunds, invents policy exceptions, and hands off to humans at the wrong moments. You have no idea if your last prompt change made things better or worse. The fix isn't a better benchmark — it's an evaluation architecture that measures what actually matters in production, at the cadence that development requires.

## Forces

- **Benchmarks lie to you** — single-turn accuracy scores (BLEU, ROUGE, even curated agent benchmarks) don't capture multi-turn failures, silent tool errors, or cost-per-task drift. An agent can score 95% on GAIA and still silently mishandle 30% of production conversations.
- **Human eval is honest but unsustainable** — 74% of production agents rely primarily on human evaluation (MAP study, arXiv:2512.04123). It's accurate. It's also too slow and expensive to gate releases or catch regressions between deployments.
- **LLM-as-judge drifts without calibration** — treating the judge as a static component causes it to silently lose alignment with real failure modes over time. You ship a regression and the judge approves it.
- **Evaluation and observation are siloed** — most teams run evals manually, trace separately, and monitor independently. When something breaks in production, nobody can answer "did this work last week? what changed?"
- **Agent complexity outpaces eval tooling** — multi-turn stateful agents with memory and tool use fail *between* steps, not at the final output. Standard pytest-shaped testing doesn't reach those failure modes.

## The Move

Build a **tiered evaluation pipeline** that separates by cost, speed, and depth — so you get continuous signal without burning budget or engineering time on every change.

### Tier 1: Deterministic guardrails on every PR (free, instant)
- Tool call schema validation — does the agent pass the right parameters with the right types?
- Policy compliance checks — hard rules enforced as code, not prompts
- Output format checks — JSON schema, required fields, length bounds
- These run in CI on every commit. Zero LLM calls. Failures block merge.

### Tier 2: LLM-as-judge sweep on schedule (cheap, ~minutes)
- Define evaluators as code using a framework like **DeepEval** (Apache 2.0, pytest-shaped, 40+ metrics) or **multivon-eval** (deterministic + cascade evaluators, CI-native)
- Use versioned golden datasets — production traces auto-labeled and archived for regression testing
- LLM judges must be calibrated against known failures: feed them examples of real production errors and adjust the prompt/threshold until they catch them
- Run nightly or on-demand against a curated eval set. Results go into a structured log with pass/fail per metric and token cost per run.

### Tier 3: Human review gate for high-stakes releases (expensive, periodic)
- Spot-check production traces for tone, trust signals, and contextual appropriateness
- Review failure cases surfaced by Tier 2 — especially anything the judge missed
- Calibrate the LLM judge against human verdicts to reduce how often this is needed
- This tier is for major releases or policy changes, not every sprint

### Integrate into CI/CD
- Evals run on commit (Tier 1), nightly (Tier 2), and gate canary deploys (Tier 3)
- Track cost-per-task and latency alongside quality metrics — operational constraints are first-class evaluation targets, not afterthoughts
- Pair-comparison statistical gating with auto-rollback on canary degradation

## Evidence

- **Research paper:** The MAP study (Pan et al., arXiv:2512.04123, ICML 2026) surveyed 306 practitioners and conducted 20 case studies across 26 domains. Key findings: 74% rely primarily on human evaluation; 68% of agents execute ≤10 steps before human intervention; 70% use prompting of off-the-shelf models (no fine-tuning). Reliability — consistent correct behavior over time — is the top reported development challenge. — [https://arxiv.org/abs/2512.04123](https://arxiv.org/abs/2512.04123)
- **Engineering post:** InfoQ's analysis of agent evaluation in practice states: "Hybrid evaluation is non-negotiable. Automated scoring (LLM-as-judge, trace analysis, and load testing) gives you repeatability and scale. Human judgment captures what automation misses: tone, trust, and contextual appropriateness." Also notes operational constraints (latency, cost per task, token efficiency, tool reliability, policy compliance) are "first-class evaluation targets, not afterthoughts." — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **OSS framework:** DeepEval (Confident AI, Apache 2.0) is an open-source LLM evaluation framework structured like pytest, with 40+ built-in metrics including G-eval, hallucination detection, and bias detection. Supports CI/CD integration and runs as native pytest test cases. — [https://github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)
- **HN discussion:** Practitioners on HN discussing production orchestration emphasize treating the agent as a system that must be tested end-to-end, not just prompting. One practitioner uses "ACID & Idempotent" principles — dry runs and runbook automations before production action. — [https://news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **Blog post:** LangWatch's analysis of agentic evaluation notes that failures occur *between* steps in multi-turn systems (wrong plan chosen, tool error not recovered, memory misused), requiring trace-level evaluation that single-turn benchmarks miss. — [https://langwatch.ai/blog/writing-effective-ai-evaluations-that-hold-up-in-production](https://langwatch.ai/blog/writing-effective-ai-evaluations-that-hold-up-in-production)

## Gotchas

- **Benchmark saturation** — if your eval dataset is static, your agents will eventually pass by overfitting to the test set, not by improving real performance. Rotate golden datasets quarterly and inject new production failures as they surface.
- **Judge self-preference bias** — LLMs tend to prefer longer, more detailed responses. Calibrate your judge against cases where brevity is correct (error messages, confirmations) to avoid rewarding verbosity.
- **Trace-first, eval-second** — teams who build observability *after* deploying agents have no data to build evals from. Instrument traces from day one, even before the eval framework is in place.
- **Cost blindness** — an agent that scores 99% at 10x the cost-per-task of the baseline is not an improvement. Track operational metrics (latency, token cost, step count) alongside quality metrics in every eval run.
