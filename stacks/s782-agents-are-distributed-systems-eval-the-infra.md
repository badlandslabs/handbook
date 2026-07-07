# S-782 · Agents Are Distributed Systems — Eval the Infra, Not Just the Model

You run your agent through 100 test cases. Score: 78%. You ship. In production, the agent fails on a broken URL, hangs on localhost calls in a cloud environment, and flags real CVEs as hallucinations. The model is fine. Your eval is lying to you.

## Forces

- **Eval catches model quality, not system health.** Agents interact with external systems — APIs, filesystems, network endpoints. A broken tool or misconfigured environment drops scores independently of model capability.
- **The right answer via the wrong path still fails in production.** An agent that reaches a correct final answer after calling the wrong tool, ignoring constraints, and making a lucky recovery has a good endpoint score and a bad trajectory.
- **Benchmarks lie at scale.** Traditional LLM benchmarks (BLEU, ROUGE) and even single-turn accuracy tests don't capture tool-call correctness, plan adherence, or recovery behavior.
- **Synthetic test data is cheap but the golden set is hard.** Generating test cases is easy. Curating ones that reflect real production failure modes — edge cases, permission boundaries, dependency failures — is expensive and slow.

## The Move

Shift evaluation from a model-quality concern to a **distributed systems concern**. Evaluate three layers:

**1. Trajectory-level metrics (the path, not just the destination)**
- Task completion: did the agent finish the goal?
- Step efficiency: how many steps vs. optimal path?
- Tool correctness: right tool, right arguments, right order?
- Plan adherence: did the agent follow the intended plan?
- Recovery quality: graceful degradation or silent failure?

**2. Infrastructure health (pre-condition for honest eval)**
- Validate all tool endpoints before running eval
- Confirm environment parity (localhost vs cloud, permissions, credentials)
- Mock or stub flaky external dependencies
- Check that agent-environment interactions match deployment context

**3. Three-level evaluation pyramid**
- **End-to-end:** did the task succeed? (binary + qualitative)
- **Trajectory-level:** was the path efficient, safe, and correct?
- **Component-level:** which specific tool, retriever, or sub-agent broke?

**Per-step rubrics over endpoint scores.** Assign pass/fail to each step in the trajectory. A trajectory rubric catches: wrong tool first, ignored constraint, lucky recovery, unnecessary round-trips.

**Pick the right judge per metric.** Use deterministic checks (exact-match, schema validation) for tool correctness and argument correctness. Use LLM-as-judge for reasoning quality, plan quality, and answer relevancy. Combine with periodic human review to keep judges calibrated.

**Build and grow the golden dataset from production failures.** Start with 50–200 real examples. Every production incident that slips through becomes a new test case. Add synthetic data via LLM to cover edge cases, but always validate synthetic examples against real behavior.

## Evidence

- **Blog post:** "Evaluating AI agents: Real-world lessons from building agentic systems at Amazon" — Amazon runs thousands of agents across the org. Their framework separates generic evaluation (standardized metrics across all agent types) from use-case-specific evaluation. Key finding: single-model benchmarks assess individual LLM performance; agentic AI requires evaluating emergent behaviors of the complete system — tool selection accuracy, reasoning coherence, memory retrieval efficiency, and task completion rates. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

- **Blog post:** "Evaluating Agents in Production: Trajectory Metrics, Not Just Final Answers" — Practitioner from jamesm.blog ran a small eval suite and found most failures came from system-level problems: broken URLs in tool calls dropped score to 22, agent calling localhost in cloud env got stuck at 46, real CVEs flagged as hallucinations were an eval artifact not a model problem. Conclusion: endpoint scoring certifies answers, not behavior. Recommends 50–200 real examples, per-step rubrics, 10+ runs per example, statistical regression tracking, and replay harnesses for regression suites. — [jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)

- **Technical guide:** "LLM Agent Evaluation Metrics in 2026: Complete Guide" — Confident AI / DeepEval (16.7k GitHub stars). Core metrics grouped into: tool calling (correctness, argument correctness, call count), planning (plan adherence, plan quality), task completion, and reasoning. Evaluates at three levels: end-to-end, trajectory-level, and component-level. Key design choice: tie every metric to a trace so a low score traces back to the exact span that caused it. DeepEval supports agentic-specific metrics (Task Completion, Tool Correctness) alongside standard RAG and conversational metrics. — [confident-ai.com/blog/llm-agent-evaluation-complete-guide](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)

- **Technical blog:** "Mastering Agentic Techniques: AI Agent Evaluation" — NVIDIA Technical Blog (May 2026). Distinguishes AI model evaluation (foundation model in isolation, static benchmarks) from AI agent evaluation (end-to-end trajectory: reasoning, tool calls, environment observations). Key benchmarks: GAIA for real-world assistance, SWE-bench for GitHub issue resolution, WebArena for web-based task execution. Core metrics: Task Success Rate (TSR), Tool Call Accuracy, Trajectory Efficiency, Cost per Task. — [developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)

## Gotchas

- **Eval before infrastructure validation produces misleading scores.** A 78% score that drops to 22% after fixing broken URLs is not a model regression — it's a broken eval setup. Validate the eval environment first.
- **LLM-as-judge has known biases.** Position bias (prefers first response), length bias (longer responses score higher), self-preference bias (judge favors its own style). Mitigate with pairwise comparisons, calibration against human judgment, and explicit bias-correction in the judge prompt.
- **Synthetic datasets cover ground truth gaps but don't replace production failures.** LLM-generated test cases miss the novel failure modes that only appear in real user interactions. Use synthetic data to scale coverage, use production incidents to preserve signal.
- **Holding out a test set you never tune against is non-negotiable.** If you iterate on eval criteria using the same test set you're measuring against, you'll overfit your eval to your agent's current failures — not to the actual failure distribution.
