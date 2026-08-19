# S-2862 · The Regression Gate Stack

[When your agent shipped and nobody noticed it got worse — a prompt tweak broke 30% of tool calls, and you found out from a customer, not a test.]

## Forces

- **Probabilistic outputs break traditional tests.** `assert output == expected` can't hold when the same input produces graded, non-deterministic outputs. Teams that tried to treat LLM output like software output ended up with either brittle tests or no tests.
- **A passing benchmark is not a passing agent.** MMLU, HumanEval, and SWE-bench are static snapshots of base model capability — not indicators of whether your specific agent workflow broke after swapping a model version or editing a system prompt. Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation, not model capability gaps.
- **Human spot-checking doesn't scale.** A developer spending 2 hours manually reviewing outputs per PR is a bottleneck and a noise source. But running evals manually is better than nothing, and teams that automated that manual process first saw the fastest quality improvements.
- **Regression on known-good behavior is the silent killer.** The agent that works fine in staging and fails in production on cases nobody thought to test is the mode of failure. The fix is a curated golden dataset — representative inputs with known-good outputs or scoring rubrics — that evolves with every production failure.

## The Move

Build a regression gate that fires on every pull request: a curated golden dataset + multi-scorer eval harness + CI quality gate that fails the build when aggregate scores drop below a configurable threshold.

### The four-layer eval stack (from pre-deployment to production)

1. **Capability benchmarks** (pre-deployment gate) — run against general-purpose datasets (MMLU, HumanEval) to catch base model regressions when you swap model versions. Fast, automated, but not specific to your workflow.
2. **Golden dataset offline evals** (PR gate) — your own curated test set. Inputs paired with expected outputs or structured scoring rubrics. Run on every pull request. This is where most teams win or lose.
3. **Shadow / online evals** (staging or canary) — live traffic on a small percentage of requests, evaluated against the same golden rubric without blocking the user response. Catches distribution drift that static datasets miss.
4. **Production monitoring** (continuous) — score production traces in real time, alert on score drops, and route confirmed failures back into the golden dataset to close the loop.

### Building the golden dataset

- Size: **50–100 cases minimum** for routine agents; **300+ for mission-critical** workflows.
- Source: Production traces first — every confirmed failure becomes a test case. Supplement with adversarial inputs and edge cases.
- Coverage: At least 5 cases per tool the agent can call. Include inputs known to trigger known failure modes.
- Format: Inputs + expected outputs or a structured rubric (a list of criteria the response must satisfy).

### Multi-scorer approach

Combine three scoring layers — never rely on one:

| Scorer type | What it catches | When to use |
|---|---|---|
| **Deterministic / code-based** | Exact output matches, JSON schema validation, metric calculations | Fast, reproducible, no LLM cost. Use for anything with a verifiable ground truth. |
| **LLM-as-judge** | Output quality, relevance, coherence, adherence to rubric | When ground truth is ambiguous. Must be calibrated against human labels first — uncalibrated judges systematically prefer verbose, confident-sounding outputs. |
| **Trajectory / span-level** | Tool-call sequences, approval gate adherence, recovery paths | When the path matters as much as the outcome. Catches agents that get the right answer via the wrong steps. |

### CI/CD integration pattern

```yaml
# promptfooconfig.yaml — Promptfoo eval gate in CI
providers:
  - id: openai:gpt-4o
    config:
      temperature: 0.3
tests:
  - vars:
      input: "What is the status of order #12345?"
    assert:
      - type: contains
        value: "order"
      - type: javascript
        value: "functionAssert()"
      - type: llm-rubric
        value: "Response acknowledges the order exists and provides a status or asks for clarification."
```

```python
# deepeval pytest test — DeepEval CI gate
from deepeval.metrics import TaskCompletenessMetric
from deepeval.test_case import LLMTestCase

def test_order_status_agent():
    metric = TaskCompletenessMetric(threshold=0.85)
    test_case = LLMTestCase(
        input="What is the status of order #12345?",
        expected_output="A response acknowledging the order",
        actual_output=agent.run("What is the status of order #12345?")
    )
    metric.measure(test_case)
    assert metric.success, f"Score: {metric.score}"
```

### The regression baseline

On first successful run, capture the aggregate scores as the **immutable baseline**. Every subsequent run compares against that baseline. The CI gate fails if:
- Overall score drops below a threshold (e.g., 90% pass rate)
- Per-metric scores drop by more than N percentage points vs baseline
- A previously passing scorer now fails

Track the baseline alongside code in git — every baseline lives at a specific commit.

## Evidence

- **GitHub repo (evalharness):** A reusable LLM evaluation harness implementing golden test sets, LLM-as-judge scoring, regression detection against a baseline, and a CI quality gate that fails the build when quality drops. Frames the core insight: "Traditional tests assert `f(x) == y`. LLM outputs are non-deterministic and graded, not equal." — [github.com/siddhashutosh/evalharness](https://github.com/siddhashutosh/evalharness)
- **Engineering blog (AgentMarketCap):** Teams with eval infrastructure reach stable production in 1/3 the time of teams that skipped it — not because their agents are better, but because they diagnose failures in pre-production instead of reacting to them post-deploy. Pre-launch checklist: 100+ golden cases, ≥90% tool-correctness, ≥85% task completion, LLM-judge rubrics calibrated against human baselines, eval gates on every PR at ≥90% threshold (≥95% for PII/financial workflows). — [agentmarketcap.ai/blog/2026/04/10/building-ai-agent-evals-cicd-2026](https://agentmarketcap.ai/blog/2026/04/10/building-ai-agent-evals-cicd-2026)
- **Platform docs (Braintrust):** Braintrust's offline evaluation flow: iterate in playgrounds → promote to an immutable experiment snapshot → automate in CI/CD as a deployment gate → score production traffic continuously → feed confirmed production failures back into the offline dataset. Production traces are the highest-quality source for golden dataset expansion. — [braintrust.dev/docs/evaluate](https://www.braintrust.dev/docs/evaluate)
- **Industry survey (arXiv 2507.21504):** Documents the shift toward Evaluation-driven Development (EDD) — integrating evals directly into the development lifecycle rather than treating them as a post-hoc step. Identifies DeepEval, InspectAI, Phoenix, and GALILEO as the leading open-source/commercial tools providing evaluation orchestration, analytics, and debugging capabilities. — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)

## Gotchas

- **Skipping LLM-judge calibration is the most common mistake.** An uncalibrated judge will score verbose, confident-sounding outputs higher than correct, concise ones. Calibrate by having the judge score 20-30 cases that a human has already scored, then measure agreement before trusting it at scale.
- **Golden datasets rot.** Inputs and acceptable outputs shift as your domain evolves. A dataset that was accurate 6 months ago may not reflect current business logic. Treat dataset maintenance as a first-class engineering task — route every confirmed production failure back into it.
- **Threshold tuning requires iteration.** Setting the gate at 95% when your baseline is 87% means every PR fails and nobody pays attention. Start permissive (e.g., allow ±3% from baseline), observe the signal for 2-3 weeks, then tighten. An ignored gate is no gate at all.
- **Offline eval coverage is always a subset of production distribution.** Shadow evaluation on live traffic catches failure modes that never made it into the golden dataset. Don't treat offline evals as sufficient — they are necessary but not sufficient.
