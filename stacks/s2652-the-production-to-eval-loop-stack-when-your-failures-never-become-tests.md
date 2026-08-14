# S-2652 · The Production-to-Eval Loop Stack

> When your agent fails in production, you fix it, and it fails the same way three months later — because the failure never became a test.

## Forces

- **The regression gap**: Every production failure that doesn't become a test case is a scheduled repeat. Agents are non-deterministic, so the same failure mode can recur long after the engineer who fixed it has moved on.
- **Evaluation without trajectory**: End-to-end accuracy scores on golden datasets don't catch tool-call ordering errors, silent context poisoning, or cost explosions that happen mid-trajectory — only trajectory-level inspection does.
- **The observability-to-eval gap**: 89% of production agent teams run observability, but only 52% run systematic evals (LangChain State of Agent Engineering Survey). Teams see where agents fail; they don't always turn that visibility into regression tests.
- **Golden datasets go stale**: Synthetic golden datasets don't reflect real user behavior. Without continuous ingestion from production traces, test sets drift until they measure what the agent was tested on, not what users actually ask.

## The Move

The move is a **closed evaluation loop**: production failures feed traces into a golden dataset, which gates CI/CD on every future change.

**Build the dataset from what breaks:**

- Capture full traces from production failures — every tool call, context window state, and error point
- Convert traces to test cases with a human-reviewed expected outcome and pass criteria
- Store test cases in a versioned golden dataset with schema validation

**Run three eval tiers in CI/CD:**

1. **Deterministic PR gate** — tool-call correctness, schema validation, return-type checks. Fast, deterministic, runs on every commit. Catches regressions a human reviewer would catch anyway.
2. **LLM-as-judge nightly regression** — run full agent trajectories against the golden dataset. A separate judge model scores task completion, reasoning quality, and safety. Catches prompt/model regressions that deterministic checks miss.
3. **Canary with error budget** — promote to production behind a traffic split. Monitor task success rate, latency, and cost against SLO baselines. Roll back if error budget is exhausted.

**Calibrate the judge model:**

- Start with a small expert-labeled reference set (5–20 cases)
- Calibrate a capable model against those labels — its judgments must match expert consensus before it scales labeling
- Use abstention signals: when the judge is uncertain, flag for human review rather than forcing a score

**Keep the dataset alive:**

- Run quarterly audits: what fraction of test cases came from production? If less than 60%, synthetic data is dominating and the set is drifting.
- Delete or re-label cases that no longer reflect product behavior.

## Evidence

- **HN Discussion (2025):** Engineers building agents at Stanford AI Lab described spending 10 minutes rerunning full agent runs after every one-line change. They built Lucidic to make agent debugging tractable — capturing traces, clustering failure trajectories, and building regression tests from production sessions. — [Launch HN: Lucidic — Debug, test, and evaluate AI agents in production](https://news.ycombinator.com/item?id=44735843)
- **Company Engineering Post (2025):** Anthropic engineers recommended that eval-first teams "just copy the shape of the eval" from a relevant public benchmark, then mine production traces for real behavior, create a small expert-labeled reference set, and calibrate a capable model against those labels before scaling. — [Tips from Anthropic on building evals you can trust — Arize AI](https://arize.com/blog/ai-agent-evaluation-how-to-build-evals-you-can-trust/)
- **Engineering Guide (2026):** A practical three-tier eval pipeline — deterministic checks on every PR, LLM-as-judge regression nightly, canary promotion with error budgets — with the core principle that "a wrong tool call at step 3 fails the build before it dooms steps 4 through 12." — [Agent Testing in CI/CD: How to Eval Autonomous Agents in 2026 — AgenticWire](https://www.agenticwire.news/article/agent-testing-cicd-guide)
- **Golden Dataset Guidance (2025):** Langfuse's engineering documentation recommends building golden datasets from real traces first, CSV imports and synthetic generation second — and growing them from production failures, not freezing them at creation. — [Golden dataset evaluation: build and maintain LLM test sets — Langfuse](https://langfuse.com/resources/engineering/golden-dataset-evaluation)
- **Closed-Loop Pattern (2026):** Arthur's Agent Development Flywheel describes the loop: production failure → trace → test case → golden dataset → release gate in CI/CD, so the same failure can never silently ship twice. — [AI Agent Regression Testing From Production Failures — Arthur](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

## Gotchas

- **Eval flakiness**: Agent runs can pass or fail on the same input due to non-determinism. Run each test case 3–5 times and measure consistency, not just pass/fail. Flag cases with >20% variance for investigation.
- **Judge model bias**: LLM-as-judge tends to be lenient on task completion and harsh on formatting. Calibrate with domain-specific rubrics, not generic prompts.
- **Cost of nightly LLM-judge runs**: Golden datasets of 500+ cases × nightly runs × judge model cost can rival inference spend. Size the dataset to the problem: 50 cases for PR gates, 200–500 for regression suites, 1000+ only for high-stakes production systems.
- **Synthetic data dominance**: If the golden dataset is mostly synthetic (prompt-engineered edge cases), it won't catch real-world regressions. Target at least 60% production-derived cases in the dataset.
