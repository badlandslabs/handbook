# S-1811 · The Eval Gap Stack — When Teams Believe in Evaluation but Only 15% Actually Do It

You ship your agent. You have tests. You ran them. You feel confident. Then in production: it silently returns corrupted data to 200 users overnight, your APM dashboard glows green, and you find out three days later. The agent "worked" in testing because you tested its responses — not its trajectories. You were measuring the wrong thing, and you were not alone.

The dominant failure in production agent deployment is not that agents fail in surprising ways. It is that teams measure what is easy to measure (output quality, single-turn accuracy) instead of what determines production reliability (trajectory correctness, tool call precision, recovery behavior). A 57-percentage-point gap separates teams who believe comprehensive testing drives reliability from those who actually achieve it.

## Forces

- **Static benchmarks reward the wrong behavior.** Traditional benchmarks evaluate end-state output, not the reasoning path or tool-use trajectory that produced it. Agents optimized for benchmark performance become brittle outside the narrow conditions tested — and you cannot see this coming because your benchmark says green.
- **The belief gap is measurable and large.** 72% of AI teams believe comprehensive testing drives reliability; only 15% achieve elite evaluation coverage (90–100% of agent behaviors tested). The majority of teams are running evaluations that give false confidence.
- **Agent failures are trajectory-shaped, not point-shaped.** A single tool call returning wrong data, a slow API holding up the reasoning loop, a partial failure in a 12-step workflow — these are invisible to output-only evaluation. You need to instrument the path, not just the destination.
- **Eval drift compounds silently.** An agent that changes behavior after a model update, a system prompt tweak, or a dependency version bump will show green on output metrics while silently degrading on the specific task distribution your users actually exercise.

## The move

Measure agent quality across three layers, not one:

- **Step-level metrics** — Did the agent call the right tool, with the right parameters, at the right time? Track tool call precision, parameter validation pass rate, and hallucinated tool invocations.
- **Trajectory-level metrics** — Did the agent follow a correct reasoning path? Measure trajectory accuracy (did it reach the goal via a valid path?), intermediate goal achievement rate, and step efficiency (did it take 3 steps or 23?).
- **Session-level metrics** — Did the agent accomplish the overall goal? Track task success rate, cost per successful task, and escalation rate (how often did it punt to human?).

Instrument trajectories, not just outputs. Log every tool call, every LLM turn, every decision branch. Build eval pipelines that replay production traffic against your agent and measure trajectory divergence, not just final output quality.

Use grounded evaluation: compare agent output against a trusted external source (database, API, ground-truth dataset) rather than relying on LLM-as-judge for all assessments. LLM judges are useful for style and coherence; they are unreliable for factual correctness against your specific domain.

Establish change detection: run regression suites on every model update, system prompt change, or dependency version bump. Track trajectory stability scores across versions — a green output with a divergent trajectory is a regression even if the task succeeded.

## Evidence

- **Research Report:** 72% of AI teams believe comprehensive testing drives reliability, yet only 15% achieve elite evaluation coverage (90–100% of agent behaviors tested) — a 57-point belief-execution gap. Source: Galileo Labs, State of Eval Engineering Report (2025–2026), https://galileo.ai/blog/ai-agent-metrics
- **Academic Framework:** AgentCompass (arXiv:2509.14647) — the first evaluation framework designed specifically for post-deployment monitoring and debugging of agentic workflows. Models expert debugger reasoning through error identification, categorization, root-cause analysis, and fix recommendation stages. Authors: Kartik et al., September 2025, https://arxiv.org/abs/2509.14647
- **Enterprise Post:** Databricks agent evaluation framework: task-level benchmarking, grounded evaluation (comparing outputs against trusted external sources), and change tracking. 85% of organizations using GenAI, majority stall after pilot phase due to inability to measure production reliability. September 2025, https://www.databricks.com/blog/key-production-ai-agents-evaluations
- **HN Discussion:** Multi-agent orchestration in production thread: teams building real agent pipelines report evaluating at trajectory level using custom infrastructure (pipeline IDs in MongoDB, step logging, replay). "There's absolute 0 framework out there that's good enough for serious work" — HN user segmondy. January 2025, https://news.ycombinator.com/item?id=47660705

## Gotchas

- **Output-only evaluation misses silent failures.** If your agent returns correct-looking data from a wrong path, output metrics pass. You only catch this with trajectory logging and replay.
- **LLM-as-judge has a ceiling.** Useful for subjective dimensions (tone, coherence, conversational quality). Dangerous for factual correctness, domain-specific logic, and safety behavior — judges trained on general corpora do not know your business rules.
- **Benchmarks leak and plateau.** Fixed evaluation datasets can be memorized. Once contaminated, they cannot detect regressions. Rotate benchmarks and prefer synthetic eval data generated from your actual production traffic.
- **Eval coverage is not the same as eval quality.** Running 1,000 test cases across 10% of your agent's behaviors is worse than running 50 well-designed cases covering 90% of behaviors. Map your coverage before you count your cases.
