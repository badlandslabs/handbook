# S-1064 · The Trajectory Eval Stack — When Your Agent Passes the Answer and Fails the Mission

You grade your agent's final output. It looks right. You ship it. Three weeks later you discover the agent took 47 tool calls to reach that answer, hallucinated 2 API parameters, and silently skipped an error branch — but still arrived at a plausible output. Final-answer grading is a false signal for agentic systems. The real question is not "did it land correctly?" but "did it get there through sound reasoning, reasonable effort, and recoverable errors?"

## Forces

- **Agents are trajectories, not outputs.** An agent is a sequence of decisions — tool selections, state mutations, error recoveries, and reasoning steps. Grading only the final answer misses the entire execution path and cannot tell you *where* failure happened, *why* it happened, or whether the failure was acceptable given constraints.
- **Outcome and process are separable quality dimensions.** A task can succeed by luck (wrong tool, right result) or fail despite sound process (right tool, bad luck). Treating outcome as the only signal conflates these, and you cannot improve what you cannot decompose.
- **Component-level failures are invisible to end-to-end grading.** If your agent correctly routes 95% of requests but systematically mishandles refunds when a specific API returns a 500, a pass/fail on the final output hides the component weakness until it hits the right production input.
- **Evals must evolve from production failures, not just from benchmarks.** Static test suites go stale the moment your agent encounters real-world inputs the suite's author didn't anticipate. An eval framework without a feedback loop from production degrades continuously.

## The Move

Score agents on two independent axes — outcome (did the task complete?) and process (was the path sound?) — then decompose each axis to the component level so failures are locatable and fixable.

### Outcome scoring

- Define binary pass/fail on the terminal state: did the agent accomplish the stated goal? Use deterministic assertions where ground truth exists (e.g., "API returned 200", "database row updated", "file written to expected path"). Fall back to LLM-as-judge on final answer quality, but only after exhausting deterministic checks.
- Run each task across multiple trials to handle non-determinism. Log trial variance — if an agent passes 8/10 trials on the same task, that 20% failure rate is meaningful signal even if the final shipped run happened to succeed.
- Add regression coverage from production: every production failure becomes a permanent test case in the eval suite.

### Process scoring (trajectory-level)

- Score intermediate steps: was the right tool selected? Were arguments structurally correct? Did error handling recover or spiral? Use the agent's full trace (tool calls, responses, state deltas) as the artifact being graded, not just the final output.
- Track efficiency: tool call count, retry count, token budget consumed, time-to-completion. A trajectory that passes outcome but calls 40 tools to do what a better-planned agent does in 4 is a process failure.
- The TRACE framework (Chen et al., 2026) formally separates process quality from outcome correctness, finding that high accuracy does not imply intelligent or efficient reasoning — some agents reach correct answers through brute-force tool retry loops rather than genuine comprehension.

### Component-level decomposition

- Grade individual agent components independently: planning, routing, tool invocation, memory retrieval, error recovery. Instrument each component so you can isolate which one failed when a trial fails.
- This is the approach Amazon's Bedrock AgentCore Evaluations uses — evaluating each functional component (orchestration, knowledge base retrieval, function calling) against component-specific metrics before assessing the end-to-end behavior.
- Use the agent-as-judge pattern: a separate evaluation agent that has access to the full reasoning trace and a grading rubric outperforms LLM-as-judge that sees only the final output. In code task experiments, agent-as-judge matched human evaluator agreement at 96.3% vs 85.1% for output-only LLM judges.

### The eval suite as a living system

- Maintain golden datasets: version-controlled collections of input examples, expected outputs, evaluation criteria, and metadata (difficulty, category, source). Populate from domain expert judgments, production failures, and adversarial testing.
- Critique Shadowing (Hamel Husain): pair binary pass/fail judgments with detailed written critiques from a principal domain expert. The critique surfaces implicit expectations that are invisible in scores alone — tone, trustworthiness, contextual appropriateness.
- LLM-as-judge evaluators require 100+ labeled examples for calibration and ongoing weekly maintenance to stay aligned with human preferences as the agent evolves.
- Run evals in CI on every commit. Treat eval regressions with the same urgency as unit test regressions — a PR that causes eval regressions does not ship.

## Evidence

- **Anthropic Engineering Blog:** "Demystifying Evals for AI Agents" (Jan 2026) defines the formal eval vocabulary — task, trial, grader, transcript — and recommends three grading strategies (deterministic assertions, LLM-as-judge, golden sets) deployed as a layered system matching eval complexity to component complexity. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **AWS ML Blog:** "Evaluating AI Agents: Real-World Lessons from Building Agentic Systems at Amazon" (Feb 2026) describes Amazon's multi-tier approach — component-level eval, end-to-end system eval, and adversarial red-teaming — with human-in-the-loop for high-stakes decision scenarios and golden dataset creation. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **arXiv:2508.02994:** "When AIs Judge AIs: The Rise of Agent-as-a-Judge Evaluation" (Aug 2025) demonstrates that agent-as-judge — evaluating intermediate reasoning traces rather than final outputs — achieves 96.3% human agreement vs 85.1% for output-only LLM judges, preserving cost-effectiveness while improving informativeness. — [arxiv.org/html/2508.02994v1](https://arxiv.org/html/2508.02994v1)
- **Hamel Husain's Blog:** "Using LLM-as-a-Judge For Evaluation" documents Critique Shadowing — a binary pass/fail + written critique process driven by a principal domain expert — as the mechanism to surface implicit quality criteria that arbitrary numerical scales miss. — [hamel.dev/blog/posts/llm-judge/](https://hamel.dev/blog/posts/llm-judge/)

## Gotchas

- **Grading only final answers gives false confidence.** A trajectory that arrives at a correct answer via flawed reasoning will pass a final-answer eval but fail in production when the input shifts slightly and the flawed reasoning path leads to a different (wrong) answer.
- **LLM-as-judge alignment drifts without maintenance.** Judges calibrated against human preferences at launch degrade as the agent evolves. Schedule periodic re-calibration — Amazon recommends weekly for high-stakes agents.
- **Too many metrics bury signal.** Teams that track 40 eval metrics end up trusting none of them. Pick 3-5 outcome metrics and 2-3 process metrics, validated against actual user/business impact, not theoretical coverage.
- **Golden datasets stale in weeks without production feedback.** Building a static eval suite and never adding production failure cases means your evals become a shrinking sample of real failure modes.
