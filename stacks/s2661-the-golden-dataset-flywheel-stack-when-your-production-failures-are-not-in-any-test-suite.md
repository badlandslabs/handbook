# S-2661 · The Golden Dataset Flywheel Stack — When Your Production Failures Are Not in Any Test Suite

Your agent works in staging. It works in your eval harness. It passes every regression. Then it hits production and fails on inputs nobody anticipated — a weirdly-formatted CSV from a legacy system, a tool that started returning `null` instead of `[]`, a user who typed their order number with a trailing space. Your test suite never had these cases. It couldn't have. The highest-value regression dataset for an AI agent is not handcrafted — it comes from production failures, if you capture them.

## Forces

- **Production outpaces imagination.** Teams spend weeks hand-crafting edge-case test sets that cover maybe 5% of what production will throw at an agent. Real failure distributions are heavy-tailed and path-dependent — you can't predict them, only collect them.
- **The loop doesn't form on its own.** Capturing failures, converting traces to test cases, annotating expected behavior, and wiring them into CI requires deliberate infrastructure. Without it, the same failure recurs three months later.
- **Golden datasets rot.** A static golden dataset from month one of your project becomes stale as the agent, tools, and user behavior evolve. The dataset must be a living artifact, continuously fed from production.
- **Adding test cases blindly creates noise.** Not every production failure is a systemic issue worth encoding as a regression test. You need a filter — otherwise your CI gate grows to thousands of tests and loses signal.

## The move

Build the **production-to-CI flywheel**: observe real failures, convert them to structured test cases, add them to a curated golden dataset, and wire the dataset as a release gate.

**The loop:**

1. **Capture at the trace level.** Every production interaction is stored as a full trace: input, tool calls, intermediate states, tool outputs, and final response. Use an observability platform (LangSmith, Arize Phoenix, Langfuse) to instrument the agent. This is prerequisite — you cannot build the flywheel from logs alone; you need structured span data.

2. **Detect failures automatically.** Rule-based detectors catch the obvious cases: tool returned an error status, agent exceeded step limit, output missing required fields. LLM-based detectors catch the subtler ones: confident wrong answer, tool call was logically wrong even if it succeeded, plan pivoted without acknowledgment. Layer both. Neither is sufficient alone.

3. **Triage before adding to the dataset.** Not every failure becomes a test case. Arthur's framework uses a threshold: only failures that meet all three criteria — (a) user-visible impact or downstream system impact, (b) reproducible given the input, (c) represents a systemic pattern rather than a one-off — qualify. This prevents the golden dataset from becoming a noise sink.

4. **Convert the trace to a structured test case.** A test case is: the original input, the expected output (derived from human annotation or downstream ground truth), and metadata (failure category, severity, tool chain involved). The expected output is the critical piece — it is what makes this a regression test and not just a trace log.

5. **Seed the golden dataset incrementally.** Start with 20–50 high-severity cases. Each production cycle adds the verified failures. A strong golden dataset grows to 200–500 cases over six months of production. Braintrust's data shows teams that continuously seed from production reach stable eval signal after roughly 3 months of active collection.

6. **Wire it as a CI gate.** The golden dataset runs on every commit. Gate on pass rate (e.g., 95% of cases must pass) and regression delta (e.g., rate drop >5 percentage points triggers a hold). Galileo recommends a dual gate: functional pass rate AND a regression check against the previous model's run on the same dataset. This catches quality degradation even when absolute pass rate looks acceptable.

7. **Close the loop with model version tracking.** Tag each test case with the model version it was written for. When you upgrade the model, re-run the full golden dataset and flag cases that now fail under the new model — those are regressions, not new failures, and they need investigation before shipping.

## Evidence

- **Company engineering post:** Arize AI's field analysis of production failures found that the highest-value test cases are those derived from production traces — specifically failures where the agent took a wrong tool path. They recommend a "failure → trace → test case → golden dataset → CI gate" pipeline as the core of agent reliability engineering. — [Arize AI, "Why AI Agents Break: A Field Analysis of Production Failures"](https://arize.com/blog/common-ai-agent-failures/)

- **Company engineering post:** Arthur describes the regression testing flywheel explicitly: "The highest-value regression test dataset for an AI agent is not handcrafted. It comes from production failures. Every time an agent does something wrong in front of a real user, it hands you a test case you could not have invented." Their framework requires three conditions before adding a failure to the golden dataset: user-visible impact, reproducible input, and systemic pattern. — [Arthur, "How to Build Regression Test Datasets for AI Agents From Production Failures"](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

- **Company engineering post:** Galileo describes CI-for-AI pipelines that use golden flow validation as the backbone. They note that teams who build eval infrastructure first reach stable production operation in significantly less time than those who build it reactively after their first major failure incident. — [Galileo, "CI Pipelines for AI Agents: Best Practices"](https://galileo.ai/blog/continuous-integration-ci-ai-fundamentals)

## Gotchas

- **The annotation bottleneck.** Converting a production trace into a structured test case requires knowing the *expected* output. For many agent tasks — "did the agent handle this customer query appropriately?" — there is no ground truth. Use LLM-assisted annotation or a human-in-the-loop review queue. Without this step, the flywheel clogs at step 4.
- **Non-determinism breaks reproducibility.** A test case that fails 30% of the time on the same input is not a good regression test. Run each case N times (N≥5) and only add cases with stable outcomes. Flag the others as flaky until the underlying non-determinism is addressed.
- **Stale golden datasets give false confidence.** If you added cases for v1 of your agent and never re-evaluate them after tool or prompt changes, the dataset tests v1 behavior, not current behavior. Tag each case with version metadata and re-validate periodically.
- **Too many test cases kill CI velocity.** A 2,000-case dataset that takes 40 minutes to run will be ignored. Target 200–500 cases with clear categorization (critical, regression, edge) and run subsets in different pipeline stages. Critical cases run on every commit; edge cases run on daily scheduled runs.
