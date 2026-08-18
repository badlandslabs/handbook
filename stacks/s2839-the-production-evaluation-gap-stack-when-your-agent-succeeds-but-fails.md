# S-2839 · The Production Evaluation Gap Stack

When your agent scores 95% on benchmarks but 30% of its outputs are wrong in production.

## Forces

- **Task completion ≠ correctness** — agents can complete a task (call the right tools, reach an endpoint) while producing wrong results. Standard metrics miss this entirely.
- **Traditional benchmarks are broken for production** — SWE-bench, WebArena, OSWorld, and others measure capability under controlled conditions, not reliability in continuous operation. UC Berkeley found most major agent benchmarks have alarming correlations with real-world performance (or lack thereof).
- **Eval engineering is as hard as prompt engineering** — but most teams treat it as an afterthought. The result: reactive loops, production fires, and blind ship cycles.
- **Observability ≠ evaluation** — logging what your agent did is not the same as knowing whether it was right.

## The Move

Build a multi-layered evaluation system that measures the right things, continuously, with both automated and human oversight.

**Structured eval taxonomy (Anthropic, 2026):**
- **Task** — a single test with defined inputs and success criteria
- **Trial** — one attempt at a task (run multiple to handle variance)
- **Grader** — logic that scores some aspect of performance; contains multiple assertions
- **Transcript** — full trace: outputs, tool calls, reasoning, intermediate results
- **Outcome** — final environment state at trial end

**Three evaluation layers (AWS Agent Evaluation, Anthropic):**

1. **Task-level correctness** — did the agent accomplish what was asked? Binary or rubric-based assertions.
2. **Trajectory quality** — was the path right? LLM-as-judge scoring of reasoning traces, tool selection patterns, and decision chains.
3. **System-level health** — cost per task, latency, token efficiency, failure rate over time.

**Practical evaluation patterns from production teams (Asana, GitHub, Vindler):**

- **LLM-as-judge with guardrails** — use a second LLM to score the first agent's outputs, but constrain it with rubrics and reference answers to reduce hallucination in the evaluation itself.
- **Production failure replay** — capture every agent failure in production, add the (input, correct_answer) pair to an eval dataset, never let the same failure go unevaluated. Tools: MrTaleky's agent-evals, DeepEval's production event logging.
- **Continuous regression suites** — run evals on every code/model/prompt change. Integrate into CI/CD. Treat agent skills like software: versioned, tested, benchmarked before deploy.
- **YC-Bench-style long-horizon evals** — simulate multi-step, multi-week tasks to stress-test planning, state management, and error recovery. Most models fail at sustained task execution beyond 10-20 steps.
- **Generator-evaluator adversarial harness** — run two agents: one generates, one critiques. Inspired by GANs. The evaluator must have verifiable taste criteria, not just vibes. (Anthropic, "Harness design for long-running applications," 2026.)

## Evidence

- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" — defines the full eval taxonomy and three-layer evaluation approach for agent harnesses. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **arXiv research:** "Evaluating Agentic AI in the Wild: Failure Modes, Drift Patterns, and a Production Evaluation Framework" (Pandey, 2026) — observed 7 production failure modes at O(10⁹) events/day scale; standard metrics (ROUGE, BERTScore, AUC) miss 4/7 entirely and detect the other 3 with significant lag. Proposes PAEF framework. — https://arxiv.org/html/2605.01604v1
- **Company post:** Vindler Solutions "Agent Evaluation at Scale: Lessons from 2025's Production Failures" — 95% task completion rate masked 30% actual failure rate; only 3/12 models sustained $200K capital in YC-Bench simulation. — https://vindler.solutions/blog/agent-evaluation-at-scale
- **GitHub repo:** AWS Labs "Agent Evaluation" — open-source framework for automated evaluator-orchestrator agents that test target agents through conversation with built-in grading and CI/CD integration. — https://github.com/awslabs/agent-evaluation
- **Company post:** InfoQ "Evaluating AI Agents in Practice" — Asana's four-layer eval stack (unit tests, LLM-as-judge, integration tests, end-to-end manual grading); GitHub's trace-driven observability for eval. — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/
- **Survey paper:** "Evaluation and Benchmarking of LLM Agents: A Survey" (arXiv:2507.21504) — comprehensive taxonomy of 50+ benchmarks, 25+ tools, 60+ papers; covers AgentBench, SWE-bench, ToolBench, GAIA, and the shift toward evaluation-driven development (EDD). — https://arxiv.org/abs/2507.21504
- **Reddit/r/LocalLLaMA:** YC-Bench results — only 3/12 LLMs passed a year-long startup simulation; scratchpad usage was the strongest predictor of success; adversarial customers caused 47% of bankruptcies. — https://reddit.com/r/LocalLLaMA/comments/1sbyte4/we_gave_12_llms_a_startup_to_run_for_a_year_glm5/

## Gotchas

- **Synthetic benchmarks don't predict production failures** — scores on curated test sets have weak correlation with real-world reliability. Build evals from your actual failure data.
- **LLM-as-judge is not neutral** — the judge model has its own biases and can be gamed. Constrain it with rubrics, reference answers, and spot-check human audits.
- **Single-trial evals are noise** — agents are non-deterministic. Run multiple trials per task and aggregate. A single pass is insufficient for any consequential decision.
- **Latency and cost are first-class metrics** — a 99% accurate agent that costs $4 per query and takes 30 seconds is often worse than a 95% accurate one that costs $0.02 and responds in 2 seconds.
- **Eval is not one-time** — build continuous evaluation into your pipeline. A static eval suite from launch day will become misleading within weeks as your agent, model, and environment evolve.
