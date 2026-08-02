# S-2016 · The Agent Evaluation Stack — When Your Agent Works in the Demo but Fails in Production

Your agent nailed the demo. Every test prompt you tried produced the right answer. You shipped it. Two weeks in, you're fielding bug reports about failures no one anticipated — edge cases that look trivial in hindsight, lucky recoveries that hid broken trajectories, and silent regressions from a model update you didn't even know shipped. This entry covers the evaluation patterns that production teams use to catch these failures before users do: trajectory scoring, production-derived golden datasets, LLM-as-judge with its known failure modes, and the regression budget framework.

## Forces

- **The output is downstream of what you actually care about.** An agent can reach the right answer through the wrong path: wrong tool first, lucky recovery, ignored constraints that didn't bite this time. Grading only the final answer hides the trajectory failure that will surface next Tuesday with different input.
- **Agents are non-deterministic in two ways.** The underlying model varies its outputs, and small variations compound across many steps. The same task can follow different paths and produce different outcomes on different runs. One-shot evaluation gives you one data point in a distribution, not a measurement.
- **Benchmarks don't predict production behavior.** Public benchmarks like MMLU or HumanEval measure model capability in isolation, not agent behavior in a specific workflow. An agent that scores 90% on a benchmark can still fail 30% of the time on your particular use case with your particular tools and prompts.
- **Eval saturation is a trap.** A golden dataset at 100% pass rate tracks regressions perfectly but gives zero signal for improvement. You need a mix of regression coverage and capability exploration.
- **Offline evals and online monitoring are different instruments.** Offline evaluation answers "did the last change break anything?" Online monitoring answers "is the system healthy right now?" Teams that only do one or the other are flying partially blind.

## The Move

### 1. Evaluate trajectories, not endpoints

Score the full run: which tools were called, in what order, with what arguments, and whether each step satisfied policy. An endpoint eval misses that the agent used the wrong tool but recovered. Trajectory evaluation catches it. Implement per-step rubrics — criteria scored at each tool call — rather than a single pass/fail at the end.

Minimum viable setup: 50–200 real examples sourced from production failures and edge cases, per-step rubrics, 10+ runs per example to handle non-determinism, and a held-out set you never tune against. Replay harnesses let you re-run captured traces against a new model or policy without re-hitting production systems.

**Concrete metrics** to track per trajectory:
- **Tool selection accuracy** — did the agent call the right tool at each step?
- **Step count / efficiency** — track total steps, token cost, and wall-clock time per run; a rise with flat success rate is a regression signal even if nothing "broke"
- **Policy compliance** — did each step stay within defined constraints (e.g., never call delete, always confirm before committing)?
- **Recovery quality** — if a tool call failed, did the agent recover appropriately?

### 2. Build golden datasets from production failures, not just engineering imagination

The highest-value regression test dataset is not handcrafted. It comes from production failures. Every time an agent fails in front of a real user, it hands you a test case you could not have invented: an authentic edge case, a real input distribution, and a concrete definition of what "broken" looks like for your system.

The production-to-test loop: **production failure → trace capture → test case extraction → golden dataset → CI/CD release gate**. Run the dataset on every prompt change, model swap, retrieval tweak, or tool update. The same failure can never silently ship twice.

Synthetic test cases still matter for coverage (cases that haven't happened yet), but they should complement production-derived cases, not replace them. A synthetic dataset built only from what engineers imagined will have blind spots that real users immediately find.

### 3. Use LLM-as-judge, but know its failure modes

Over 57% of surveyed production agent teams now rely on judge LLMs at production runtime. The field has split into two tiers: large proprietary judges (Claude 3.7 Sonnet, GPT-4o) for high-stakes verification where accuracy matters most, and small distilled judges (Galileo Luna-2 3B–8B, Prometheus 2 7B, Patronus Lynx 8B) for high-throughput inline checking where cost and latency dominate.

The critical failure mode: **LLM judges grade the wrong thing when applied naively.** Two problems compound. First, grading only the final answer misses broken trajectories. Second, judges ding correct trajectories on phrasing or format even when the content is right. To address this, use trajectory-aware judges that score the reasoning path and intermediate steps, not just the final output.

Judge reliability requires calibration. The production standard is a Spearman correlation of 0.80+ with human evaluators. Maintain this by running the judge against a set of human-labeled examples monthly and swapping the judge model or adjusting the prompt if correlation drops below threshold. Ensemble judging — combining multiple judge models and taking weighted consensus — produces more stable scores than any single judge.

Cost reduction without sacrificing accuracy is achievable: small distilled judges can achieve 97% cost reduction at 0.88–0.95 accuracy relative to large proprietary judges for many evaluation tasks.

### 4. Track consistency metrics (pass@k), not just success rate

An agent with 75% per-trial reliability has only a 42% chance of passing all three independent trials under pass@3. A system that "works" 75% of the time in demo fails regularly in production where users expect reliability. Track pass@3 or pass@5 across your golden dataset — this reveals consistency that single-run success rate hides.

### 5. Set a regression budget, not just a pass threshold

A golden dataset at 100% pass rate tracks regressions perfectly but gives no improvement signal. Instead, set a regression budget: the maximum acceptable failure rate for the golden dataset, the maximum step count increase before alerting, and the maximum trajectory divergence from the canonical path.

Three inputs for setting the budget: (1) current failure rate on the golden dataset, (2) business cost of failures (what does each failure cost in real terms?), and (3) traffic volume (low-traffic systems can tolerate higher per-instance failure rates than high-traffic ones).

### 6. Combine offline evaluation with online monitoring

Offline evaluation answers "did the last change break anything?" — run in CI/CD on the golden dataset before shipping. Online monitoring answers "is the system healthy right now?" — track success rates, latency, tool call patterns, and error rates on live traffic.

LangChain's 2026 State of AI Agents report found only 52.4% of teams run offline evaluations and just 37.3% run online evals. Most teams are flying partially blind.

## Evidence

- **Engineering blog — Anthropic:** Anthropic's "Building Effective AI Agents" (Dec 2024, HN 543 points) defines the agents vs. workflows distinction and notes that effective evaluation requires task-level benchmarking and grounded evaluation with change tracking. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **Engineering blog — James Murphy:** "Evaluating Agents in Production: Trajectory Metrics, Not Just Final Answers" (June 2026) documents the minimum viable eval setup (50–200 real examples, per-step rubrics, 10+ runs per example) and introduces the replay harness pattern for offline trajectory testing. — [jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics](https://jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)

- **Industry research — Zylos Research:** "LLM-as-Judge in Production: Agent Reasoning Verification, Self-Correction, and Hallucination Defense" (April 2026) surveys production teams finding >57% rely on judge LLMs at runtime, documents the 6 judge patterns, and reports small distilled judges achieve 97% cost reduction at 0.88–0.95 accuracy vs. large proprietary judges. — [zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

- **Platform post — Arthur:** "How to Build Regression Test Datasets for AI Agents From Production Failures" (June 2026) articulates the production-to-test flywheel and documents that production-derived test cases outperform synthetic ones because they capture real input distributions. — [arthur.ai/column/regression-test-datasets-ai-agents-production-failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

- **Platform post — Mastra:** "AI Agent Evaluation: Build Production-Grade Agents" (June 2026) reports only 37.3% of agent teams run online evals per LangChain's 2026 State of AI Agents report, and demonstrates the consistency math: 75% reliability → 42% pass@3. — [mastra.ai/articles/ai-agent-evaluation](https://mastra.ai/articles/ai-agent-evaluation)

- **Platform post — Google Cloud:** Vertex AI Gen AI Evaluation Service (Jan 2025, public preview) implements trajectory evaluation with metrics including exact trajectory match, tool call accuracy, and policy compliance scoring. — [cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service](https://cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service)

- **Platform post — Microsoft:** Azure AI Foundry evaluation library (April 2025) introduced purpose-built agentic metrics covering trajectory correctness, tool use correctness, and task completion — distinguishing these from traditional NLP metrics that fail for agentic systems. — [techcommunity.microsoft.com/blog/azure-ai-foundry-blog/evaluating-agentic-ai-systems-a-deep-dive-into-agentic-metrics/4403923](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/evaluating-agentic-ai-systems-a-deep-dive-into-agentic-metrics/4403923)

- **Academic survey — KDD 2025:** "Evaluation and Benchmarking of LLM Agents: A Survey" (arXiv:2507.21504, KDD 2025) proposes a two-dimensional taxonomy (evaluation objectives × evaluation methods) and documents enterprise-specific challenges including trajectory evaluation datasets like AAAR-1.0, ScienceAgentBench, and TaskBench. — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)

## Gotchas

- **Public benchmarks don't translate.** Your agent scoring well on WebArena or GAIA doesn't mean it performs on your specific workflow with your specific tools. Source evaluation data from your actual system.
- **One run is not a measurement.** Agents are non-deterministic. Run each evaluation example 10+ times and report the distribution. Single-run success rates are misleading.
- **Eval saturation blinds you to improvement.** If your golden dataset is at 100% pass rate, you can't tell if you're getting better or worse. Maintain a separate capability exploration set alongside your regression set.
- **Judge correlation drifts over time.** As models update, judge prompts drift, and real-world distributions shift, a judge that was 0.85 correlated with human evaluators six months ago may now be 0.60. Recalibrate monthly.
- **Offline passing ≠ production health.** An agent can pass all offline evaluations and still be failing in production due to different input distributions, rate limits, downstream API changes, or tool behavior differences between test and live environments. Both offline and online evaluation are required.
- **Efficiency regression is silent.** A rise in step count or token cost with a flat success rate is a genuine regression — the agent is working harder to achieve the same result. Track efficiency metrics even when accuracy is stable.
