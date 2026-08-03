# S-2091 · The Evaluation Stack — When Your Pass1 Is Green but Production Is on Fire

Your agent gets 94% on your test suite. It gets deployed. Three weeks later, an incident report surfaces: a cascading silent failure burned $47,000 in fraud before anyone noticed. The test suite didn't catch it because it was never designed to. Lab benchmarks, passing CI gates, and team "gut checks" are three different ways to miss the same thing — the gap between how agents behave in evaluation and how they behave in production.

This is the evaluation stack: the layered approach that closes the gap between agent quality in the lab and agent reliability in production.

## Forces

- **Lab benchmarks measure capability, not reliability.** HELM, MT-Bench, AgentBench, and BIG-bench score whether a model *can* do something in a controlled episode. They don't measure whether your agent *does* its job continuously in production under edge conditions, tool failures, and input drift.
- **"Vibe checks" have three failure modes.** Teams test happy-path queries, anchor their judgment to what shipped last time (not what users need), and have no regression harness — so silent degradation between versions goes undetected for weeks.
- **The constraint decay problem is invisible to pass/fail metrics.** A coding agent can ace its baseline API contract and drop ~30 percentage points once framework, database, and ORM constraints stack on top. Standard metrics don't catch this progressive fragility.
- **Production introduces non-determinism at scale.** One user request may produce 15+ different tool-call paths depending on intermediate results. Checking the final output tells you nothing about which path got there or what quietly broke on the way.
- **Evals without a feedback loop are decoration.** Scores that don't change what ships are vanity metrics. The value of an eval is measured by how it closes the loop — turning a failure into a test case, a monitor, or a context fix.

## The Move

A four-layer evaluation architecture that gates deployment and monitors production continuously:

### Layer 1 — Deterministic Checks (microseconds, zero cost, no LLM needed)

Programmatic assertions that run on every response before it's returned:

```
def check_response(response: str) -> EvalResult:
    checks = [
        assert_response_valid_json(response),       # format correctness
        assert_no_forbidden_patterns(response),     # safety patterns
        assert_output_length_bounds(response),      # cost control
        assert_required_fields_present(response),   # schema contract
    ]
```

These run in CI, cost nothing, and catch structural regressions (wrong format, missing fields, policy violations) instantly. They cannot catch whether the *meaning* is correct.

### Layer 2 — Golden Datasets (the hard part that teams skip)

A curated set of 100–200 query–answer pairs, built by domain experts (not engineers), covering:

- Happy-path queries (to establish baseline)
- Edge cases: null values, Unicode names (O'Brien, José, 北京), empty fields, concurrent requests
- Adversarial inputs: prompt injection attempts, malformed inputs
- Multi-turn trajectories: tasks that require 5+ steps of reasoning

**The golden dataset is the canonical truth for your agent.** It gates pre-deployment and enables regression testing across model and prompt changes. Without it, you're comparing output to vibes.

Building it: mine real production queries → expert annotation (not engineer judgment) → cover edge cases explicitly → version the dataset → re-annotate quarterly.

### Layer 3 — LLM-as-Judge (for anything requiring judgment)

Use an LLM as an automated grader for subjective quality — tone, helpfulness, reasoning quality, adherence to policy. Two modes:

- **Deterministic checks + LLM-as-judge for quality:** The judge evaluates against a rubric. For exact-match domains (code correctness, math), use deterministic assertions. For anything requiring judgment, use the LLM-as-judge.
- **Trace-based evaluation:** Score the *trajectory* — was the path efficient, were the right tools called in the right order, did the agent recover from failures? Confident AI's DeepEval and LangSmith both support trajectory-level scoring.

### Layer 4 — Production Monitoring (the layer that catches what pre-deployment misses)

Deployed agents must emit structured traces to a time-series evaluation store. Monitor:

| Metric | What It Catches |
|--------|----------------|
| End-to-end task completion rate | >90% target for well-defined workflows |
| Partial completion rate | Agent made progress but didn't finish |
| Failure rate by type | Model error, tool error, timeout, quality rejection |
| Human intervention rate | How often humans must override or correct output |
| Entropy drift (per-call) | Statistical process control on rolling evaluation scores — catches model provider updates that degrade a task class by 8% across thousands of executions within 24 hours |

Set p-value thresholds on rolling 24-hour windows of task-completion fidelity scores. This catches population-level regression — distributed failures that individual task evaluation misses.

## Evidence

- **Research: arXiv production evaluation paper (May 2026)** — Found that standard benchmarks (HELM, MT-Bench, AgentBench, BIG-bench) fail to detect 4 of 7 production failure modes entirely and detect the other 3 only after multi-cycle lag. Proposes a framework for continuous production evaluation covering compounding decision errors, tool failure cascades, output drift, and absence of ground truth for long-horizon tasks. — [arXiv:2605.01604](https://arxiv.org/html/2605.01604)

- **Engineering: LangChain ADLC blog (May 2026)** — Harrison Chase formalizes the Agent Development Lifecycle: Build → Test → Deploy → Monitor. Key principle: evals operate in two stages — pre-deployment gating ("is this version ready to release?") and production feedback ("what should the next version fix?"). Scores only matter when they change what ships. — [LangChain Blog: The Agent Development Lifecycle](https://www.langchain.com/blog/the-agent-development-lifecycle)

- **Engineering: LangChain evals documentation (Mar 2026)** — LangChain's eval documentation defines the distinction precisely: benchmarks measure raw model capability against a fixed test set (one-time, when choosing a base model); evals score the whole system on actual behavior continuously, covering specific tasks, data, policies, prompts, and tools. — [LangChain: LLM Evals](https://www.langchain.com/resources/llm-evals)

- **Industry: Forasoft evaluation guide (Jul 2026)** — Reports MIT Project NANDA (2025) finding that 95% of enterprise generative-AI pilots produced zero measurable P&L impact; RAND (2025) placed failure rate at 80.3%. Cites the $47,000 prompt injection fraud (Jan 2026) and $4,050 first-year cost of a proper eval pipeline versus tens of thousands in prevented churn. — [Forasoft: LLM Evaluation in Production](https://www.forasoft.com/blog/article/llm-app-evaluation-production-2026)

- **Research: Constraint decay paper (arXiv, May 2026)** — Found that coding agents passing a baseline API contract drop ~30 percentage points in assertion pass rate once framework, database, and ORM constraints accumulate. Prohibition constraints decay faster than commission constraints as conversation depth grows. — [arXiv:2605.06445](https://arxiv.org/pdf/2605.06445v1)

- **Engineering: Harness engineering blog (Mar 2026)** — Proposes three evaluation layers: (1) individual task evaluation, (2) integration tests against full pipeline, (3) population-level regression detection via statistical process control on aggregated evaluation scores. The third layer catches model-provider updates that shift a task class by 8% across thousands of executions. — [Harness Engineering: Agent Evaluation & Observability in Production AI](https://harness-engineering.ai/blog/agent-evaluation-observability-in-production-ai/)

## Gotchas

- **Your golden dataset will go stale.** User language shifts, edge cases you didn't anticipate enter production, and model behavior drifts. Re-annotate quarterly and mine fresh queries from production logs continuously.
- **Pass/fail metrics hide trajectory quality.** An agent can reach the right answer through a catastrophically wrong path — or fail to reach the right answer through a mostly-correct path with one recoverable error. Score the trajectory, not just the outcome.
- **Silent failures are the dangerous ones.** Agents that appear functional in logs can quietly return malformed outputs, propagating errors through multiple steps before surfacing downstream. The Harness paper calls this "entropy accumulation" — it requires statistical monitoring on aggregated traces, not per-call assertions.
- **LLM-as-judge has judge bias.** The judge model may be systematically lenient or harsh on your specific domain. Calibrate it against human annotations before relying on it for high-stakes decisions.
- **Your CI gate is only as good as your dataset.** If the golden dataset doesn't cover the failure mode that hit production, the gate provides false confidence. Coverage analysis of your dataset against real production failure logs is not optional.
