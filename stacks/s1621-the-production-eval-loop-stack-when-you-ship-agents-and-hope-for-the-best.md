# S-1621 · The Production Eval Loop Stack

When your agent changes break silently, your test suite says "pass," and users find bugs first.

## Forces

- Agents are non-deterministic — same input can produce different trajectories, making "did it work?" a statistical question, not a binary one.
- A bad early step cascades: one wrong tool call can corrupt every following step, and end-to-end pass/fail masks where the failure originated.
- The final answer is only the last step of a longer run — grading the output without grading the trajectory is like grading a math exam by looking at the answer key without checking the work.
- 40% of enterprise AI failures in 2028 will trace to inadequate evaluation rather than model capability gaps (Gartner, 2026).
- Traditional benchmarks (BLEU, ROUGE, MMLU) measure token overlap or single-turn accuracy — they miss tool call fidelity, recovery behavior, and multi-step coherence.

## The move

Build an eval loop that closes the gap between "it works in the demo" and "it works in production."

### The core eval primitive: Task + Trials + Grader

Anthropic's evaluation framework (Jan 2026) defines three building blocks: a **Task** is a test case with defined inputs and success criteria; a **Trial** is one attempt at that task (run multiple to account for non-determinism); a **Grader** is the logic that determines pass/fail. The grader is where judgment lives — deterministic code for exact checks, LLM-as-judge for nuanced qualities.

### Three-level evaluation hierarchy

- **End-to-end (did it do the thing?):** Binary or graded task success. SWE-bench for coding agents; WebArena for web agents; custom business metrics for domain-specific tasks.
- **Trajectory-level (how did it get there?):** Efficiency, tool call sequence, recovery from errors. Amazon's Bedrock AgentCore Evaluations measure this across accuracy of tool selection, coherence of reasoning, and efficiency of memory retrieval.
- **Component-level (which part broke?):** Per-step tracing to isolate failures. Langfuse's observability captures every LLM call, tool invocation, and control-flow decision as structured traces — failures that hide in intermediate steps surface here.

### The eval-to-production flywheel

Braintrust's eval pattern: **production traces → test cases → evals → deploy**. Online evaluators score live traffic; failing traces auto-generate test cases; the eval suite grows organically from real user behavior. GitHub Actions blocks merges below a quality threshold.

### Pick the right grader for the job

- **Deterministic checks** for exact things: tool name correctness, API response schema, return type, function call arguments.
- **LLM-as-judge** for nuanced things: response tone, contextual appropriateness, whether the agent acknowledged uncertainty.
- **TRACE framework** (arxiv 2510.02837, Sep 2025) — an evidence bank accumulates knowledge from preceding reasoning steps to assess logical soundness without requiring a pre-defined ground-truth trajectory.

### Metrics that actually matter in production

Task completion rate | Tool call fidelity (% correct tools called) | Token efficiency (cost-per-task) | Recovery rate (did it gracefully handle errors?) | Trajectory length vs. optimal path | Latency per step | Hallucination rate in tool responses

### Trace everything, then replay

Langfuse captures full execution graphs for LangGraph, OpenAI Agents SDK, Claude Agent SDK, CrewAI, Pydantic AI, and Vercal AI SDK — zero manual instrumentation with their SDK wrappers. LangSmith's auto-dataset feature converts successful production traces into eval cases automatically.

## Evidence

- **Company engineering post:** Amazon's AI Agent Evaluation Library in Bedrock AgentCore uses a four-step automated workflow — define inputs, run trials, score, analyze — measuring tool selection accuracy, reasoning coherence, memory retrieval efficiency, and task completion. Published 2026. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)

- **Framework documentation:** Anthropic's eval framework (Jan 2026) introduces the Task/Trial/Grader model and advocates for pre-deployment eval loops to catch regressions before users do. Key insight: evaluations are first-class products — their value compounds across the agent's lifecycle. — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Academic paper:** TRACE (ICML 2026 / arxiv 2510.02837) proposes evaluating reasoning trajectories rather than final answers, using an evidence bank that accumulates knowledge from preceding steps to assess logical soundness without ground-truth trajectories. — [arXiv](https://arxiv.org/abs/2510.02837)

## Gotchas

- **Only grading the final answer:** Inspect the trajectory. A task can "succeed" by the wrong path — correct output from flawed reasoning that will break on the next edge case.
- **Single trial per task:** Agents are non-deterministic. Run at least 3-5 trials and track variance, not just the pass rate.
- **LLM-as-judge has LLM problems:** Judges inherit the biases and variance of the models running them. Calibrate against human judgment on a small set before scaling. The "eval lie" — where high eval scores mask real failures — is a documented failure mode.
- **Evals drift with the world:** Production agents interact with systems that change. A passing eval suite six months ago may not reflect current behavior if external APIs, UIs, or data have shifted.
