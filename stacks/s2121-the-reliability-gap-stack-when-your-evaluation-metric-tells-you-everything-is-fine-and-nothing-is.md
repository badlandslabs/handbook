# S-2121 · The Reliability Gap Stack — When Your Evaluation Metric Tells You Everything Is Fine and Nothing Is

Your agent scores 97% on pass@3. Your team celebrates. You ship it. Three months later, users are filing bugs at a steady clip and nobody can explain why — the benchmark is green. The problem is not the agent. The problem is that you were measuring the wrong thing. pass@3 is a best-case metric: it tells you whether *any* of three attempts succeeded. It says nothing about whether *all three* succeed — the actual consistency your users experience. A 70%-per-trial agent reads as 97% on pass@3 but 34% on pass^3. The gap between those two numbers is the Reliability Gap, and most teams are flying blind inside it.

## Forces

- **Metric optimism vs. user experience** — pass@k rewards agents that can eventually succeed; users need agents that always succeed on the first try
- **Non-determinism is structural, not incidental** — LLM sampling means the same input produces different outputs; a "working" agent can fail 30% of the time and look great on pass@3
- **LLM judges drift without calibration** — an uncalibrated model judge can show perfect scores while diverging from expert human review, creating false confidence
- **Eval datasets go stale in weeks** — production inputs shift, model behavior changes with updates, and yesterday's golden set becomes tomorrow's noise
- **37% performance gap between benchmarks and production** — (per arXiv:2504.11543) means teams optimizing for benchmarks are shipping agents that underperform in the real world

## The move

Measure consistency, not capability. Build a two-layer eval pipeline: offline benchmarks for development confidence, production traces for reality.

**The eval stack (four layers, per InfoQ):**
- Layer 1 — Capability benchmarks (MMLU, HumanEval, tau-bench): measure whether the model *can* do the task
- Layer 2 — Task completion metrics: measure whether the agent *does* the task end-to-end
- Layer 3 — LLM-as-judge with human calibration: measure whether the output *meets quality bar*
- Layer 4 — Operational metrics: latency, cost per task, token efficiency, tool reliability, policy compliance

**pass^k over pass@k for production:**
- `pass@3` = at least one of three attempts succeeds → optimistic, useful for exploration
- `pass^k` = all k attempts succeed → conservative, matches user experience
- Track both. Report pass^k as the shipping gate. The delta between them is your reliability headroom.

**Calibrate your LLM judge against a human gold set:**
- Start with 20–50 real failure cases from production traces (per Digital Applied's 2026 methodology)
- Label them by hand with an expert reviewer
- Measure judge-human agreement (target Cohen's κ ≥ 0.6)
- Minimum gold set: 100+ labeled examples before trusting the judge
- Recalibrate every 30 days; model behavior drifts between versions

**Code-based graders for deterministic cases, model-based graders for open-ended quality:**
- Code-based: exact match, regex, JSON schema validation — fast, deterministic, zero drift
- Model-based: tone, relevance, whether the agent recovered gracefully from a tool failure — requires calibration

**Feed production traces back into the eval dataset:**
- Log every production failure as a potential eval case
- Run offline evals against this growing set on every code change
- Gate CI/CD on pass^k thresholds, not pass@3

**Monitor three operational layers post-deploy:**
- Behavioral: task success rate, error recovery rate, tool call patterns
- Quality: LLM-judge scores, human spot-checks on a sample
- Economic: latency p50/p95/p99, cost per task, token efficiency

## Evidence

- **LangChain (2025):** Benchmarked multi-agent architectures on tau-bench; found single-agent performance degrades significantly with context size even when irrelevant to the task. Multi-agent splits (separate agents per domain) yielded a ~50% performance improvement over a naive single-agent supervisor. — [https://www.langchain.com/blog/benchmarking-multi-agent-architectures](https://www.langchain.com/blog/benchmarking-multi-agent-architectures)

- **Digital Applied (2026):** A 70%-per-trial agent achieves ~97% pass@3 but only ~34% pass^3. Their methodology recommends starting with 20–50 real failure traces from production, using pass^k as the CI gate, and recalibrating LLM judges against 100+ human-labeled examples every 30 days. — [https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology](https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)

- **MIT 2025 AI Agent Index (arXiv:2602.17753):** Indexed 30 deployed agents across 45 fields each. Found 14.7% of data fields were unavailable, and 55% of safety-related fields had no information at all — meaning most production agents cannot be evaluated on their own stated safety claims. — [https://arxiv.org/html/2602.17753v1](https://arxiv.org/html/2602.17753v1)

- **Thoughtworks (2025):** 95% of AI projects fail. Organizations struggle with defining success in a probabilistic environment and navigating the eval tooling ecosystem. Traditional deterministic testing fails because multiple valid responses exist for the same input. — [https://www.thoughtworks.com/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production](https://www.thoughtworks.com/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)

- **InfoQ (2026):** "Agents are systems, not models — evaluate them accordingly." Classical NLP benchmarks (BLEU, ROUGE) don't capture how agents fail. Behavioral metrics (task success, graceful recovery, consistency) and hybrid evaluation (automated + human) are non-negotiable for production. — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **Anthropic Engineering (via GitHub Gist):** Evaluations enable teams to ship agents by making problems visible before users see them. Without evals, debugging is reactive. Framework-agnostic; compatible with Harbor, Promptfoo, Braintrust, LangSmith, Langfuse. — [https://gist.github.com/vishalsachdev/b6e5076ec3ced7e4f0228969f0727eba](https://gist.github.com/vishalsachdev/b6e5076ec3ced7e4f0228969f0727eba)

## Gotchas

- **Running pass@3 and calling it reliability** — it is a capability metric, not a reliability metric. Use it during development for rapid iteration; gate shipping on pass^k.
- **Shipping with an uncalibrated LLM judge** — the judge will agree with itself but not with your experts. Build the human gold set *before* the judge, not after.
- **Eval dataset never updated after initial creation** — production traces are your most valuable eval data. If you're not logging failures back into the eval set, your offline metrics are becoming stale within weeks.
- **Treating benchmark scores as certification** — model updates (GPT-4 showed 10pp accuracy drops across versions per Chen et al., 2023) can regress agents silently. Continuous evaluation is required, not point-in-time certification.
