# S-2437 · The Trajectory Eval Stack — When Your Agent Passed Every Benchmark but Still Fails in Production

The moment you ship an agent to production, a cruel reality surfaces: every benchmark you ran was measuring the wrong thing. Final-answer scoring tells you the destination, not the path — and the path is where production agents actually die.

## Forces

- **Errors compound in agent loops.** A single bad tool call in step 3 can cascade into 20 wasted steps and a wrong answer that looks right. Standard LLM evals score one input-output pair; agents run hundreds of steps before delivering anything.
- **Correct answers hide reckless behavior.** An agent can refund $47,000 it shouldn't, call the wrong database, and still reach the "right" answer through luck. Endpoint scoring certifies the answer, not the judgment that produced it.
- **Silent failures look like success.** A data enrichment agent that returned HTTP 200 on every call, reported success on every step, and had a green dashboard — but had hallucinated half its field mappings after 6 hours of runtime.
- **Offline evals drift from production.** Model version bumps, input distribution shifts, and real user behavior diverge from test sets. Teams discover problems days or weeks after the regressions ship.
- **LLM-as-judge is everywhere but unreliable.** Every team uses it; no team fully trusts it. The gap between exact-match agreement and actual validity is 33–41 percentage points.

## The Move

Measure agents on four dimensions, not one. Then run those measurements continuously, in production, not just before launch.

### The Four Dimensions

- **Trajectory** — Did the agent take a sensible path? Count steps, flag unnecessary tool calls, detect loops/retries, check that required steps are present in correct order. A rubric scores each decision node, not just the final output.
- **Tool Use** — Did it call the right tools with the right arguments? Structured tool-call extraction gives you per-call accuracy, argument validity, error recovery rate, and which tools are most error-prone.
- **Task Completion** — Did the user get what they asked for? Goal achievement, answer correctness, resolution rate. The baseline, but not the ceiling.
- **Multi-turn Quality** — Does performance hold across conversation turns? Context management degrades silently when the context window fills. Track whether the agent reuses stale data or ignores updated context.

### Scoring Structure

- **Per-turn labels** feed both evals and RL reward signals. Each step is a data point.
- **Trajectory rubrics** define "acceptable paths" — not just one right answer but a range of valid approaches. An agent that calls a search tool then a Wikipedia tool for the same query took a different path than one that called only Wikipedia; both may be valid.
- **Binary pass/fail beats numeric scores.** Arbitrary 1–10 scales introduce non-determinism. Pass/fail on specific criteria (e.g., "did not call external tool with unsanitized user input") is more reliable and more actionable.

### Continuous Evaluation Pipeline

- **Production-to-regression loop:** Capture problematic traces from production monitoring and add them to the eval dataset in one click. Close the feedback loop from live failure to regression test.
- **Track cost and latency per task**, not just per call. An agent that achieves 90% accuracy but costs $4 per task is a different product than one that achieves 85% at $0.12.
- **Alert on trajectory drift** — when average step count, tool error rate, or cost-per-task changes significantly after a model or prompt update.

## Evidence

- **MAP Study (arXiv 2512.04123, 2025):** First large-scale systematic study of 86 agents in production across 26 industries. Found 57% of organizations run agents in production, but only 37% run continuous evaluations against live data. Primary motivation: productivity gains. Top failure category: silent quality degradation under distribution shift.
- **Braintrust Framework:** Documents the two-layer eval architecture — trajectory scoring (per-step) plus endpoint scoring (final output). Notes that LLM-as-judge agreement with humans on MT-Bench, JudgeBench, and RewardBench shows "substantial gap" between exact-match and Cohen's κ, with deflation of 33–41 percentage points across providers.
- **Anthropic Engineering Blog (Jun 2025):** Internal research evals on their multi-agent orchestration system showed one of the largest single-architecture jumps in agentic AI quality metrics documented to date. Key lesson: systematic eval at every layer — orchestrator planning, subagent execution, synthesis — catches failures that final-answer scoring misses entirely.
- **Amazon Agents Finding:** After building thousands of agents internally since 2025, discovered that traditional LLM evaluation methods fundamentally fail for agentic systems. Gartner projects 40%+ of AI agent projects will fail by 2027, primarily due to measurement gaps.

## Gotchas

- **Don't stop at held-out benchmarks.** Benchmarks like GAIA, tau-bench, and SWE-Bench establish baseline expectations but don't capture your specific production failures. Use them to calibrate; build your own eval set from production traces.
- **LLM-as-judge needs meta-evaluation.** Run your judge against a golden set of human-annotated examples. Track Cohen's κ, not just exact-match accuracy. The judge's reliability (consistency across runs) is not the same as its validity (correctness).
- **Context window surprises are silent failures.** An agent that works for 95% of conversations and silently misbehaves when the context fills will look fine in your eval set if your eval set doesn't include long conversations. Inject long-context cases deliberately.
- **Alert on cost/latency, not just accuracy.** A regression that drops accuracy by 2% but doubles cost-per-task is a business failure, not just a quality regression. Track both.
- **Retroactive labeling is expensive but worth it.** Hand-annotating production traces to build golden eval sets is tedious. It's also the highest-signal data you can feed your eval pipeline. Budget for it.
