# S-2551 · The Feedback-Loop Stack — When Your Agent Fails Silently in Production

*Your agent shipped clean. Tests passed. Three weeks later a user reports it billed the wrong client — but nobody noticed, nobody caught it, and the same failure mode is now latent in every future deployment until someone writes a test for it. The fix is a closed loop: production failures become regression tests, regression tests become CI gates, CI gates become confidence.*

## Forces

- **Agents fail invisibly.** Unlike code crashes, agent failures often produce plausible-looking outputs. The wrong answer looks like the right answer until a human notices. By the time you learn about it, the failure is already in production and already encoded in your users' mental model of what the agent does.
- **Synthetic test sets miss what users actually do.** You can engineer imagined edge cases, but you cannot invent the actual distribution of real inputs. Production traffic is a sampling of reality your synthetic set will never match.
- **Non-determinism breaks traditional regression assumptions.** A test that passed last Tuesday may fail today for the same input. You need to track distributions, not binary pass/fail.
- **The loop breaks at the human bottleneck.** Capturing a failure, writing a test, shipping it to CI — each step requires human action and memory. In practice, most teams skip the steps after "someone noticed."

## The move

Build a **closed feedback loop** that converts every production failure into a regression test automatically, and gates deployments on that growing test suite.

**The core loop — four steps, all traceable:**

1. **Trace every execution.** Instrument every agent run with structured telemetry: input, reasoning trace, tool calls, outputs, and latency. Use a tracing platform (Langfuse, LangSmith, Arize Phoenix, Helicone) that can replay trajectories end-to-end. Without a trace, a failure is just a complaint.

2. **Detect failures automatically, not manually.** Set up monitors that score production traces against your evaluation rubrics in real time. Flag when quality drops below threshold, when a tool call fails silently, or when the agent takes an unexpected path — before a human reports it. Langfuse, LangSmith, and Braintrust all support this as a production monitoring layer.

3. **Promote failures to test cases immediately.** When a production failure is confirmed, save the trace as a labeled test case with metadata (failure type, date, user-impact). This is the highest-value data you can add to your eval suite — an authentic edge case you did not engineer and could not have imagined.

4. **Gate releases on the cumulative suite.** Run the full golden dataset — original plus every promoted failure — as a merge-blocking CI check. Regressions block deploys. Pass rates become your release criterion.

**Key implementation details from practitioners:**

- **Tolerance bands over exact thresholds.** Exact score matching is too brittle for LLM outputs. Track pass rates over 3–5 re-runs and use a band (e.g., "≥85% pass rate over 3 runs") as your gate criterion. — *Source: aiml.qa LLM Evaluation Framework Benchmark 2026*
- **Calibrate LLM judges against human reviewers.** Automated judges drift — re-run with human labels quarterly and adjust rubric prompts. — *Source: Google Cloud Agent Factory recap, October 2025*
- **Seed golden cases from production baselines, not imagination.** Run the current production agent against your evaluation set and mark every passing case as golden. Add metadata about capability coverage and failure origin. — *Source: Kinde, CI/CD for Evals guide*
- **Propagate trace IDs end-to-end.** Every component — retrieval, planning, tool execution, response — must emit structured telemetry with a common trace ID. Without this, trajectories cannot be replayed and the feedback loop has no substrate. — *Source: Google Cloud engineering checklist, July 2026*

## Evidence

- **Research (UC Berkeley / Stanford / 25+ institutions):** Survey of 86 production agent deployments found 95% fail in their first year. The most common failure mode was silent incorrect outputs that users worked around rather than reported — making production monitoring critical for discovery. — *[arXiv:2512.04123 — Measuring Agents in Production (MAP), December 2025](https://arxiv.org/html/2512.04123v1)*
- **Engineering blog (Arthur):** Documents the production failure → trace → test case → golden dataset → CI gate loop in detail. Notes that production failures contain "authentic edge cases you could not have invented" and argues this is the highest-value source for regression test datasets. — *[Arthur.ai — AI Agent Regression Testing From Production Failures, June 2026](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)*
- **Engineering blog (Galileo):** Documents eval-driven CI pipelines as the mechanism that enforces the loop gate. Describes "golden flow validation" as the backbone of the CI pipeline and drift detection replacing manual QA for continuous monitoring. — *[Galileo AI — CI Pipelines for AI Agents Best Practices, April 2025](https://galileo.ai/blog/continuous-integration-ci-ai-fundamentals)*

## Gotchas

- **Don't let agents write their own regression assertions.** Agents will optimize for the test, not the behavior — encoding the bug as "expected." Always have humans validate that assertions capture intended behavior, not implementation artifacts.
- **Flaky tests are worse than no tests.** If your CI is red most of the time, engineers stop trusting it. Use tolerance bands, re-run on failure before blocking, and separate flaky-happy paths from stable critical paths.
- **The loop only closes if someone owns it.** Without a designated owner reviewing confirmed failures and promoting them to test cases, the loop breaks at step 3. Build a lightweight process (one label, one PR, five minutes) and a reminder to use it.
- **A growing golden set has a growing cost.** Every new test case re-runs on every CI run. Prune aggressively — tests that no longer represent current behavior (deprecated features, old edge cases) should be archived, not kept.
