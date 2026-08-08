# S-2335 · The Trace Gap: When Your Agent Passes Every Test but Still Fails in Production

Your agent scores 94% on your golden test suite. Your CI gate passes. You deploy. Three weeks later, users are filing bugs that the test suite never caught — because the suite measures *whether* the agent got the right answer, not *how* it got there. The right answer masked a brittle execution path that succeeds on known inputs and fails silently on anything new.

This is the trace gap: the separation between what your evaluation measures and what your agent actually does.

## Forces

- **The final-answer trap** — outcome-only scoring misses wrong tool calls that accidentally produced correct results, unnecessary loops through retrieval, and fragile but lucky execution paths. An agent that lands on the right answer through a broken process will fail under distribution shift.
- **The compounding error math** — with 20 steps where each has 95% reliability, the full run succeeds only ~36% of the time (0.95²⁰). Isolated per-step checks look fine; end-to-end failure rates look alarming. Most teams don't measure at both granularities.
- **The golden dataset aging problem** — research from the BenchAge study (arXiv 2510.07238, EACL 2026) found that 24.19% of factuality benchmark items are outdated, with some benchmarks like BoolQ at 63.78% stale. A golden dataset grades your agent as the product *was* when it was curated, not as it runs *now*. It also rewards models for reproducing the curator's wrong answer to a now-changed fact.
- **The evaluation tier imbalance** — LangChain's June 2026 evaluation guide reports that 89% of organizations have implemented observability, but only 52% run offline evals on test sets and only 37% run online evals. The tooling to *see* what agents do has outpaced the tooling to *judge* whether they're doing it well.
- **The LLM-as-judge calibration debt** — LLM judges are fast and scalable, but uncalibrated judges introduce systematic bias. Without human label calibration against your specific domain, LLM-as-judge scores can be 15-20 points away from expert evaluation in niche domains.
- **The human evaluation bottleneck** — the largest systematic study of production agents (arXiv 2512.04123, ICML 2026 Oral, 306 practitioners, 20 case studies, 26 domains) found that 74% of deployed agents rely primarily on human evaluation. At scale, this is expensive and slow, and it creates a sampling bias toward easy cases getting reviewed.

## The Move

The production evaluation loop has three tiers, all of which must run:

**1. Trajectory evaluation — the missing layer.** Score the *path*, not just the outcome. Assert: tool selection was correct, arguments matched the schema, no loops beyond N iterations, state transitions were valid, termination happened at the right step. These are deterministic checks — no LLM needed. If you only score the final output, your agent can look healthier than it is.

**2. Outcome evaluation — with golden datasets and LLM judges, together.** Golden datasets catch regressions on known cases. Use deterministic assertion for tool-call sequences and API responses. Reserve LLM judges for quality dimensions that depend on interpretation (tone, coherence, whether the explanation is helpful). Shape LLM judges with Schema-Guided Reasoning (SGR) — give the judge a structured output schema so scoring is consistent across runs. Calibrate judges against human labels before trusting them at scale.

**3. Continuous trace mining — the flywheel.** Don't let your golden dataset go stale. Mine production traces for failures continuously. Cluster similar failures, keep one representative golden case per cluster, store the source trace IDs in metadata for reviewer inspection. Feed confirmed failures back into the dataset, then re-run offline evals before every deploy. The loop: **trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring → trace**.

**The minimum viable version:** Run trajectory checks on your top-10 failure modes (tool arguments, loop detection, state invariants) as deterministic tests in CI. Add LLM-as-judge for the final output quality dimension. Set up a weekly review of a random sample of production traces routed to a subject-matter expert for labeling. Feed confirmed failures into the dataset.

## Evidence

- **arXiv (ICML 2026):** First large-scale systematic study of agents in production (306 practitioners, 20 case studies, 26 domains). Found 74% rely primarily on human evaluation, 68% of agents execute ≤10 steps before human intervention, and reliability is the top development challenge. — [https://arxiv.org/abs/2512.04123](https://arxiv.org/abs/2512.04123)

- **LangChain blog (June 2026):** Three evaluation tiers (run/trace/thread) — trajectory evaluation catches failures that outcome-only scoring misses. Reports 89% of orgs have observability but only 37% run online evals. — [https://www.langchain.com/resources/agent-evals](https://www.langchain.com/resources/agent-evals)

- **arXiv (May 2026, UCBerkeley):** BenchJack agent achieved 100% on Terminal-Bench and SWE-bench Verified not by solving tasks but by exploiting evaluation infrastructure. Taxonomy of eight recurring flaw patterns in agent benchmarks. — [https://arxiv.org/abs/2605.12673](https://arxiv.org/abs/2605.12673)

- **arXiv (Oct 2025, EACL 2026):** BenchAge study found 24.19% average of factuality benchmark items are outdated — penalizing models for giving the currently correct answer. — [https://arxiv.org/abs/2510.07238](https://arxiv.org/abs/2510.07238)

- **Engineering blog (June 2026):** Trace-to-test-suite methodology: cluster production failures, keep one representative golden per cluster, version the dataset, gate CI on regression suite. Emphasizes specific failure labels over vague categories. — [https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/](https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/)

- **Engineering blog (July 2026):** Practitioner playbook — task success rate, cost-per-task, latency, and drift over time are the four core metrics. Emphasizes span-level tracing for root cause isolation. — [https://prefactor.tech/blog/agent-evaluation-in-production-what-to-measure-and-how-to-prove-it](https://prefactor.tech/blog/agent-evaluation-in-production-what-to-measure-and-how-to-prove-it)

## Gotchas

- **Datasets inflate your numbers without adding signal.** A large, stale golden dataset passes on near-duplicates while missing new failure shapes. Quality and recency of the dataset matter more than quantity.
- **LLM judges need calibration per domain.** A judge trained on general reasoning quality may be 15+ points off for domain-specific output requirements. Always run a small human-label calibration set before trusting judge scores at scale.
- **Observability ≠ evaluation.** Tracing what your agent did is not the same as judging whether what it did was correct. Most teams have the former without the latter.
- **The eval → deploy gap is real.** Even teams with good eval infrastructure often don't gate deployment on eval results. The eval is useless if it doesn't block or flag bad deploys.
- **Multi-agent interaction effects are evaluated last, if at all.** Individual agent quality doesn't sum to system quality. An eval framework that tests each agent in isolation will miss coordination failures, shared-state corruption, and cascading errors between agents.
