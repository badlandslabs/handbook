# S-2085 · The Evaluation Gap Stack · When Your Pass@1 Is Green but Your Production Is on Fire

*When your agent scores 94% on your test harness but degrades silently in production — because you were measuring the wrong thing, the wrong number of times, against the wrong distribution.*

## Forces

- **Single-run success is not reliability.** Pass@1 tells you "can this agent succeed once?" — not "will it succeed when it matters?" Consistency across runs (pass^k) is what your users experience, and it is almost always worse.
- **Outcome metrics lie.** An agent can reach the wrong answer through a correct-looking trajectory, or reach the right answer through a catastrophic trajectory. Final-state checks miss both failure modes.
- **Traditional testing assumes determinism.** AI agents are stochastic. The same task, run twice, can produce different tool sequences, different intermediate states, and different outcomes. Your CI pipeline was not built for this.
- **74% of production agents lack formal evaluation.** The teams that do have evals often build them as an afterthought — point-in-time checks, not continuous measurement. The failure is invisible until it is expensive.

## The Move

Measure what users actually experience — trajectory quality, not just outcome. Run statistically rigorous pass@k with confidence intervals. Combine automated grading with human spot-checks and integrate evaluation into CI/CD so regressions surface before deployment.

### The four-layer evaluation stack (Amazon, 2026)

1. **Capability benchmarks** — does the agent have the right abilities? Use domain-specific benchmarks (SWE-bench for code agents, ToolBench for tool use, τ-benchmark for consistency). Pre-deployment only; go/no-go gate.
2. **Trace evaluation** — how does it reason? Inspect tool selection accuracy, intermediate reasoning steps, error recovery sequences, and memory retrieval quality. This is where you catch "right answer via wrong path" and "right path via wrong tool."
3. **Operational metrics** — what does it cost and how fast is it? Track latency (p50/p95/p99), cost per task, token efficiency, and tool call budgets. These are first-class signals, not afterthoughts. Cost per task trending up is often the first sign of a model degradation issue.
4. **Safety and policy** — does it do harm? Red-teaming, PII handling checks, permission boundary testing, and harmfulness scoring. Runs continuously on production traffic, not just at release.

### Statistical rigor for pass@k

- Use the **unbiased pass@k estimator** (Chen et al., 2021) rather than naive "any of k runs pass." The naive method overestimates at small k.
- Report **Wilson score confidence intervals**, not just point estimates. Wilson intervals stay in [0, 1] and give correct coverage at small sample sizes — Wald intervals under-cover and produce nonsense bounds.
- Track **pass^k** (all k runs must pass) alongside pass@k. The gap between them quantifies the reliability gap — how far "can succeed once" runs ahead of "usually succeeds." This is what matters for business automation.

### LLM-as-Judge in production

More than 50% of surveyed production agent teams now use judge LLMs at runtime for quality gating, not just in evaluation harnesses. This means LLM-as-Judge has crossed from testing tooling into **load-bearing production infrastructure**. Calibrate judges to 0.80+ Spearman correlation against human judgments on a shared rubric before trusting them. Use judges for trajectory quality (did the agent use the right tool in the right order?), not just outcome quality. Pair with human spot-reviews on a sample of traces — humans catch "metric green, user red" failures that automated judges miss, particularly around tone, trust, and contextual appropriateness.

### Deterministic evaluation environments

Gauntlet (GitHub, mbsdeepak/gauntlet) exemplifies a useful pattern: hermetic simulated tool environments — fake filesystem, ticket store, config service — where evaluation is fully reproducible. Same seed, same behavior. Eliminates flakiness from real-world API changes, network variability, or external service availability. Graders inspect final state deterministically. This gives you the reproducibility of unit tests with the agentic realism of live tool use.

### Integrate into CI/CD

Evaluation must trigger automatically on code changes, run continuously on production traffic, and surface failures within minutes — not days. Configure three trigger types:
- **Commit-triggered**: every prompt/prompt-template/tool-schema change runs the full evaluation suite before merge.
- **Scheduled**: weekly full evaluation against updated test dataset catches distribution drift.
- **Event-driven**: production anomaly detection triggers targeted re-evaluation of the affected capability.

Store evaluation results, test datasets, production logs, and model artifacts in a trace store. Reproducibility and trend analysis depend on this data being organized and queryable.

## Evidence

- **AWS/Amazon engineering blog (Feb 2026):** Amazon's agent evaluation framework developed from thousands of agents built across the organization since 2025. Their core finding: traditional LLM evaluation treats agent systems as black boxes and fails to provide insights into tool selection accuracy, multi-step reasoning coherence, and root cause identification. They propose the four-layer framework covering capability, trace, operational, and safety dimensions. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **Paul Simmering / simmering.dev (Jan 2026):** Survey of 306 AI agent practitioners found reliability issues are the biggest barrier to enterprise adoption. Practitioners respond by forgoing open-ended tasks, building only internal-facing agents reviewed by humans, and avoiding customer-facing interfaces. Shows empirically that single-run success (60%) degrades significantly across 8 runs, with the reliability gap between pass@k and majority@k quantifying how far "can succeed once" runs ahead of "usually succeeds." — [simmering.dev/blog/agent-benchmarks](https://simmering.dev/blog/agent-benchmarks)
- **GitHub: Gauntlet (mbsdeepak/gauntlet):** Open-source agentic tool-use evaluation framework using deterministic simulated tool environments with hermetic fakes (filesystem, ticket store, config service). Grades planning correctness, tool selection, error recovery, and goal achievement. Reports pass@k with unbiased Chen et al. (2021) estimator and Wilson score confidence intervals. — [github.com/mbsdeepak/gauntlet](https://github.com/mbsdeepak/gauntlet)
- **Gartner (2026, cited via thinking.inc):** Projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps. — [thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production)

## Gotchas

- **Pass@1 is a vanity metric.** If your benchmark only reports pass@1, you are measuring "can this work in the best case" — not "will this work in production." Demand pass^k from your benchmarks or run the experiments yourself.
- **Outcome-only evaluation misses trajectory failures.** An agent that achieves the right final state by calling the wrong tools in the wrong order is one code change away from failure. Inspect traces, not just final states.
- **LLM-as-Judge has its own failure modes.** Judges inherit the biases of the model that runs them. Without calibration against human judgments (target: 0.80+ Spearman correlation), you are measuring the judge's opinion, not the agent's quality.
- **Test distribution ≠ production distribution.** Benchmarks trained on curated test sets can score well against tasks that don't match real user inputs. Domain-specific benchmarks (real GitHub issues for code agents, real user queries for support agents) outperform generic ones.
- **74% of teams have no formal evals.** If you are in this majority, the most valuable thing you can build is a 20-query golden dataset with a simple LLM-as-Judge evaluator — not a comprehensive evaluation platform. Start measurable, iterate to comprehensive.
