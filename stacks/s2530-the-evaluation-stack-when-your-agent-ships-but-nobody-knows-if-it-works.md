# S-2530 · The Evaluation Stack — When Your Agent Ships But Nobody Knows If It Works

Your agent passed its test cases. Your agent responds correctly to sample prompts. Your agent shipped on Friday. Three weeks later it is making confident wrong decisions in production at 3 AM and nobody has a metric for what went wrong. This is not a testing problem. It is an evaluation architecture problem — and it is the reason Gartner predicts over 40% of agentic AI projects will be cancelled by end of 2027. Not because models fail, but because teams cannot measure whether their agents work.

## Forces

- **Single-run success hides multi-run collapse.** An agent that succeeds 60% of the time on a single attempt drops to ~25% when measured across eight consecutive runs. Traditional testing catches the 60%, not the 25%. For anything customer-facing, reliability is the number that matters — and most teams don't compute it.
- **Trajectory is invisible unless you instrument it.** Agents produce a trace — a sequence of reasoning steps, tool calls, environment observations, and state mutations. A correct final answer reached through a broken path is a failure waiting to recur. Most teams grade only the answer and ship blind to the reasoning chain.
- **Cost and latency are non-obvious failure modes.** One survey of 27 AI companies found 50x cost variation ($0.10–$5.00/task) across teams achieving similar accuracy. Latency profiles for multi-step agents are dominated by tool call round-trips, not model inference — a metric most dashboards don't surface.
- **Offline gates ship; online watches.** A versioned test suite in CI catches regressions before deploy. But production distributions drift, tools break, and edge cases surface that no pre-launch dataset anticipated. Teams need both — and most have only one.

## The Move

Evaluate agents across three layers, not one. Each layer answers a different question:

**1. Outcome — did the task get done?**
- Task success rate: did the agent reach a correct terminal state?
- Task completion rate: did it finish without giving up?
- Use deterministic assertions for tasks with known correct answers. Use an LLM-as-judge for open-ended quality judgments. Target ≥0.80 Spearman correlation between the judge and human annotations before trusting it.

**2. Trajectory — did it take a sane path?**
- Tool selection accuracy: did it call the right tool, with the right parameters?
- Step efficiency: how many steps vs. the optimal minimum for this task class?
- Recovery quality: if it made a wrong call, did it self-correct before compounding the error?
- Rate the trajectory independently from the outcome. A correct answer via a broken path is a reliability debt.

**3. System — what did it cost to get there?**
- Tokens per task (input, output, total)
- Latency per task and per step
- Cost per task
- Error rate by type (API failure, tool timeout, reasoning failure, Hallucination)

**Build the evaluation harness in layers:**

- **Golden dataset from production failures.** The highest-value test cases are not handcrafted — they come from real failures. Every production incident is a trace, the trace is a test case, the test case joins the golden dataset, and the golden dataset becomes a release gate in CI. Each step is one turn of a flywheel.
- **pass@k, not pass@1.** Compute both. pass@1 is single-run success. pass@k is the probability of at least one success in k attempts. At 70% per-run success: pass@3 ≈ 97%, but all-3-times (pass^3) ≈ 34%. For customer-facing agents, report the reliability number — pass@1, pass@3, pass@5 — alongside the pass/fail.
- **CI gates + production sampling.** Run the golden dataset against every commit. Block deployments on score regressions. Simultaneously, sample a percentage of production traces and run automated scoring on them — catch distribution drift that pre-launch evals missed.
- **Domain benchmarks as sanity checks.** Use SWE-bench Verified for coding agents, WebArena for web-navigation agents, GAIA for general reasoning agents. These are not your golden dataset — they are the sanity check that your agent is competitive with the field and hasn't regressed on canonical tasks.
- **LLM-as-judge with rubric.** Use a 3-tier rubric: 7 top-level dimensions (task completion, tool use, reasoning quality, safety, efficiency, consistency, recovery) → 25 sub-dimensions → specific assertions at the leaf level. Calibrate the judge against human annotations before wide deployment.

## Evidence

- **Amazon Bedrock AgentCore evaluations framework:** Amazon built and shipped thousands of agents since 2025 and documented the lesson that single-model benchmarks fail for agentic systems — they treat agents as black boxes evaluating only final outcomes, ignoring the reasoning chain, tool selection, and multi-step decision-making that determine real-world reliability. Their framework evaluates: tool selection accuracy, multi-step reasoning coherence, memory retrieval efficiency, and task completion success rates. — [AWS ML Blog, Feb 2026](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)

- **AlphaEval (arXiv:2604.12162):** Production-grounded benchmark of 94 tasks sourced from 7 companies deploying AI agents in their core business, spanning 6 O*NET occupational domains. Surveyed 27 AI product companies: 63% report low confidence that model updates actually improve their products, 25.9% have no explicit evaluation criteria, and 70.4% rely on developers testing as a side task. The best agent configuration across their benchmark achieves only 64.41/100, revealing a substantial research-to-production gap. Key finding: scaffold choice matters as much as model choice. — [arXiv:2604.12162](https://arxiv.org/pdf/2604.12162)

- **Gartner prediction:** Over 40% of agentic AI projects will be canceled by end of 2027 — not because models aren't capable, but because teams cannot reliably measure whether their agents work in production. — [Gartner, June 2025](https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027)

- **DeepEval 2025:** Production-ready agent evaluation capabilities shipped with task completion metrics, tool correctness scoring, and MCP interaction evaluation. Agent evaluation "took center stage" across the open-source eval ecosystem in 2025, with DeepEval adding 20+ built-in metrics, OpenTelemetry support, and integrations with LangChain, LlamaIndex, CrewAI, and PydanticAI. — [DeepEval Changelog 2025](https://deepeval.com/changelog/changelog-2025)

- **Langfuse golden dataset guide:** Practical pattern for building regression test sets from production traces — capture a production failure as a trace, convert it to a test case, add it to the versioned golden dataset, gate CI/CD on regression. Combined with LLM-as-judge for automated scoring and CI/CD regression testing on every PR. — [Langfuse Golden Dataset Guide](https://langfuse.com/resources/engineering/golden-dataset-evaluation)

- **Prefactor Tech practitioner playbook:** "A model can score well on MMMU or HumanEval yet fail a multi-step workflow because it loses track of state after six tool calls or calls the wrong API." Documents production failure modes: confident wrong actions (agent reaches wrong conclusion confidently), ghost actions (agent takes steps that don't affect the outcome), and silent degradation (drift over time that doesn't trigger alerts). — [Prefactor Tech, July 2026](https://prefactor.tech/blog/agent-evaluation-in-production-what-to-measure-and-how-to-prove-it)

## Gotchas

- **Measuring only the final answer misses the most common failure mode.** Agents that call the wrong tool, then call another tool to recover, then produce a plausible-sounding answer are scored as "correct" by output-only evaluation. Instrument the trajectory.
- **pass@1 is not your reliability number.** For any customer-facing workflow, run and report pass@3 and pass@5. A 70% pass@1 agent is not a production-ready agent — it is an agent that needs three tries per request on average.
- **Golden datasets go stale.** The production distribution changes, your agent's capabilities change, your tools change. Schedule periodic golden dataset review — trim outdated cases, add new ones from recent production failures. A stale golden dataset gives false confidence.
- **LLM-as-judge needs calibration.** A judge that hasn't been checked against human annotations will have unknown bias. Before deploying automated trajectory scoring, measure Spearman correlation against human judgments on a sample of 50–100 cases. Target ≥0.80.
- **Cost is almost always undermeasured.** Most agent observability stacks track latency and accuracy but not cost per task. Multi-step agents with repeated tool calls can easily run 10–50x more tokens than a simple LLM call for the same nominal task. Track it.
