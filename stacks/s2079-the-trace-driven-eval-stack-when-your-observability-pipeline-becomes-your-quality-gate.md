# S-2079 · The Trace-Driven Eval Stack — When Your Observability Pipeline Becomes Your Quality Gate

You built your agent. You have monitoring dashboards. But when a new model version ships and quality regresses, your dashboards tell you the agent is still running — not that it's silently failing on 15% of tasks. The gap between "agent is running" and "agent is working" is where production agent projects stall. The solution teams converge on: making the observability pipeline do double duty as the eval infrastructure.

## Forces

- **Observability and evaluation are the same data problem.** Both start from the same thing — a structured trace of what the agent did. Yet most teams build them as separate systems, paying the storage, schema, and pipeline cost twice.
- **Static eval suites miss runtime failure modes.** An offline test suite run weekly catches regressions. A production quality gate catches regressions in the same deployment that caused them. The delta in detection speed translates directly to exposure reduction.
- **50x cost variance between similar-accuracy agents** (Jobsbyculture, 2026) means the eval harness must track cost-per-task as a first-class metric, not a post-hoc analysis.
- **37% lab-to-production performance gap** (Jobsbyculture, 2026) — even well-validated agents degrade significantly under production conditions. Continuous trace sampling is the only mechanism that catches this before users do.
- **OpenTelemetry agent semantic conventions are now real.** The OTel community published a standard schema for AI agent traces (Iterathon, 2026), making vendor-neutral trace collection viable for the first time.

## The Move

Treat production traces as the eval harness. Build the pipeline so traces collected in production can be re-played, re-scored, and compared across model versions without instrumentation changes.

### Capture traces as first-class data

- **Emit OpenTelemetry spans for every LLM call, tool invocation, and decision point.** Use the OTel AI agent semantic conventions (now stable, per Iterathon's 2025 guide) so traces are vendor-neutral and portable.
- **Store traces long-term in an analytics-ready store.** Databricks' Unity Catalog integration (May 2026) writes OTel traces directly to managed tables, enabling SQL-based eval queries over historical traces. S3 + Athena or BigQuery works equally well — the key is structured schema, not a proprietary observability product.
- **Include enough metadata per span:** task ID, model version, prompt version, session ID, tool chain, latency, token count, cost, and outcome. This is the join key for every eval query you'll ever write.

### Build five primary metrics into the eval harness

| Metric | Definition | Production signal |
|--------|-----------|-------------------|
| **Task Completion Rate** | % tasks fully completed without human intervention | Core ROI metric |
| **First-Pass Accuracy** | % correct on first attempt | Efficiency proxy |
| **Cost per Task** | Tokens + infrastructure cost | Budget guardrail |
| **Tool-Call Precision** | Correct tool selected, correct parameters | Chain-of-thought quality |
| **Recovery Rate** | Tasks successfully recovered after error | Resilience |

These five cover the dimensions InfoQ's production lessons identified as load-bearing for enterprise agents: correctness, efficiency, cost, process quality, and resilience (InfoQ, March 2026).

### Use LLM-as-judge as a calibrated instrument

- **Run judges offline for eval runs, online for runtime quality gating.** Offline (on historical traces) gives you regression detection. Online (at inference time) gives you quality gates. Both need the same judge infrastructure.
- **Calibrate before deploying.** Zylos Research (2026) documents that all judge LLMs exhibit positional bias (prefer earlier options), verbosity bias (prefer longer responses), and self-preference (prefer outputs similar to their own). Establish ground truth on 50+ examples before the judge affects production decisions.
- **Run multiple judges for high-stakes decisions.** Majority voting across 2-3 judge models (different families, e.g., Claude + GPT-4o) reduces single-judge bias. This pattern appears in both Zylos Research and LangSmith's trajectory evaluator.
- **Match judge model tier to decision stakes.** High-stakes verifications (financial transactions, medical data) use a frontier judge. Routine quality gates can use a smaller, distilled judge for cost efficiency (Zylos Research documents the large-judge / small-judge tradeoff).

### Close the regression loop with trace diffing

- **Store task inputs + expected outcomes as version-controlled JSON alongside the codebase.** Run the eval harness on every model or prompt change before deploy.
- **Trace diffing catches silent regressions** where output quality scores improve but execution paths silently degrade. An agent that takes 3x more tool calls to reach the same answer has regressed even if the final output matches — this is invisible to outcome-only scoring.
- **Aggregate production metrics by model version.** When cost-per-task increases without a corresponding quality improvement, the agent is over-reasoning or looping — a signal that precedes many production incidents.

## Evidence

- **Company Engineering Post:** Databricks writes OTel traces directly to Unity Catalog tables via fully managed serverless ingestion. "Production traces become immediately usable for analysis and evaluation, enabling faster iteration loops." Traces feed both monitoring dashboards and the eval harness with no schema migration. — [Databricks Engineering Blog, May 2026](https://www.databricks.com/blog/observability-any-agent-anywhere-production-ready-tracing-opentelemetry-unity-catalog)
- **HN Discussion / Practitioner Survey:** Anonymous AI practitioner running agent pipelines for ~1 year summarized production orchestration patterns including eval-aware design. Core insight: teams building serious agents are converging on LangGraph + custom eval layers rather than full-featured frameworks. — [Hacker News, "Ask HN: How are you orchestrating multi-agent AI workflows in production?" (HN id: 47660705)](https://news.ycombinator.com/item?id=47660705)
- **Research / Guide:** Zylos Research documented six LLM-as-judge patterns in production use (offline eval, online runtime verifier, self-consistency loops, Reflexion, constitutional AI/RLAIF, inference-time reward models). Found that >57% of production agent teams now use judge LLMs. Identified the calibration requirements, bias taxonomy (positional, verbosity, self-preference), and the large-judge vs. small-judge tradeoff for different stakes. — [Zylos Research, May 2026](https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns/)
- **Industry Guide:** Jobsbyculture's 2026 production eval guide reports: 37% lab-to-production performance gap, 50x cost variance between agents with similar accuracy, 20–40% of regressions missed by output-only scoring. Documents the five-metric framework (task completion, first-pass accuracy, cost per task, tool-call precision, recovery rate). — [Jobsbyculture, AI Agent Evaluation Guide 2026](https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026)
- **Technical Guide:** Iterathon's 2025 observability guide documents OTel semantic conventions for AI agents as now stable, enabling vendor-neutral structured trace collection. — [Iterathon, AI Agent Observability 2025](https://iterathon.tech/blog/ai-agent-observability-production-2025)
- **Open-Source Framework:** FuturOneAI's ai-agent-evaluation-framework (CC BY 4.0, created May 2026) explicitly differentiates model benchmarks (MMLU, HumanEval) from agent evaluation — the former measure knowledge retrieval, the latter measure workflow completion. — [GitHub: FuturOneAI/ai-agent-evaluation-framework](https://github.com/FuturOneAI/ai-agent-evaluation-framework)

## Gotchas

- **Judge calibration is not optional.** Every major source (Zylos, LangSmith, InfoQ) warns that deploying an uncalibrated judge in production quality gates is a common mistake. The biases are systematic, not random — they will consistently mis-score certain response types.
- **Output-only scoring misses 20–40% of regressions.** If your eval suite only checks final outputs, you need trajectory evaluation for the same test cases. The execution path is where agents silently degrade.
- **Single-run pass rates are statistically meaningless for non-deterministic agents.** Run each task 5–10 times with temperature > 0. Report pass-at-N, not pass-at-1. A task with 70% pass-at-1 but 95% pass-at-5 is a very different agent than one with 95% pass-at-1.
- **Benchmarks and production are different environments.** SWE-bench and AgentBench have documented benchmark saturation and overfitting issues (Berkeley RDI). A benchmark pass rate of 85%+ does not translate to 85% production task completion. Treat benchmarks as necessary but not sufficient.
- **Trace storage costs scale with agent volume.** At high task volumes, storing full traces with all LLM call payloads becomes expensive. Budget for trace sampling (e.g., capture 10% of traces at full fidelity, 100% of failed traces) and budget for the analytics query layer on top.
