# S-1803 · The Measured Agent Stack — When Your Agent Passes All Tests and Still Fails in Production

Your eval suite is green. Task success rate: 87%. You shipped the new model, watched the dashboard, and two weeks later a user reported that the agent filed a refund, reported success in its response, and nothing actually changed. The eval suite never caught it — because it was testing final-answer correctness on handcrafted prompts, not production behavior under real distribution. Your agent was measured, but not well.

You need evaluation as a closed loop: offline tests that catch regressions, production sampling that surfaces real failures, and a path that turns every failure back into a test.

## Forces

- **Your eval suite tests what you imagined, production reveals what you didn't.** Handcrafted test cases cover the scenarios you thought of. Real users produce ambiguous phrasing, malformed inputs, and unexpected tool sequences that no engineer would have invented — and those are exactly the cases that expose the agent's actual reliability gap.
- **Offline evals measure the agent, production eval measures the system.** An agent can pass every offline test and still degrade silently because a retriever drifted, a downstream API changed its schema, or user input distribution shifted. Offline tests don't see the deployment context.
- **The judge sees the response, not the trajectory.** A single-pass LLM judge grading a final answer cannot detect whether the agent called the right tool, looped unnecessarily, recovered from a failure, or produced a plausible-sounding false completion. Trajectory-aware scoring requires instrumenting the full execution trace — not just the output.
- **Academic benchmarks have been gamed to uselessness.** UC Berkeley researchers found all eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) could be exploited. One team gamed 890 tasks with a single character change. Several systems achieved near-perfect scores while solving zero real problems. Benchmark scores for agent evaluation are now unreliable as proxies for production quality.
- **Eval startups fail because teams confuse the tool for the discipline.** The HN thread on "Why eval startups fail (2025)" surfaced the core problem: teams adopt an eval platform expecting it to solve measurement, then stop investing in the curation, calibration, and workflow discipline that makes measurement work. The tool is the easy part.

## The move

Build a three-layer eval system that operates as a closed loop: offline regression tests, production trace monitoring with sampled human review, and a weekly promotion of failing production traces into the test dataset.

**1. Trace everything, not just final outputs.**
Instrument the full execution trace — every tool call (name, arguments, return value), every LLM call, every retrieval result, every intermediate step. This is the artifact that lets you move from "the task failed" to "which tool call was wrong." Langfuse, LangSmith, OpenTelemetry instrumentation, or Phoenix all provide this. Without traces, your failure analysis is guesswork.

**2. Measure four dimensions, not one.**
- **Trajectory quality:** Did the agent take a sensible path? Count steps, detect loops and unnecessary retries, verify correct ordering of required steps. Langfuse's trajectory dimension tracks this.
- **Tool use correctness:** Did it call the right tools with valid arguments? Did it recover from tool errors? Tool error rate and argument validity are measurable with deterministic checks — don't use a judge for things you can verify exactly.
- **Task completion:** Did the user get what they asked for? Beyond pass/fail: step efficiency (how many calls vs. optimal), policy adherence (did it respect domain constraints), and graceful degradation (does it fail safely and informatively when it can't complete).
- **Operational metrics:** Latency per task, cost per task, token efficiency, and error rates. These are first-class evaluation targets, not afterthoughts.

**3. Offline eval: golden dataset from production failures, not engineer imagination.**
The highest-value regression test dataset is not handcrafted — it comes from production failures. Every time an agent does something wrong in front of a real user, the execution trace becomes a test case. A fintech company processing GL codes couldn't track mismatches with state checks alone — they needed to capture the actual distribution of failure traces to build meaningful assertions. Start with 20–50 high-signal production failures. Stratify by tool, argument edge case, and error code. Run against every prompt change, model swap, retrieval tweak, or tool update.

**4. Calibrate your LLM judge, then deploy it.**
LLM-as-judge scales evaluation beyond manual review but requires calibration. Aim for 75–90% judge-to-human agreement before running against production data. Use deterministic checks wherever possible (exact tool names, argument schema validity, output format) and reserve the judge for anything requiring context or judgment. The gap between a naively configured judge and a well-calibrated one is wide enough to produce opposite conclusions about agent quality.

**5. Sample production traces, don't review all of them.**
Human review is expensive and slow. Sample production traces — prioritize low-scoring slices (judge scores below threshold), first-occurrence failure patterns, and high-stakes task types. Every reviewed trace that fails becomes a candidate for the golden dataset. LangSmith's Annotation Queues and Braintrust's production logging support this workflow: add any trace to a dataset with one click, run offline evals to catch regressions, ship changes that pass, and monitor with online scoring.

**6. Close the loop every week.**
Offline eval → CI/CD gate → production trace monitoring → Error Feed → dataset update → offline eval again. Treat the eval setup as the backbone of the CI/CD process for agents, not a one-time checkpoint. Claude's eval engineering report (March 2026) recommends running critical scenario regression tests on every change, with production traffic sampled continuously to surface new failure modes weekly.

## Evidence

- **HN Ask HN ("What broke when I tried to evaluate an AI agent in production", 2026):** A practitioner tried a benchmark-style approach against their production agent and found it failed in unexpected ways — the benchmark didn't capture the agent's actual failure modes in deployment. The broader HN thread on "Why eval startups fail (2025)" confirmed that teams adopt eval platforms but skip the curation discipline that makes them work. — [https://news.ycombinator.com/item?id=47416033](https://news.ycombinator.com/item?id=47416033); [https://news.ycombinator.com/item?id=48637868](https://news.ycombinator.com/item?id=48637868)

- **Databricks Engineering Blog ("The Key to Production AI Agents: Evaluations", September 2025):** Found that 85% of organizations are using GenAI in at least one function, but the majority of projects stall after the pilot. Effective evaluation requires task-level benchmarking grounded in production data, with continuous measurement that connects eval results back into agent improvement. — [https://www.databricks.com/blog/key-production-ai-agents-evaluations](https://www.databricks.com/blog/key-production-ai-agents-evaluations)

- **Zylos Research / arXiv Survey on Agent Evaluation (2026):** UC Berkeley examination of eight prominent agent benchmarks found all could be gamed to near-perfect scores through minimal exploits. Benchmarks for agent evaluation are unreliable as proxies for production quality and must be supplemented with real-trajectory evaluation. — [https://arxiv.org/html/2507.21504v1](https://arxiv.org/html/2507.21504v1); [https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)

## Gotchas

- **"Metric green, user red" is the most expensive failure mode.** A judge can score a final answer favorably while the agent produced a false task completion (reported success, nothing changed) or burned 3x the budget getting there. Trajectory-level metrics catch what final-answer scoring misses. This is why the InfoQ evaluation guide (2026) calls hybrid evaluation non-negotiable — automated scoring plus human judgment on sampled traces.
- **Benchmark contamination is now a first-order concern.** If your eval dataset overlaps with training data, your scores are measuring memorization, not capability. Verify your eval prompts are isolated. For agent-specific evaluation, prefer trajectory datasets built from your own production traces over any public benchmark.
- **Sampling bias kills eval value.** If you only review traces that the judge already flagged, you'll never discover failure modes your judge isn't calibrated to detect. Mix in random sampling alongside threshold-based prioritization to catch novel failure patterns.
- **Eval without a CI gate is theater.** Running evals that don't block deployment is worse than not running them — it creates the illusion of measurement while allowing regressions to ship. The golden dataset must be wired into your release process as a gate, not a dashboard.
- **You need fewer metrics, not more.** Four dimensions (trajectory, tool use, task completion, operational) with one or two metrics per dimension beats a dashboard with 20 indicators. The NVIDIA agent evaluation guide recommends a focused matrix: task success rate, trajectory visibility, tool usage correctness, and custom business KPIs — nothing else until those four are stable.
