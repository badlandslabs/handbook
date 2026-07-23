# S-1520 · The Evals-First Stack — When You Build an Agent and Have No Idea If It Works

You've shipped an agent. It responds correctly in your demos. It works on the test cases you wrote. Then it hits production traffic — edge cases you never imagined, model updates you didn't catch, tool failures that cascade silently — and you have no idea if it's actually working. This is the eval gap: the moment between "it seems fine" and "we know it's fine."

## Forces

- **Agents are systems, not models.** Single-turn accuracy metrics (BLEU, ROUGE) and classical NLP benchmarks don't capture how agents fail. An agent can produce the right answer through the wrong process — or the wrong answer through a process that looks fine. You have to evaluate the system, not just the output.
- **Behavior beats benchmarks.** Curated test sets tell you if your agent does well on curated test sets. They don't tell you if it handles a real user's malformed input, a tool API that returns 500 errors, or a model update that quietly changes behavior.
- **Eval quality and cost trade off.** Human evaluation is the gold standard but doesn't scale. LLM-as-a-judge scales but has correlation drift. Agent-as-a-judge gives richer intermediate feedback but adds infrastructure complexity.
- **Silent failures are the real danger.** An agent can report inventory correctly by accident — referencing last year's data instead of today's. The result looks right. The process failed. Standard evals miss this entirely.

## The move

Evaluate agents on a continuous pipeline with layered checks — not a one-time benchmark at launch.

**Define success at the system level first, not the model level.**
- Ask: does the agent complete the full workflow end-to-end? Not just "did it answer," but "did it accomplish the task."
- For a refund agent: did it process the refund correctly, notify the right systems, and close the ticket — not just produce a coherent-sounding response?
- Task success is binary for many cases, but the path matters: an agent that gets lucky vs. one that reliably follows the correct process are not the same.

**Build a three-layer eval stack:**
1. **End-to-end behavioral evals** — does the agent achieve the user's goal across complete sessions? Use goldens (expert-labeled test cases) for regression. Run them on every commit or PR.
2. **Component-level trace checks** — did the right tools get called with the right arguments? Did the agent use the tool outputs correctly? Did handoffs between agents happen correctly? These catch silent failures that pass the end-to-end check.
3. **LLM-as-a-judge for subjective quality** — tone, relevance, whether responses are grounded in retrieved context. Use a judge model separate from the agent model. Target ≥0.80 Spearman correlation with human judgment; calibrate against a human-labeled sample first.

**Track operating envelopes alongside quality scores.**
- Token consumption per session: high counts signal runaway reasoning loops or inefficient prompt construction.
- Latency per step and per session.
- Step/token budgets: limit iterations per session to prevent runaway costs and infinite loops.
- Tool call counts: agents that search, summarize, then search again for the same information are wasting latency and money.

**Use pass^k, not pass@k, for reliability-critical domains.**
- Standard pass@k (success at least once in k tries) is fine for exploratory tasks. For customer service, support, or anything where each interaction must succeed: pass^k asks "did it succeed in all k tries?"
- Tau-Bench data shows GPT-4o hitting ~61% pass^1 on retail but only ~25% pass^8 — a stark reminder that "works sometimes" is not "works."

**Calibrate LLM-as-a-judge with human rubrics before trusting it.**
- Build 3-tier rubrics: 7 dimensions → 25 sub-dimensions → 130 specific items, or domain-specific criteria grounded in what users actually care about.
- Run LLM-judge and human-judge on the same sample. If correlation is below 0.80, the judge model isn't calibrated for your domain — keep humans in the loop for that metric.
- Re-run calibration after every model update; behavior drift between model versions is well-documented.

**Integrate evals into CI/CD, not just pre-launch.**
- Commit-triggered: catch regressions on every code change.
- Scheduled: catch drift from model updates, tool API changes, or input distribution shifts.
- Event-driven: re-evaluate when upstream tools change their schemas or error codes.
- OpenAI's own GPT-4 showed measurable behavior changes across versions — tasks at 97% accuracy in March 2023 dropped to 87% by June 2023 on the same benchmark.

## Evidence

- **Databricks Blog (2025):** 73% of companies say GenAI is critical to long-term strategy, but most AI agents fail before reaching production. Databricks recommends three pillars: task-level benchmarking (does it complete workflows?), grounded evaluation (does it use enterprise context, not generic knowledge?), and change tracking (does it survive model updates?). — [databricks.com/blog/key-production-ai-agents-evaluations](https://www.databricks.com/blog/key-production-ai-agents-evaluations)
- **Sierra AI / τ²-Bench GitHub (2025):** τ-Bench evaluates customer service agents in simulated multi-turn conversations with policy compliance and real API calls. The key innovation is pass^k — reliability over average-case success. Top models still score only 61–69% pass^1 on retail and 35–46% on airline — far from ceiling. — [github.com/sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench) + [oss.vstorm.co/blog/tau-bench-ai-agent-benchmarks](https://oss.vstorm.co/blog/tau-bench-ai-agent-benchmarks)
- **arXiv / Agent-as-a-Judge (Zhuge et al., 2024):** Standard LLM-as-a-judge sees only final outputs. Agent-as-a-judge evaluates intermediate steps — whether tools compiled at each stage, whether the agent followed each sub-requirement, how many tool calls were used. On code generation tasks, agent-as-a-judge matched human evaluator reliability while dramatically outperforming output-only LLM-judge. The DevAI benchmark (55 real tasks, 365 hierarchical requirements) is the testbed. — [arxiv.org/abs/2410.10934](https://arxiv.org/abs/2410.10934)
- **InfoQ / Evaluating AI Agents in Practice (March 2026):** Single-turn accuracy metrics don't capture agent failure modes. The article documents four critical principles: evaluate systems not models, prioritize behavior over benchmarks, use hybrid (automated + human) evaluation, and treat operational constraints — latency, cost, policy compliance — as first-class eval targets. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Google Cloud / Methodical Approach to Agent Evaluation (Nov 2025):** Documents the "silent failure" problem — agents that produce correct outputs through incorrect processes. Recommends multi-layered eval: human evaluation to establish ground truth and failure modes, LLM-as-a-judge for scale, and continuous monitoring for drift. — [cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Confident AI / Definitive Agent Evaluation Guide (2026):** Agents fail at both end-to-end level (task never completes, loops, latency) and component level (wrong tool parameters, tool outputs unused, bad handoffs). The failures live in the execution trace. Component-level metrics — not just final output scoring — are required. — [confident-ai.com/blog/definitive-ai-agent-evaluation-guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)
- **MLflow / Monitoring Agentic AI in Production (Jun 2026):** Three metric categories: performance (session success rate, tool call accuracy, step count, time-to-first-token), quality (hallucination frequency via LLM-as-a-judge, grounding accuracy, retrieval precision), and cost/safety (turn budgets, token consumption, policy compliance). — [mlflow.org/articles/monitoring-agentic-ai-in-production-2026-guide](https://mlflow.org/articles/monitoring-agentic-ai-in-production-2026-guide)

## Gotchas

- **"Metric green, user red."** LLM-as-a-judge scores can pass while human reviewers flag tone, trust, or contextual issues. Always sample human judgments to calibrate and catch this gap — it doesn't show up in automated scores.
- **Eval inflation from training contamination.** Pre-built benchmarks can inflate scores if test cases leaked into training data. Build domain-specific golden datasets from real production failures — each failure you catch in the wild is a permanent test case.
- **Re-evaluating on every model update is non-negotiable.** Model behavior shifts between versions and even over time within a version. An agent certified at launch is not certified six months later without re-evaluation.
- **End-to-end pass doesn't mean component-level correctness.** An agent can reach the right final answer by calling the wrong tools, ignoring tool outputs, or making a lucky inference. Trace-level inspection is the only way to catch this.
- **Agent-as-a-judge adds cost but not always complexity.** If your judge needs to call tools to verify intermediate state (e.g., "did this code actually compile?"), that's a second agent — budget for it. The payoff is dramatically better signal than output-only scoring.
