# S-2373 · The Multi-Layer Eval Harness

When your agent passes a demo, your team celebrates, and you deploy — without ever building the infrastructure that would tell you whether it still works when the model updates, the prompt changes, or real users hit edge cases.

## Forces

- **Eval infrastructure is always the last thing built.** Teams ship agents with dashboards and monitoring but no eval suite. The first model update lands silently and nobody knows until customers complain.
- **Pass@1 is not reliability.** An agent achieving 60% success on a single run drops to ~25% across 8 consecutive runs (Operator Collective, 2025). Standard test suites measure capability, not consistency.
- **Trajectory matters more than output.** An agent can return the right answer via a broken path — calling the wrong API, using stale data, or hallucinating a tool response. Google Cloud calls these "silent failures": result looks right, execution failed. Output-only scoring misses them entirely.
- **Eval quality is the throttle on iteration speed.** NINtec (2026) observes that investing in good golden sets early pays back across the entire eval iteration cycle. Teams that skip this spend more time debugging unexplained regressions.
- **The lab-to-production gap is ~37%.** Benchmark performance routinely overstates real-world reliability by a significant margin (Jobs by Culture, 2026).

## The Move

Build a four-layer eval harness that runs offline in CI and online in production. Each layer gates a different failure mode.

### Layer 1 — Golden Set Regression (offline, CI-gated)

Curated input-output pairs covering the workload's full distribution. Source cases from real production failures, not synthetic generation alone. Run after every prompt or model change. Version the dataset alongside code. Key properties:

- **Deterministic assertions** for factual correctness (exact-match on structured outputs, schema validation)
- **Golden traces** for multi-step task success (expected tool-call sequence + final output)
- **Edge case bank** — Unicode names (O'Brien, José, 北京), null values, concurrent requests, adversarial inputs

### Layer 2 — Judge-LLM Scoring (offline, CI-gated)

Automated rubric-based scoring against dimensions that exact-match cannot capture. The rubric is the operative artefact — not the judge model. Score across:

- **Plan quality** — did the agent reason toward the right goal?
- **Tool selection** — did it call the correct tools in the right order?
- **Execution correctness** — did it handle tool responses and errors?
- **Output quality** — does the result satisfy the user's intent?

NINtec (2026) and Braintrust (2026) both report that rubric-based judge scoring catches failures invisible to binary pass/fail. Mastra (2026) notes that `pass@k` (probability of at least one success in k trials) measures capability, while `pass^k` (probability of succeeding in all k trials) measures reliability — and these can diverge dramatically at high step counts.

### Layer 3 — CI Quality Gates (offline, pre-deploy)

Wire the eval harness into the development workflow. Every PR runs the full offline suite. Braintrust surfaces scores directly in pull requests. Required practices:

- **Canary + A/B** for significant changes: route live traffic to the new variant, compare goal completion rates and cost-per-task before full rollout
- **Canary metrics minimum:** task success rate, median latency, cost delta vs. baseline
- **Regression threshold:** block merge if any critical-path golden set drops below baseline, or if cost-per-task increases >15%
- **Eval saturation check:** a suite at 100% tracks regressions but gives no signal for improvement — rotate and expand cases quarterly

### Layer 4 — Production Drift Monitoring (online, continuous)

Capture every production trace. Score production logs against golden cases on a sample. Feed confirmed failures back into the golden set. Key signals:

- **Goal completion rate** over rolling windows (daily/weekly)
- **Cost-per-task** trend — models drift in pricing and token consumption between versions
- **Trajectory deviation** — alert when the agent's tool-call pattern diverges from expected paths even if the output is correct
- **Golden set enrichment loop:** every production failure becomes a test case within 48 hours

## Evidence

- **Braintrust Framework:** Evaluates agents layer-by-layer — plan quality, tool selection, execution — with CI/CD integration that gates releases. Scores surface in pull requests. Cross-framework compatibility means teams aren't locked in. — [https://www.braintrust.dev/articles/ai-agent-evaluation-framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- **Google Cloud Blog:** Recommends measuring trajectories, not just outputs, and capturing real production interactions as test cases. "An agent tasked with reporting inventory might give the correct number but reference last year's report by mistake." — [https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **72Technologies:** Three factors break the standard testing playbook: non-determinism (even at temperature=0, models occasionally return different tokens — documented by both Anthropic and OpenAI), silent model drift (the same model ID can return different results months apart), and tool signature changes. — [https://www.72technologies.com/blog/agent-evals-ci-regression-tests](https://www.72technologies.com/blog/agent-evals-ci-regression-tests)
- **NINtec:** Production eval harnesses require three core components: golden-set construction (input-output pairs covering full distribution), judge-LLM scoring against workload-specific rubrics, and drift monitoring to catch silent regressions between releases. — [https://www.nintecsystems.com/insights/evaluating-claude-production-eval-harnesses](https://www.nintecsystems.com/insights/evaluating-claude-production-eval-harnesses)
- **InfoQ:** "Traditional LLM evaluation methods treat agent systems as black boxes and evaluate only the final outcome, failing to provide sufficient insights to determine why AI agents fail or pinpoint root causes." — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Maxim AI:** Goal completion rates below 55% for CRM-connected agents in production. Error rates compound exponentially in multi-step workflows — 90% per-step reliability yields ~65% overall for a 7-step workflow. — [https://www.getmaxim.ai/articles/ensuring-ai-agent-reliability-in-production/](https://www.getmaxim.ai/articles/ensuring-ai-agent-reliability-in-production/)

## Gotchas

- **Benchmark saturation is a false positive.** A suite scoring 100% catches regressions but tells you nothing about whether the agent is improving. Rotate cases and expand coverage quarterly.
- **Output-only scoring hides broken execution.** The agent can land on the right answer through the wrong path. Trajectory inspection catches this; output comparison misses it.
- **Golden sets rot.** Production distributions shift. Cases sourced once from a snapshot become stale. Continuous enrichment from production failures is not optional — it's the only way to maintain signal.
- **Eval at the end is too late.** Adding evaluation infrastructure after an agent is already complex makes debugging harder and the refactoring cost higher. Start with a minimal golden set and one judge dimension on day one, even before the agent is production-grade.
- **Non-determinism makes single-run pass/fail meaningless.** A pass at 25°C (one trial) doesn't mean the agent is reliable. Report `pass^k` across multiple runs for reliability, not `pass@1` for capability.
