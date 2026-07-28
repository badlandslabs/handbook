# S-1790 · The Trajectory Evaluation Stack — When Your Agent Looks Right But Gets There for the Wrong Reasons

Your agent's final output is correct. Your dashboard is green. You shipped it. Three weeks later you discover it has been calling the wrong tool on step 7 of a 12-step reasoning chain — it just happened to stumble into a correct answer anyway. Output evaluation can't catch this. You need to evaluate the path, not just the destination.

## Forces

- **Output-only evaluation misses the mechanism.** An agent can reach a correct answer through a broken reasoning chain, a lucky hallucination, or a tool call it happened to compensate for. The final response looks identical whether the agent reasoned well or guessed well.
- **Agents accumulate decisions silently.** A 50-step agent makes dozens of internal choices — tool selections, parameter constructions, retrieval calls, retry decisions — that never appear in the user-facing output. These are exactly the points where failures originate, and output evals are blind to them.
- **Stochasticity makes pass/fail unreliable.** An agent that passes 9 out of 10 runs on a critical scenario still has a 10% failure rate on a high-stakes task. Single-run output scoring flatters agents that are statistically lucky.
- **Evals must themselves be evaluated.** The judge (human or LLM) scoring the agent is itself a system that can be wrong. Without calibrating the evaluator against labeled examples, you're measuring noise.

## The Move

Evaluate the trajectory, not just the output. Score the full reasoning chain — plans, tool calls, intermediate reasoning steps, and how the agent decided it was done.

**Core components:**

- **Three-tier evaluation structure:** Outcome metrics (did it solve the task?), trajectory metrics (did it reason correctly along the way?), and component metrics (did it call the right tool with the right arguments?). All three layers together give you coverage that output-only scoring cannot.
- **Deterministic checks for structural correctness:** Tool ordering, argument construction, loop detection, and invariant violations can be checked programmatically — these are fast, reproducible, and don't require an LLM judge. Use LLM judges only where the check depends on interpretation.
- **Schema-Guided Reasoning (SGR) for LLM judges:** Give the judge a structured rubric with explicit dimensions rather than open-ended instructions. Calibrate the judge against human-labeled examples before trusting it. Target 0.80+ Spearman correlation with human labels as a minimum bar.
- **Production-to-dataset flywheel:** Real production failures flow into annotation queues, then become labeled test cases, then become regression tests. This closes the gap between your eval suite and what users actually do to your agent.
- **CI gates with re-runs:** Re-run critical scenarios on stochastic agents — a single pass/fail on a stochastic system is misleading. Run multiple seeds and track pass rates, not just pass/fail.
- **Multi-turn session-level scoring:** Score the full session, not individual turns. A conversation can score well on coherence while the user abandons on turn 3. Measure completion, not just fluency.

## Evidence

- **LangChain evaluation guide (April 2026):** "Assessing whether an AI agent achieved its goal requires scoring the entire trajectory: the tools selected, the intermediate reasoning, and how the conversation unfolded." Distinguishes three evaluation dimensions: grounding and context use, user experience quality, and security and safety. Documents the production-to-dataset loop. — [https://www.langchain.com/resources/llm-evaluation-framework](https://www.langchain.com/resources/llm-evaluation-framework)
- **Microsoft Azure AI Foundry (July 2025):** "Agents break in ways single-turn metrics can't see. A task silently stalls mid-session. A factual claim slips through ungrounded. A conversation scores 4.2 on coherence while the user abandons it on turn three." Documents a five-step eval path: multi-turn evaluation, task-specific rubric definition, simulation-based dataset generation, trace sampling, and live benchmarking — all on the same trace surface. — [https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/before-you-ship-your-agent-a-five-step-path-to-evaluations-you-can-trust/4532311](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/before-you-ship-your-agent-a-five-step-path-to-evaluations-you-can-trust/4532311)
- **Edge of Context blog / trace2evals (June 2026):** "A chatbot hands you one answer to grade. An agent hands you a whole tree of decisions: plans, tool calls, retries, and the moment it decided it was done." Proposes the full loop: trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring. Companion GitHub repo: [slavadubrov/trace2evals](https://github.com/slavadubrov/trace2evals). — [https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/](https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/)
- **Galileo AI evaluation guide (July 2026):** "Agents can achieve 60% success on single runs but drop to 25% across eight runs." Documents a three-tier rubric with 7 dimensions, 25 sub-dimensions, and 130 items. Cites Gartner: 40%+ of agentic AI projects will be cancelled by 2027, attributing this to eval gaps, not model capability gaps. — [https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Confident AI (DeepEval):** Documents trajectory failure modes output evals miss: context drift, knowledge attrition, infinite loops, circular reassurance ("I'm on it" without new state), and latency abuse (six verbose turns when two would do). — [https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)
- **GitHub: abhiai-git/agent_trajectory_evaluation:** Python package for evaluating tool-using LLM agent reasoning trajectories — modular framework supporting trajectory-level and telemetry-level evaluation. — [https://github.com/abhiai-git/agent_trajectory_evaluation](https://github.com/abhiai-git/agent_trajectory_evaluation)

## Gotchas

- **Evaluating the evaluator is often skipped.** LLM-as-judge scales evaluation but drifts without human calibration. Without measuring the judge's own accuracy, you're flying blind.
- **Cost and latency operating envelopes must be tracked alongside quality.** An agent that scores well but burns 10x the budget or takes 5x longer is not a success — track step counts, token usage, and per-run cost in the same traces as quality metrics.
- **A green output can hide a red trajectory.** The most dangerous production failures are the ones that look like success. Periodic trace auditing — even on successful runs — catches agents that are getting lucky rather than reasoning correctly.
- **Human-in-the-loop is calibration, not replacement.** Human review of a sample of traces calibrates the automated judge and surfaces "metric green, user red" failures. It does not replace broad scenario coverage.
