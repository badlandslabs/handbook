# S-1362 · The Regression Pipeline Stack

When you reach for it: Your agent passes its eval suite — but two weeks later you discover it was returning corrupted data in production. Your benchmark scored the final answer. Nobody scored the trajectory. You need a pipeline that converts every production failure into a permanent regression test, and runs it on every change.

## Forces

- **Final-answer scoring misses the most expensive failure mode.** An agent can produce a correct-looking reply by fabricating a customer ID, calling `get_balance` on it, getting a permission error, and apologizing fluently. The trajectory is broken. The output looks fine. — *[BestAIWeb](https://www.bestaiweb.ai/how-to-build-an-agent-evaluation-pipeline-with-langsmith-braintrust-and-deepeval-in-2026)*
- **Offline eval and online monitoring are different jobs, not the same job at different times.** Offline eval (against a fixed golden dataset) gates releases — it answers "is this version better?" Online monitoring (against sampled production traffic) detects regressions — it answers "is quality holding?" Both are required; neither replaces the other. — *[Benchmarking Agents Review, Vol. III, Apr 2026](https://benchmarkingagents.com/for-production-monitoring)*
- **LLM-as-judge is load-bearing in production, not just an eval harness.** Over half of surveyed production agent teams now run judge LLMs at runtime for quality gating and tool-call verification — not just during batch evaluation. — *[Zylos AI Research, Apr 2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)*
- **Your eval dataset rots if it only grows from handcrafted tests.** Production input distribution always exceeds what you can invent. The highest-value regression tests come from real failures — authentic edge cases no one would have thought to synthesize. — *[Arthur, Jun 2026](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)*

## The move

Build a three-layer evaluation pipeline. Each layer runs continuously and feeds the next.

**Layer 1 — CI Regression Gate (offline, pre-deploy)**
- Run against a versioned golden dataset on every prompt change, model swap, or tool modification
- Score three things: trajectory correctness (did it use the right tools in the right order?), output correctness (is the final answer right?), and cost efficiency (did it use N tools when 3 would have sufficed?)
- Deterministic checks for exact tool names and parameters; LLM-as-judge for reasoning quality and task completion
- Require passing threshold as a hard gate — do not deploy if the golden set regresses

**Layer 2 — Production Monitoring (online, continuous)**
- Sample 1–5% of production traces and run them through an eval scorer asynchronously
- Track cost-per-task and latency-per-step as first-class metrics, not afterthoughts — two agents with identical accuracy can differ 50x in cost depending on tool-call redundancy and retry loops — *[JobsByCulture AI, May 2026](https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026)*
- Correlate traces to business outcomes, not just latency: "what percentage of support tickets were actually resolved vs. just answered?" — *[AgentWorks, Jun 2026](https://agent-works.ai/insights/agent-observability-logs-traces-evals)*
- Flag trajectories that call tools out of expected order, use hallucinated arguments, or hit error-recovery loops

**Layer 3 — The Regression Flywheel (data loop)**
- Every production failure becomes a trace, the trace becomes a test case, the test case joins the golden dataset, the golden dataset gates the next deploy — *[Arthur](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)*
- Human review on flagged production traces → annotation queue → curate into golden set
- LLM-as-judge scales the annotation queue but requires calibration: rubric quality matters more than judge model size; structured rubrics with scoring examples achieve 0.85–0.92 Spearman correlation with expert human judgment, versus 0.60–0.75 without them — *[Tendril/TechJacks citing arXiv "Judging LLM-as-a-Judge," Zheng et al., 2024](https://techjacksolutions.com/ai/agentic-ai/build/agent-evaluation-benchmarks/)*

## Evidence

- **HN Ask HN (Dec 2024):** "Ask HN: What AI Agents are in production?" — practitioners consistently cite observability and evaluation as the hardest unsolved part of agent deployment, ahead of orchestration or tool integration. — [HN #42485738](https://news.ycombinator.com/item?id=42485738)
- **BestAIWeb (May 2026):** Documents a real support agent that silently changed its trajectory over a week — from calling `lookup_customer` first to calling `get_balance` first with a fabricated ID. The final message looked fine. Nobody caught the trajectory regression until a human reviewed traces. — [bestaiweb.ai](https://www.bestaiweb.ai/how-to-build-an-agent-evaluation-pipeline-with-langsmith-braintrust-and-deepeval-in-2026)
- **LangChain (Apr 2026):** Production monitoring creates a data flywheel: real-world failures → annotation queue → regression tests. Without this loop, eval datasets capture only the failures you anticipated, leaving the majority of production failure modes undetected. — [langchain.com](https://www.langchain.com/resources/llm-evaluation-framework)
- **Arthur (Jun 2026):** Non-determinism means an agent that passes today can fail tomorrow — making the regression flywheel not just useful but structurally necessary for any production agent. — [arthur.ai](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

## Gotchas

- **LLM-as-judge without rubrics is unreliable.** A judge evaluating "did the agent do a good job?" without a structured rubric achieves 0.60–0.75 correlation with human judgment. The rubric is the product, not the judge model.
- **Sampling production traffic misses tail failures.** If a failure mode occurs 0.1% of the time, 5% sampling gives you ~1 in 5,000 odds of capturing it. Set sampling thresholds by failure severity, not uniform percentage.
- **Cost tracking at the run level, not the step level, hides regressions.** An agent that doubles its tool-call count on a specific input type won't show up in average cost-per-task unless you track at step granularity.
- **Eval data without versioning is not a gate.** If your team can deploy without running the golden dataset, it won't be run. The pipeline must be automated, not opt-in.
