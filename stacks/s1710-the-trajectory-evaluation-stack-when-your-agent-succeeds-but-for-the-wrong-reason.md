# S-1710 · The Trajectory Evaluation Stack — When Your Agent Succeeds But For the Wrong Reason

Your agent returns the right answer 95% of the time. Your test suite passes. Your manager is satisfied. Then you discover the agent is ignoring authentication checks, calling sensitive tools before permission validation, and recovering by luck — not design. Every deployment works in the demo and surprises you in production. The problem isn't the answer. It's the path to it.

Endpoint scoring tells you the destination. Trajectory evaluation tells you whether you should trust the journey.

## Forces

- **The gap between correctness and safety** — an agent can reach the right answer through a reckless trajectory: wrong tool first, lucky recovery, ignored constraints that didn't bite this time. Endpoint scores miss this entirely.
- **Non-determinism demands statistical rigor** — a single trial on a single example is meaningless for agents; variance is structural, not noise.
- **Public benchmarks are broken** — UC Berkeley researchers found all eight prominent agent benchmarks can be gamed to near-perfect scores without solving a single real task. One team gamed 890 tasks with a single character change.
- **The eval investment trap** — teams over-invest in prompt iteration and under-invest in measurement infrastructure, then ship blind.
- **Process vs. output confusion** — testers grade the essay, not the math that produced it. For agents, the logic matters as much as the conclusion.

## The Move

Evaluate the trajectory, not just the output. Build a two-dimensional eval system:

**Trajectory evaluation (the process):** Score which tools were called, in what order, with what arguments, and whether each step satisfied business logic and policy. Did `check_inventory` run before `place_order`? Did authentication happen before balance inquiry? This is logic and regression testing — it catches the failure mode that endpoint scoring hides.

**Response evaluation (the output):** Is the final answer correct, grounded, and safe? This is the familiar output-quality check.

**Then layer four supporting practices:**

1. **Golden datasets with step-level rubrics.** A case schema with: `id`, `input`, `expected_steps[]`, `step_rubric{}`, and `response_criteria`. Version-controlled, seeded with 50–200 real production examples. Re-run critical scenarios multiple times — a single pass on stochastic outputs misleads you more than it informs you.

2. **Statistical regression over single trials.** Run each example 10+ times. Track pass rate variance, not just pass/fail. A held-out set you never tune against catches overfitting to the eval itself.

3. **Trace-first observability.** Capture the full call graph — LLM spans, tool calls, framework steps, per-span latency, and token usage. Not only to debug failures, but to build the dataset of real trajectories that become your next round of test cases.

4. **LLM-as-judge + human sampling.** Use an LLM judge for broad coverage at speed. Use human review on a random sample of traces to calibrate the judge and surface "metric green, user red" cases. They complement each other — judges scale, humans correct drift.

**Track operating envelopes in the same system as quality:** cost per task, latency per step, token budgets. A passing eval at 10× the cost or latency is not a passing eval.

## Evidence

- **Anthropic Engineering Blog (Jan 2026):** "The capabilities that make AI agents useful — autonomy, intelligence, and flexibility — also make them harder to evaluate." Proposes task/trial/grader taxonomy; emphasizes trajectory + response as the two eval dimensions. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Ask HN: Testing AI Agents (harperlabs, ~4 months ago):** Framework identifying 7 failure modes teams don't test before shipping: hallucination under unexpected inputs, edge case collapse (nulls, Unicode), prompt injection, context limit surprises (silently misbehaves when window fills), cascade failures (tool error compounds across 3+ calls), regression, and agent loops. Notably: "Most teams test #1 and #3. Almost no one systematically tests #4, #5, and #6." — [URL](https://news.ycombinator.com/item?id=47325105)

- **Google ADK Codelab:** "You aren't just grading the Essay (Final Response); you are grading the Math (The logic/tools used to get there)." Distinguishes trajectory evaluation (logic/regression) from response evaluation (output quality), using a customer service agent flow as worked example. — [URL](https://codelabs.developers.google.com/adk-eval/instructions)

- **James M, Practitioner Guide (Jun 2026):** "An agent can reach the right answer through a reckless path: wrong tool first, lucky recovery, ignored constraints that did not bite this time." Minimum viable setup: 50–200 real examples, per-step rubrics, 10+ runs per example, statistical regression tracking, held-out set never tuned against. Introduces replay harnesses for re-running captured traces against new models without re-hitting production. — [URL](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)

- **Zylos Research / Berkeley RDI:** "One team gamed 890 tasks with a single character change. Several systems hit 100% on multiple benchmarks while solving zero real problems." — [URL](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)

- **Confident AI:** "90% of AI development time should be spent on evaluation and observability rather than prompting." Recommends DeepEval for `@observe` and inline metrics, with separate trace/online-eval tooling for production — [URL](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

## Gotchas

- **Single-trial endpoint scoring is theater.** A pass on one run of one example tells you almost nothing about reliability. You need distribution over runs, not a single point estimate.
- **Golden datasets rot.** Real inputs drift as product changes. A golden dataset that isn't versioned and periodically refreshed becomes a false security blanket — it passes while production fails silently.
- **Judge calibration drifts.** LLM-as-judge scores shift across model versions. Re-calibrate against human-labeled samples before each major shipping gate, not just at eval suite creation time.
- **Trajectory eval catches the path, not the edge case.** You still need fuzzing and adversarial input testing (Unicode names, null values, concurrent requests) to find which paths get triggered. Trajectory eval tells you whether the path was right; it doesn't discover all the paths that exist.
- **Cost and latency are eval outputs, not afterthoughts.** Track them in the same trace infrastructure. A model upgrade that improves quality but 10× cost or latency isn't an improvement for a production system — and you won't catch it without envelope metrics in the eval pipeline.
