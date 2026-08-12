# S-2515 · The Agent Evaluation Stack · When You Ship an Agent and Don't Know If It's Working

You have an agent running in production. It returns 200s and produces answers. You have no idea if those answers are correct, whether it took the right path, or whether it will fail on the next edge case. This is the evaluation gap — and it bites the moment agents move beyond demos.

## Forces

- **The trajectory is invisible** — agents make dozens of internal decisions (tool calls, retries, routing) before producing a final answer. Output-only evaluation misses the entire execution path, including dangerous or wasteful ones.
- **Ground truth is scarce** — agents are non-deterministic and tasks are open-ended. Unlike unit tests, there is often no single correct answer, making automated scoring non-trivial.
- **Offline evals lie** — benchmarks like MMLU and HumanEval measure model capability in isolation, not agent behavior in your specific environment. An agent that nails GAIA can still fail your workflow.
- **LLM-as-judge scales but drifts** — using a model to evaluate another model is the dominant solution, but judges introduce their own bias and require calibration against human-labeled examples.
- **The flywheel is the goal** — production failures → annotation → regression tests is the standard data loop, but most teams never close it.

## The Move

Evaluate at **three levels** across two axes — trajectory and outcome — not just the final answer.

**Evaluate end-to-end first:**
- **Task Success Rate** — binary or graded pass/fail on whether the agent completed the goal.
- Use **real production-like test cases**, not synthetic benchmarks. Amazon's Bedrock team found that "thousands of agents built across Amazon organizations" converge on this principle: isolate the specific workflow, define what "done" looks like, score it.

**Then evaluate the trajectory, not just the output:**
- **Trajectory quality** — were the right tools selected, in the right order, with correct parameters? The [TRAJECT-Bench](https://arxiv.org/abs/2507.21504) paper (2025) introduced fine-grained trajectory evaluation specifically to close the gap where "final answers look right but the path was wrong, expensive, or unsafe."
- **Tool call accuracy** — did the agent call the correct tool? Were arguments formatted correctly? The [FareedKhan-dev/ai-agents-eval-techniques](https://github.com/FareedKhan-dev/ai-agents-eval-techniques) repo (47 stars, MIT) implements 12 techniques including trajectory eval and tool precision measurement as runnable notebooks.
- **Step efficiency** — did the agent loop, retry excessively, or take an obviously long path? NVIDIA's agent eval guide recommends measuring "trajectory efficiency" alongside accuracy.

**Then drill to the component level:**
- **Per-turn assessment** — LangChain's evaluation framework calls this the "invisible" layer: each individual reasoning-action-feedback loop matters, not just aggregate scores. This is what feeds fine-tunes and RL reward signals.
- **Groundedness and context use** — is the agent citing retrieved docs correctly, not hallucinating? LangChain's trajectory eval dimension specifically tracks "grounding and context use."

**Use the right judge for each level:**
- **Deterministic checks** for tool names, API schemas, exact facts — no judge needed, just assertion.
- **LLM-as-judge** for anything requiring judgment: answer quality, trajectory reasonableness, safety. Requires structured rubrics, multiple judge passes, and calibration against human-labeled examples to mitigate bias. LangChain (April 2026) notes that "structured rubrics, multiple judge passes, and calibration against human-labeled examples" are the minimum viable setup.

**Close the production data flywheel:**
- Route production failures → human annotation queue → regression test suite.
- Monitor for drift with continuous evaluation runs tied to deployment gates — "automatically block deployments if evals fail."

## Evidence

- **AWS Amazon Bedrock engineering blog (Feb 2026):** "Evaluating AI agents: Real-world lessons from building agentic systems at Amazon" — three-dimensional eval framework (outcome quality, trajectory quality, tool interaction quality) developed from thousands of agents. Key finding: traditional LLM eval is black-box and misses root cause; agents need process visibility, not just result checking. — [URL](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **NVIDIA Technical Blog (May 2026):** "AI Agent Evaluation" — model eval (benchmarks, static datasets) vs. agent eval (trajectories, tool calls, outcomes). Recommends GAIA for general agents, SWE-bench for coding agents. Key metrics: Task Success Rate, Tool Call Accuracy, Trajectory Efficiency. — [URL](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)
- **LangChain (April 2026):** "LLM Evaluation Framework: Trajectories vs. Outputs" — trajectory evaluation across three dimensions (grounding/context, UX quality, security/safety). Production monitoring creates a "data flywheel" where failures become regression tests. LLM-as-judge requires calibration; not a free lunch. — [URL](https://www.langchain.com/resources/llm-evaluation-framework)
- **arXiv 2507.21504 (Jul 2025):** "Evaluation and Benchmarking of LLM Agents: A Survey" — two-dimensional taxonomy: evaluation objectives (behavior, capabilities, reliability, safety) and evaluation process (interaction modes, datasets, metrics). Notes the eval gap is "complex and underdeveloped" despite rapid agent growth. — [URL](https://arxiv.org/abs/2507.21504)
- **Confident AI (Jun 2026):** "LLM Agent Evaluation Metrics 2026" — four metric clusters (tool calling, planning, task completion, reasoning) across three eval levels (end-to-end, trajectory, component). Offline evals miss production failures because the environment, data, and user behavior differ. — [URL](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **GitHub: FareedKhan-dev/ai-agents-eval-techniques (2025):** 12 implemented evaluation techniques as runnable notebooks: trajectory evaluation, tool precision, component-wise RAG, LLM-as-judge. Stars: 47. — [URL](https://github.com/FareedKhan-dev/ai-agents-eval-techniques)
- **GitHub: langchain-ai/agentevals (2025):** Readymade evaluators for agent trajectories, integrated with LangSmith. Stars: 687. — [URL](https://github.com/langchain-ai/agentevals)

## Gotchas

- **Don't stop at final-answer pass/fail.** The answer can be right while the path was wrong, wasteful, or unsafe. Evaluate the trajectory.
- **Benchmarks ≠ production evals.** MMLU and HumanEval measure model capability, not agent behavior in your specific environment. Build test sets that reflect actual production inputs.
- **LLM-as-judge needs calibration.** Uncalibrated judges drift — they favor verbose outputs, prefer their own model's style, and have positional biases. Run them against human-labeled gold examples first.
- **Tracing is prerequisite, not optional.** Without structured trace capture (spans, tool calls, intermediate steps), trajectory eval is impossible. Invest in observability before eval.
- **Per-turn eval is the hardest but most valuable.** It feeds fine-tuning and RL reward signals and catches failures invisible to trajectory-level scoring. Most teams skip it and pay for it later.
- **Eval without deployment gates is theater.** Run evals as CI/CD blockers — "automatically block deployments if evals fail" — not as periodic reports nobody reads.
