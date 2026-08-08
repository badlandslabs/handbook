# S-2353 · The Task-Completion Gap Stack — When Your Agent Says Done But Isn't

Your agent reports task completion. Your dashboard shows 95% success rate. Then you spot-check the outputs and find only 70% are actually correct. The gap between "said done" and "actually done" is the task-completion gap, and it silently kills production agent deployments. Teams discover it the hard way: after shipping, after users complain, after the error surfaces in a quarterly audit.

## Forces

- **Task completion ≠ output correctness.** A "completed" task can still produce wrong answers, malformed data, or actions taken on incorrect premises — and the agent has no native signal to distinguish the two.
- **Agents are pipelines, not endpoints.** Unlike a chat response, a multi-step agent produces multiple intermediate states where errors compound: wrong tool choice → wrong data → wrong conclusion → confident wrong output. A single pass/fail metric misses all of it.
- **Ground truth is expensive to create.** Agent evaluation requires gold-standard examples with the full action trace — not just input/output pairs but the sequence of tool calls, decisions, and recovery steps. Most teams don't budget for this upfront.
- **LLM-as-judge is helpful but unreliable.** Using a separate LLM to evaluate agent outputs is cheap and scalable, but the judge model has its own failure modes: it can be gamed by confident wrong answers, suffers from position bias, and has no access to the environment state the agent was acting on.

## The move

**Measure the gap directly, then close it from both ends — evaluation pipeline and agent architecture.**

- **Track completion rate and accuracy rate as separate metrics.** Completion rate = did the agent reach an end state. Accuracy rate = did that end state match the true objective. The difference between them is your gap. One engineering team discovered their agent "completed" 95% of tasks but only 70% were correct — the 25-point gap was invisible until they measured it.
- **Build a bespoke eval suite per agent, not a generic one.** LangChain's production learnings across four deep agents found that traditional dataset-based evals break down for long-running agents. Instead, they used custom assertions per datapoint, single-step decision validation, and full trace replay — each pattern catching failures the others miss.
- **Run single-step evals at every decision point.** Between the input and the final output, the agent makes N tool-selection and reasoning decisions. Validate each one independently. This catches error compounding early and tells you exactly which step failed.
- **Use LLM-as-judge as a signal, not a verdict.** Run LLM-as-judge in the eval pipeline (cheap, fast), but spot-check results against ground truth. Train a smaller model on your specific output domain for faster turnaround without relying on frontier model access.
- **Simulate failure modes in the eval environment.** Don't just test happy paths. Include cases where tools return empty results, APIs timeout, selectors break, or the agent picks the wrong tool. LangChain found reproducible test environments with seeded failure states essential for validating recovery behavior.
- **Alert on the gap trend, not the gap absolute.** The gap will never be zero. What matters is whether it's growing — which signals model drift, upstream API changes, or tool schema updates that broke your agent's reasoning.

## Evidence

- **HN discussion (July 2025, 128 points):** Practitioners debated evaluations as the foundation for reliable production agents. One commenter's team started with "hundreds of evals" and concluded "less is more" — focused coverage of decision points beats exhaustive test count. Another noted "we discovered our agent was completing tasks at 95% but only 70% were correct" — the gap was invisible until measured explicitly. — https://news.ycombinator.com/item?id=44712315
- **LangChain production deep agents (2025):** Deployed four production deep agents (coding, email, agent-building). Built a five-pattern evaluation approach: bespoke test logic per datapoint, single-step evaluations, full agent turn tests, multi-turn with conditional logic, and reproducible environment setup. Found traditional dataset-based evaluation insufficient for stateful, long-running agents. — https://blog.langchain.com/evaluating-deep-agents-our-learnings/
- **MachineLearningMastery production evaluation guide (Feb 2026):** Outlines four evaluation pillars: task success, tool usage quality, efficiency/cost, and safety/alignment. Argues traditional LLM metrics (BLEU, perplexity) don't apply because agents take actions, invoke tools, and must recover from failures — evaluating agents is like testing an entire financial system, not a calculator. — https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance

## Gotchas

- **A pass/fail rate is not a quality metric.** An agent can complete every step in a workflow but produce a wrong final answer. You need output correctness validation, not just trace completion validation.
- **Eval coverage decays as the agent changes.** A test suite written against the current agent prompt and toolset will silently become less representative as you iterate. Re-derive eval cases when the agent's scope or tooling changes significantly.
- **LLM-as-judge can be gamed.** Confident wrong answers score higher than uncertain right answers on many judge prompts. Calibrate your judge prompt specifically for your output domain, and include adversarial test cases that test whether confident errors outscore cautious correctness.
