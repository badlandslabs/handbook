# S-2414 · The Probability of Okay Stack — When Your Agent Isn't Quite Right but You Can't Prove It

Your agent works. You ran it ten times and nine it came back fine. But Gartner says over 40% of agentic AI projects get cancelled by end of 2027 — and inadequate evaluation frameworks are the top cited reason. The problem isn't that nothing is measured. It's that most teams measure the wrong things: they check if the agent succeeded this run, not whether it's reliable across runs, safe in its reasoning, or cost-efficient at scale.

## Forces

- **Single-run accuracy lies.** An agent achieving 60% success on one run drops to 25% across eight runs. Outcome-only metrics hide the variance that's catastrophic in production.
- **Trajectories matter as much as outputs.** An agent that calls the wrong tool, recovers, and lands on the right answer still taught users to trust a brittle system.
- **Agents fail in ways deterministic software can't.** Silent cascade errors, tool-call failures that look like success, gradual drift from a baseline nobody pinned down.
- **LLM outputs resist ground-truth comparison.** Summaries, analyses, and judgments often have multiple valid forms — you can't diff your way to correctness.

## The move

Evaluate on two axes at minimum, across both pre-deployment and production phases.

**Two-tier metric structure:**
- **Trajectory metrics** — did the agent take a sound reasoning path? (tool-call order, recovery from errors, context usage)
- **Outcome metrics** — did it actually solve the task? (accuracy, completeness, latency, cost)

**Measure reliability, not just capability:**
- `pass@k` — probability agent succeeds at least once in k attempts. Optimistic. Answers: *can it do this at all?*
- `pass^k` — probability it succeeds on every one of k attempts. Answers: *can we depend on it?* Most production use cases need the latter.

**Build a golden dataset before you need it:**
- Curate 50–200 real production inputs with expert-labeled expected outcomes and trajectories
- Include edge cases, adversarial inputs, and failure-mode examples
- Refresh quarterly — stale golden sets miss drift

**Use LLM-as-judge for qualitative dimensions:**
- Train rubric prompts that operationalize "good" for your domain (not generic likert scales)
- Calibrate judges against human-labeled subsets — target 0.80+ Spearman correlation before trusting scores
- Combine with deterministic checks for what machines can verify (JSON schema, PII presence, exact-match facts)

**Tier evals by cost and run them in CI/CD:**
- **Fast deterministic checks** (schema validation, fact anchoring, safety patterns): run on every PR, complete in minutes
- **Expensive trajectory evals** (LLM-judge on large datasets): nightly or pre-release gates
- Gate merges on pass-rate thresholds — regressions cannot ship without explicit override

**Monitor production for what pre-deployment misses:**
- Task completion rate, tool error rate, token consumption per task, latency distribution
- Anomaly detection for gradual drift — threshold alerts catch sudden drops but miss slow degradation

## Evidence

- **Survey (arXiv):** *Evaluation and Benchmarking of LLM Agents: A Survey* (2025) — maps the fragmented eval landscape and argues systematic assessment is essential before production deployment. — https://arxiv.org/abs/2507.21504
- **Blog post (Galileo AI):** *Agent Evaluation Framework* — documents the 40%+ cancellation stat and proposes trajectory + outcome as the two non-negotiable evaluation dimensions. — https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks
- **Engineering post (Bayer + Thoughtworks on Martin Fowler):** PRINCE multi-agent system uses structured eval pipelines with defined success criteria per agent role; found that boundary failures (wrong tool, dropped context) were only caught via trajectory-level evaluation. — https://martinfowler.com/articles/reliable-llm-bayer.html
- **Engineering blog (Google Cloud):** Vertex AI Gen AI evaluation service explicitly evaluates both final response and agent reasoning trajectory, noting that understanding "the why behind an agent's actions" is essential for reliability. — https://cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service

## Gotchas

- **Running golden dataset evals in Jupyter notebooks is not evaluation infrastructure.** It works once, then rots. Evals must be automated, versioned, and triggered by code changes.
- **LLM-as-judge has calibration drift.** The judge model changes, the rubric prompt drifts, or domain-specific cases slip through. Re-calibrate against human labels regularly, not just at launch.
- **pass@k is not a reliability metric.** Shipping on pass@k means you're claiming the agent is reliable because it sometimes works. For any production dependency, use pass^k and set the threshold based on business cost of failure.
- **Silent failures are the real danger.** An agent that returns wrong data in the right format passes output-only checks. Only trajectory evaluation — tracing tool calls, intermediate decisions, context usage — catches this.
