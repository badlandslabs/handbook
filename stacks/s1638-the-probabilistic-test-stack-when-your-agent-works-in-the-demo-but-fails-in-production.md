# S-1638 · The Probabilistic Test Stack — When Your Agent Works in the Demo but Fails in Production

You ship an agent, it works perfectly in testing, then silently degrades in production — until a customer complaint surfaces the problem three days later.

## Forces

- **Non-determinism is the default, not the exception** — the same input can produce different tool calls, reasoning paths, and outputs across runs, making pass/fail binary testing meaningless.
- **The benchmark-to-production gap is measurable** — enterprises report ~37% performance drop between lab benchmark scores and live deployment, and ~88% of agent pilots never reach production at all (Next Waves Insight, 2026; Cleanlab, 2025 survey of 95 engineering leaders with live agents).
- **Traditional testing frameworks assume deterministic outputs** — pytest assertions on LLM responses fail non-deterministically, giving false negatives and eroding team trust in the test suite.
- **Evaluation is undersampled** — only ~5% of surveyed enterprises have agents live in production, and <1 in 3 teams are satisfied with their observability/guardrail solutions (Cleanlab, August 2025).
- **Component-level failures compound** — a reasoning layer error cascades into a wrong tool call, which cascades into an incorrect final output; testing only the output masks which layer broke.

## The Move

Separate evaluation into layers and instrument each one independently. Treat evaluation as a first-class CI/CD citizen with stochastic assertions, not binary pass/fail.

**Reasoning layer evaluation:**
- Verify the agent's plan at each step — does the reasoning trace show correct intermediate goals before tool calls?
- Use trajectory analysis to assess *how* the agent arrived at a conclusion, not just whether the final answer is right.
- Metrics: step-level goal alignment, planning coherence score, hallucination detection on internal reasoning.

**Action layer evaluation:**
- Assert on tool call accuracy: correct tool selected, correct arguments passed, correct sequencing.
- Run tool-call benchmarks like BFCL (Berkeley Function Calling Leaderboard) as regression gates.
- Record full tool timelines with arguments, results, and timing for post-mortem debugging.

**End-to-end evaluation:**
- Task completion: did the agent achieve the user's goal? Use LLM-as-judge on the full execution trace rather than scoring outputs in isolation.
- Use golden datasets derived from real production failures — not curated happy-path examples.
- Assert on *pass rates* over N runs, not binary pass/fail. If a task succeeds 7/10 times, that's a measurable 70% reliability signal, not a flaky test.

**Operational layer:**
- Build evaluation into CI/CD pipelines so every code change triggers an eval suite.
- Log full execution traces with timestamps, token counts, and cost estimates per run.
- Set alert thresholds on aggregate metrics (e.g., task completion rate drops below 80% → page on-call).

## Evidence

- **Cleanlab enterprise survey:** Only 5% of enterprises have AI agents live in production (95 of 1,837 screened respondents); 70% of regulated enterprises rebuild their agent stack every 3 months or faster. Less than 1 in 3 teams are satisfied with observability and guardrail solutions. 63% of enterprises plan to improve observability and evaluation capabilities. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **DeepEval (confident-ai/deepeval, 17k+ GitHub stars):** Open-source framework modeled on pytest for LLM applications. Runs evals via metrics including G-Eval, task completion, answer relevancy, and hallucination detection. Supports LLM-as-judge evaluation of full agent traces. Compatible with LangChain, OpenAI Agents, and 10+ frameworks. Evaluates reasoning and action layers separately for component-level debugging. — [github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)
- **AgentEval (.NET):** Microsoft's evaluation toolkit for AI agents introduces "stochastic evaluation" — assert on pass *rate* over multiple runs rather than single pass/fail, addressing the fundamental non-determinism problem. Includes behavioral policies (guardrails as code), full tool timelines, and OWASP LLM Top 10 2025 red team probes. — [github.com/AgentEvalHQ/AgentEval](https://github.com/AgentEvalHQ/AgentEval)
- **Thoughtworks:** Proposes a layered eval framework: unit evals (prompt-level), integration evals (tool chains), and production observability (real-time quality monitoring). Notes that 95% of AI projects fail largely because teams cannot measure whether the system is working. — [thoughtworks.com/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production](https://www.thoughtworks.com/en-in/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)
- **Trajectory evaluation:** agent_trajectory_evaluation (abhiai-git) evaluates the *reasoning process*, not just final answers — flagging when an agent reached a correct answer via incorrect reasoning, which component-level eval would miss. — [github.com/abhiai-git/agent_trajectory_evaluation](https://github.com/abhiai-git/agent_trajectory_evaluation)

## Gotchas

- **Golden datasets go stale fast** — if your agent's behavior shifts (new model version, prompt update), old golden cases may no longer reflect expected outputs. Re-derive golden datasets from production traces quarterly.
- **LLM-as-judge has biases** — judges favor verbose outputs, agree with initial positions, and exhibit positional bias toward first options. Calibrate judge prompts and use deterministic heuristics for safety-critical assertions.
- **Stochastic evaluation multiplies CI run time** — running 10 trials per test to get pass rates is 10x slower. Budget compute accordingly or sample strategically (run full trials only for critical paths).
- **Trace storage costs scale with agent complexity** — a 50-step agent run produces ~50x more trace data than a simple RAG query. Set retention policies and sample aggressively for non-critical paths.
- **The 37% production gap means your benchmark suite is lying to you** — SWE-bench shows 87.6% on curated GitHub issues but production agents face API rate limits, auth complexity, schema drift, and compounding failure states. Test in production-adjacent environments, not just static benchmarks.
