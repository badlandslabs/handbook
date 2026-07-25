# S-1641 · The Trace-to-Eval Flywheel Stack

When your agent works in the demo but silently degrades in production — and you have no way to catch it until a user reports it.

## Forces

- **The eval gap is real and persistent** — 72% of teams believe comprehensive testing drives reliability, but only 15% achieve it (Galileo/State of Eval Engineering Report, 500+ enterprise practitioners)
- **Agents fail silently in ways software doesn't** — they return HTTP 200, LLM calls succeed, tool invocations complete, yet outputs are wrong due to causal failures distributed across multi-step chains (Zylos Research, 2026-04-30)
- **Retrofitting eval after MVP costs 4-6 weeks** and introduces data collection lag that means regressions go undetected for days (Intuz/TDS, May 2026)
- **The bottleneck moved** — from model choice and protocol choice to the governed harness around agents (ContextOS, June 2026)

## The move

The core pattern: every production failure becomes a test case, every test case joins a golden dataset, every golden dataset gates deployment. The flywheel runs continuously in production, not just at launch.

- **Define success as behavioral outcomes, not output matching.** Traditional ML metrics (accuracy, precision) fail to capture agentic success. Measure task completion, tool selection fidelity, context utilization, and downstream user impact — not string equality.
- **Use a grader LLM to score agent outputs, not human review.** Pass agent outputs + evaluation criteria to a separate model that produces structured scores. This scales across thousands of runs and enables automated regression detection.
- **Capture production traces as your primary test asset.** Every agent execution is a queryable trace of nested spans. When a failure occurs, the trace is the diagnosis artifact — not a log file, not a screenshot.
- **Convert diagnosed failures into permanent test cases in one click.** Braintrust and similar platforms support one-click conversion of production failures into eval cases. This is the highest-signal test data you will ever have: authentic edge cases, real input distribution, concrete definition of "broken."
- **Run evals ahead of every deploy, gate on regression.** Pre-deployment eval suites catch behavioral regressions from prompt changes, model swaps, retrieval tweaks, or tool modifications before they reach users. Braintrust's GitHub Action posts regression reports as PR comments.
- **Track cost and latency alongside quality.** A 12-metric framework (Intuz) covers four categories: retrieval quality, generation quality, agent behavior, and operational metrics. Skipping any category leaves a blind spot.

## Evidence

- **Enterprise survey:** Galileo found a 57-point belief-execution gap on eval coverage. Only 15% of teams achieve 90-100% behavioral coverage despite 72% believing it drives reliability. The root cause: teams underestimate how fundamentally different agent evaluation is from traditional ML evaluation. — [State of Eval Engineering Report](https://galileo.ai/blog/ai-agent-metrics)
- **Engineering post:** Arthur.ai describes the flywheel pattern explicitly — production failure → execution trace → test case → golden dataset → CI gate. Notes that production failures beat synthetic prompts for test coverage because they cover the long tail of edge cases teams didn't imagine. — [AI Agent Regression Testing From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Primary research:** Zylos Research (591 documented incidents, 2023-2026) found 88% of agent failures trace to infrastructure gaps — missing guardrails, absent monitoring, inadequate trace instrumentation — not model quality. Proposes trace-driven debugging as the remediation framework. — [Trace-Driven Debugging for AI Agent Failures](https://zylos.ai/research/2026-04-30-trace-driven-debugging-ai-agent-failures)
- **Framework:** OpenAI's agent eval platform combines four primitives: traces (full execution records), graders (LLM-based scorers), datasets (curated test inputs), and eval runs (batch execution against datasets with scoring). Designed for CI integration. — [Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals)
- **OSS framework:** nano-step/eval-harness provides behavior-regression testing for LLM agents with 4-class attribution (identifies root cause of regressions), 6-field FAIL schema, cost gating, and flaky-test detection. Runs as a pre-push hook. — [eval-harness README](https://github.com/nano-step/eval-harness)
- **Production deployment:** GrowthX built Output.ai (used by Lovable, Webflow, Airbyte) on Temporal's durable execution model specifically to handle the replay and recovery problem. Daniel Lopes (CTO): "agent reliability is a distributed systems problem, not a model problem." — [Taming AI agents with Output.ai at GrowthX Labs](https://temporal.io/resources/on-demand/taming-ai-agents-with-output-ai-at-growthx-labs)
- **Industry analysis:** ContextOS (June 2026) argues the real story of 2026 is not that agents became production-ready but that "the outer layers matured faster than the middle" — the governed harness is now the differentiator. — [State of AI Agents in 2026](https://contextosai.com/blog/state-of-ai-agents-2026)
- **12-metric framework:** Intuz's post-MVP retrofit pattern (4-6 weeks) covers retrieval, generation, agent behavior, and cost/latency. Skipping operational metrics leaves compliance and business stakeholders without evidence of reliability. — [12-Metric Framework From 100+ Deployments](https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/)

## Gotchas

- **A passing eval is not a passing agent.** Eval coverage matters as much as eval results. Teams with 70% coverage and 95% pass rate still ship broken agents. The 70/40 Rule (Galileo): invest 40% of eval time in coverage, not just passing existing tests.
- **Flaky tests plague probabilistic systems.** Run each failing case 3-5 times before treating it as a real regression. nano-step/eval-harness explicitly does this — byte-identical across samples means real failure, not stochastic noise.
- **Cost gating is load-bearing.** LLM-based grading is expensive at scale. Track cost-per-eval-run and gate expensive grading behind pass/fail thresholds from faster heuristics. nano-step's approach: fail-fast on cost thresholds before running full grading.
- **Synthetic test suites go stale fast.** Hand-crafted prompts and expected outputs drift as the domain evolves. Production-derived test cases auto-update as real users exercise the system. Build the infrastructure to capture them from day one.
- **Tracing without actionability is overhead.** Raw traces are diagnosis artifacts, not fixes. The value is in converting the diagnosed failure into a permanent test case — otherwise you replay the same incident.
