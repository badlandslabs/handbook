# S-1893 · The Evals Stack — The Gap Between What Your Agent Reports and What It Actually Did

The moment your agent runs in production, your APM dashboard goes green and your quality metrics go dark. You know the agent ran. You don't know if it ran correctly. Traditional software reliability metrics — uptime, error rate, latency — tell you nothing about whether the agent actually did what the user asked. The gap between "agent completed" and "task resolved" is where quality goes to die.

## Forces

- **Completion ≠ correctness** — agents reliably finish tasks they haven't actually resolved, and they'll tell you so confidently
- **Standard benchmarks miss production failures** — curated test sets don't cover the real input distribution your users actually send
- **The trace is the product** — every metric worth having is derived from the execution trace; without it you have nothing to measure
- **Stochasticity demands repeatability infrastructure** — one run is noise; a suite of reproducible evals is signal
- **Human judgment is slow and expensive** — it scales poorly but remains the ground truth calibrator

## The move

**Instrument first, eval second.** You cannot evaluate what you cannot observe. Build tracing into your agent from the start, then layer evaluation on top of those traces.

**Track three evaluation layers simultaneously:**

- **End-to-end (task completion):** Did the agent successfully complete the user's request? Gold standard tests + LLM-as-judge score the full trajectory. This is your primary quality signal.
- **Component-level (tool correctness):** Did the agent call the right tools with the right arguments? Schema validators catch malformed calls; deterministic checks catch wrong parameters.
- **Operating envelope (cost/latency/step budgets):** Track tokens per trace, latency per step, and step counts. An agent can be correct and economically unviable.

**Build a two-loop eval system:**

- **Offline eval loop:** Pre-deployment. Golden dataset runs in CI on every prompt/model change. Deterministic scorers for anything with ground truth; rubric-anchored LLM-as-judge for subjective quality. Gate deployments on eval thresholds.
- **Online eval loop:** Production traffic. Continuous scoring on a sampled slice of live traces. Catch regressions the moment they emerge — before your users do.

**Watch for silent semantic failures.** The most dangerous agent failure mode is one that returns HTTP 200 and sounds confident: the agent submits a patch, declares success, and the work is actually wrong. Detect this by separating *submit rate* (how often the agent reports completion) from *resolve rate* (how often the task is actually solved). The gap between the two is your hidden defect surface.

**Use statistical process control on eval scores over time.** Rolling windows of task-completion fidelity scores will catch model-provider updates that degrade performance across a specific task class — failures that individual eval runs miss because they're distributed across thousands of executions.

**Calibrate LLM-as-judge with human review.** LLM judges are fast and scalable but drift. Sample traces reviewed by humans calibrate the judge and surface "metric green, user red" cases — where automated scores look fine but real users are dissatisfied.

## Evidence

- **MAP study (ICML 2026):** First systematic study of 86 production agent deployments across 26 domains. Key finding: 74% of production teams depend primarily on human evaluation, and **no team reports applying standard production reliability metrics** (e.g., five-nines availability) to their agent systems. Evaluation focuses on whether agents produce correct outputs, not traditional software reliability. 68% of agents execute at most 10 steps before human intervention. — [arXiv:2512.04123](https://arxiv.org/abs/2512.04123) / [IBM Research](https://research.ibm.com/publications/measuring-agents-in-production)

- **Silent semantic failures in coding agents (arXiv 2026):** Across 1,750 trajectories on SWE-bench Verified tasks, submit rates ranged from 70–100% while resolve rates ranged from 18–65% across frontier models. Llama 4 Maverick had the highest submit rate (99%) but lowest resolve rate (18%) — an 81 percentage-point gap. Monitoring submit rate alone ranks models in the **wrong order**. Gemini submits least often (70%) but resolves more tasks than GPT-5 (50% vs 44%). — [arXiv:2603.25764](https://arxiv.org/html/2603.25764)

- **Golden dataset + CI regression gates:** A practical eval harness (jbelnick/llm-judge-evals) uses hand-labeled golden datasets, deterministic fidelity scorers, a rubric-anchored LLM judge with code-enforced guardrails, and a CI regression gate. `make drift` demonstrates the gate catching a model swap that introduces subtle regressions (e.g., a price field changing scale from 0.09832 to 0.9832 — fluent output, wrong answer). — [GitHub jbelnick/llm-judge-evals](https://github.com/jbelnick/llm-judge-evals)

- **HN discussion — "What broke when I tried to evaluate an AI agent in production":** A practitioner reports that benchmark-style eval approaches failed in unexpected ways — specifically, agent behavior varied across runs on the same inputs due to model non-determinism, making reproducible scoring difficult without trace-based replay infrastructure. — [Hacker News #47416033](https://news.ycombinator.com/item?id=47416033)

- **YC W25 Launch — Lucidic:** AI agent observability platform built after founders struggled with debugging complexity developing e-commerce and math olympiad agents. One-line initialization (`lai.init()`) with step-level metadata, memory, and tool output tracking. 116 HN points on launch. — [Hacker News #44735843](https://news.ycombinator.com/item?id=44735843)

## Gotchas

- **Don't conflate APM with agent quality.** HTTP 200 means the API worked. It tells you nothing about whether the agent's reasoning was sound or its output was correct.
- **Don't trust LLM-as-judge without calibration.** Judges have position bias (preferring the first or last option in a list), can be fooled by fluent-but-wrong outputs, and drift over time. Human rubrics on sampled traces are the calibration anchor.
- **Don't skip operating envelope metrics.** An agent can score 95% on quality evals while burning 10× your token budget per request. Track cost and step counts in the same traces as quality.
- **Don't evaluate once.** One eval run is a snapshot, not a trend. Regression detection requires population-level statistical analysis over sliding windows — catching the model update that degraded performance by 8% across a specific task class.
- **Don't evaluate only at deployment.** Production traffic surfaces failure modes that handwritten test sets never cover. Continuous online evals on sampled live traces catch what pre-deployment testing misses.
