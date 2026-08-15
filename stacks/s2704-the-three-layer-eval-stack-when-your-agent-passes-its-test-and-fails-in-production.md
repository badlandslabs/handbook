# S-2704 · The Three-Layer Eval Stack — When Your Agent Passes Its Test and Fails in Production

Your eval suite is green. Your CI pipeline ships. Three weeks later, a customer reports the agent spent $4,200 calling a search API 600 times to answer a single question — and got the wrong answer. The test suite never caught it because it only graded the final output. The three-layer eval stack is the measurement discipline that would have caught it: grade the tool calls, grade the trajectory, grade the output. Most teams measure only the third and wonder why their agents still fail.

## Forces

- **Output grading hides path-dependent failures.** An agent can reach a correct answer through a broken process that will fail next time with slightly different input. Output-only grading rewards luck.
- **Tool calls are where agents spend money and make irreversible decisions.** API calls, file writes, database queries — these are the actual cost and risk vectors, and most eval suites never inspect them.
- **Trajectory quality is non-obvious to measure.** "Reasonable path" is ambiguous; there are often multiple valid routes, and the quality of the path matters for reliability, not just correctness.
- **Stochastic models make single-trial evals unreliable.** An agent that scores 94% on one run might score 61% on the next due to output variance. Multiple trials are required for stable estimates.
- **Benchmark green ≠ production green.** Standard benchmarks test held-out tasks but don't measure latency, cost, tool-call accuracy, or graceful failure under partial API responses.

## The move

Measure agents at three layers simultaneously, not just the final output:

- **Layer 1 — Tool call correctness:** Did the agent call the right tool, with the right arguments, at the right time? Check tool name, argument schema, and call ordering. This is deterministic and automatable with schema matching or regex.
- **Layer 2 — Trajectory quality:** Was the reasoning path from prompt to answer reasonable? Measure step count vs. expected, presence of loops or redundant calls, and whether the agent recovered from tool failures or ignored them. Use trace inspection or LLM-as-judge for this layer.
- **Layer 3 — Final output quality:** Is the answer correct, complete, and in the expected format? Use LLM-as-judge for nuanced quality, deterministic checks for factual accuracy, and human review for tone and contextual appropriateness.
- **Layer 4 — Operational behavior (often missed):** Track cost per task, latency per step, retry rates, and partial failure rates in the same traces used for quality scoring. Operational metrics catch the $4,200 search bug that output grading misses.
- **Run multiple trials.** Single runs are unreliable for stochastic agents. Run each task 3–5 times and aggregate scores; report variance alongside averages.
- **Integrate into CI/CD.** Evals that only run manually become neglected evals. Trigger eval runs on every commit, on a schedule, and on production anomalies. Catch regressions before they reach users.
- **Calibrate LLM-as-judge against human judgment.** Automated judges drift; sample 5–10% of traces for human rubric review to keep judge scores aligned with real quality.

## Evidence

- **LangChain State of Agent Engineering survey:** 89% of organizations have implemented observability for agents, but only 52% run offline evals on test sets and just 37% run online evals — indicating the tooling to *see* agents has outpaced the tooling to *judge* them. This gap is where production failures hide. — [LangChain — Evaluating AI Agents at the Run, Trace, and Thread Level](https://www.langchain.com/resources/agent-evals)
- **Enterprise deployment data:** Agents achieve ~60% success on single runs in enterprise deployments; this drops to ~25% across 8 runs. Standard benchmarks miss these reliability challenges because they report single-point estimates, not reliability profiles across variance. — [Galileo AI — How to Build an Agent Evaluation Framework](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Anthropic engineering guidance:** An evaluation ("eval") is a test with defined inputs and grading logic applied to output. For autonomous agents, each task should have multiple graders covering different dimensions, and trials should be run multiple times to account for output variance. The key insight: "The capabilities that make agents useful — autonomy, intelligence, and flexibility — also make them harder to evaluate." — [Anthropic — Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Pontil operational case study:** An agent that produces the correct final answer through a broken or wasteful process "is a failure that has not happened yet." They document a real production case where output-only grading missed a tool-call loop that burned $4,200 on a single task. — [Pontil — Agent Evals: How to Measure Tool Calls, Trajectories, and Production Reality](https://www.pontil.com/blog/agent-evals-how-to-measure-tool-calls-trajectories)
- **LangChain OSS eval package:** LangChain's `agentevals` package provides readymade evaluators for agent trajectories, supporting both deterministic matching (for tool-call schema validation) and LLM-as-judge (for trajectory quality). Evaluators run offline against fixed datasets to catch regressions when prompts, tools, or models change. — [GitHub — langchain-ai/agentevals](https://github.com/langchain-ai/agentevals)

## Gotchas

- **Output-only grading is a false signal.** Agents can fail in dozens of ways — wrong tool, right tool wrong args, right tool right args wrong order, right path but excessive cost — that produce correct-looking final answers. If you only check the output, you only catch the ones where the answer itself is wrong.
- **Single-trial evals lie for stochastic systems.** Run each task 3–5 times and report pass rate with variance. A "94% reliable" agent that scores 94/100 on one run and 61/100 on another is not 94% reliable.
- **LLM-as-judge needs calibration.** Automated judges can be 60–70% correlated with human judgment out of the box and drift over time as model behavior changes. Sample traces for human rubric review to catch judge drift before it masks real regressions.
- **Benchmarks ≠ reliability surface.** pass@1 on ToolBench is one coordinate on a multi-dimensional surface. Real production spans rate limits, API schema drift, input phrasing variation, and cost constraints. Benchmarks measure one slice; you need eval suites that measure the whole surface.
- **Operational metrics belong in the same trace as quality metrics.** Cost, latency, and step count are not "DevOps concerns" separate from "quality concerns." The agent that scores 95% on quality but burns $4,200 per task is not a production-ready agent.
