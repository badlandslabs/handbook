# S-1824 · The Eval-First Stack: When You Build Agents Before You Can Prove They Work

You have a multi-step agent working in dev. You ship it. Three weeks later, a silent regression surfaces — the agent now fails 30% of the time on a specific input class, and you only find out when a user files a complaint. You have no regression suite, no baseline, no idea when it broke. The eval-first stack prevents this by making quality measurable before the agent ships, not after.

## Forces

- **The non-determinism tax** — agents are inherently stochastic. A passing manual test tells you almost nothing about reliability. Without a structured eval suite, you ship on vibes.
- **Trajectory opacity** — an agent's final output often looks fine even when the execution path had failures. The order-lookup tool returned stale data; the model covered gracefully. Logs only show the polished lie.
- **Eval is undervalued until it disappears** — teams discover evals are "vital" (HN, 128 points) only after shipping broken agents for weeks. The cost of building them grows with the number of agents and input permutations.
- **LLM-as-judge is promising but uncalibrated** — using one LLM to judge another is scalable, but a naive judge introduces its own biases (prefers certain writing styles, length, self-confidence). Calibration is required before trusting it as a release gate.
- **Coverage vs. speed** — comprehensive step-level evaluation is expensive and slow. Teams need a tiered approach: fast binary gates for CI, deeper rubric scoring for deeper analysis.

## The move

Start with end-to-end binary success criteria, instrument for trajectory tracing, layer in graded evaluation, and close the loop with production failure regressions.

### 1. Define success as a binary gate first

Before writing a single eval test, define one question: did the agent accomplish the user's goal? Output a simple `yes` or `no`. This is better than nothing and cheap to implement. Every additional eval layer builds on this foundation.

From aunhumano.com: *"Add e2e evals, define a success criteria (did the agent meet the user's goal?) and make the evals output a simple yes/no value. This is much better than no evals."*

### 2. Instrument for trajectory tracing before measuring

Agents fail at specific steps — tool calls, retrieval, reasoning transitions. Before you can evaluate quality, you need to see the full execution path. Trajectory tracing records inputs, outputs, timing, tool calls, retrievals, and state changes as connected spans.

From Braintrust: *"Production agents are difficult to debug because a single run typically involves multiple model calls, tool calls, retrievals, and state changes. Agent tracing records the full execution path as connected spans — capturing inputs, outputs, timing, tool calls, retrievals, and state changes — to identify the failing step rather than rerunning the agent."*

Implement with LangSmith callbacks (any LangChain app: set `LANGCHAIN_TRACING_V2=true`), Braintrust spans, or custom OpenTelemetry instrumentation. Framework-agnostic.

### 3. Layer in rubric-based LLM-as-judge for graded quality

Once you have binary gates, add rubric scoring for trend data. A rubric defines explicit quality criteria; the judge evaluates against those criteria rather than an arbitrary score.

From Promptfoo: *"Start with `llm-rubric` and one clear pass/fail criterion. Use scoring anchors only when you need trend data, not just a release gate. Treat candidate output as untrusted input to the judge."*

Minimal rubric config:

```yaml
assert:
  - type: llm-rubric
    value: |
      Evaluate: did the agent complete the user's request correctly?
      Return pass=true if all required steps were taken and no
      incorrect information was provided.
```

### 4. Calibrate the judge before trusting it in CI

An uncalibrated LLM judge introduces systematic bias — length preference, style bias, position effects in pairwise comparison. Calibrate by running the judge against 10–20 labeled examples where you know the correct verdict.

From Promptfoo: *"Calibrate the judge on labeled pass/fail examples before trusting it in CI."*

### 5. Turn production failures into regression evals automatically

When a production trace reveals a failure, write the exact input that triggered it as a regression eval before shipping any fix. Braintrust calls this "trace-to-regression": capture the failing trace, convert to a test case, add to your eval suite.

From Braintrust: *"Turn a failing production trace into a regression eval that prevents the same failure from reaching production again."*

### 6. Use multi-agent judges for complex evaluations

For high-stakes evaluations, a single judge introduces its own biases. Multi-agent evaluation — where multiple LLM agents debate or collaborate to reach a verdict — reduces individual bias and captures multiple perspectives.

From arXiv 2508.02994: *"A single LLM judge may carry inherent biases and thus produce skewed evaluations. Multi-agent evaluation frameworks in which multiple LLM agents collaborate or debate to assess outputs address these limitations by reducing individual bias and representing multiple viewpoints."*

## Evidence

- **Blog post:** "On evaluating agents" — aunhumano.com, Sep 2025 — Advocates starting with binary end-to-end success criteria and layering step-level evaluation on top. Covers trace analysis as a complement to evals. — https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/

- **HN thread (128 pts, 19 comments):** "Principles for production AI agents" — HN discussion on the importance of eval suite design, with commenters noting LLM-as-critic approaches lack empirical validation and internal experiments found LLMs were "not good critics" without calibration. — https://news.ycombinator.com/item?id=44712315

- **HN thread (42 pts, 9 comments):** "Evaluating Agents" — Links aunhumano.com post; core debate on trajectory-level vs. endpoint-level evaluation, with commenters noting endpoint scoring misses mid-execution failures. — https://news.ycombinator.com/item?id=45121547

- **Documentation:** "LLM as a Judge Evaluation Guide" — Promptfoo official docs — Covers rubric-based scoring, judge calibration, injection guard, and tiered evaluation for production CI pipelines. — https://www.promptfoo.dev/docs/guides/llm-as-a-judge/

- **Documentation:** "Agent Evaluation" — Braintrust — Explains why standard LLM evals fail for agents (single-turn scope), defines end-to-end vs. step-level evaluation taxonomy, describes trace-to-regression workflow. — https://manifesto.preview.braintrust.dev/articles/agent-evaluation

- **Article:** "Agent tracing: how to trace and debug AI agents in production" — Braintrust, Jun 2026 — Walks through the instrumentation-to-debugging pipeline with a concrete support agent failure example (order-lookup → stale retrieval → wrong answer). — https://www.braintrust.dev/articles/agent-tracing-debug-ai-agents-production

- **Paper:** "When AIs Judge AIs: The Rise of Agent-as-a-Judge Evaluation for LLMs" — arXiv:2508.02994v1 — Surveys evolution from single-model judges to multi-agent evaluation frameworks; covers bias reduction, perspective diversity, and trajectory-level evaluation. — https://arxiv.org/html/2508.02994v1

## Gotchas

- **No eval suite is not "shipping fast" — it is "accumulating invisible debt."** Every agent shipped without evals is a system whose reliability is unknown. A regression suite takes an afternoon to build and pays dividends every week thereafter.
- **LLM-as-judge without calibration is worse than no eval** — an uncalibrated judge creates false confidence. Calibrate on labeled examples before using it as a release gate.
- **Endpoint-only evaluation misses mid-trajectory failures.** The agent may complete the task with wrong intermediate steps that happen to produce an acceptable final output. Track both outcome and execution path.
- **Evals that only run in dev are not production evals.** Schedule eval runs against production traffic samples, or run against a curated regression suite in CI on every deploy. A eval that never runs doesn't catch regressions.
