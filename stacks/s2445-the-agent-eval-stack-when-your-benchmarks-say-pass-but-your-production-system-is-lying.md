# S-2445 · The Agent Eval Stack — When Your Benchmarks Say Pass But Your Production System Is Lying

Your eval suite reports 94%. Your agent is in production. Every week a different customer hits a failure mode your suite never caught. The problem is not that your agent is bad. The problem is that you are testing the wrong thing in the wrong place in the pipeline. GenAI produces content. Agents produce outcomes. Those require completely different evaluation practices — and most teams discover this the expensive way after shipping.

## Forces

- **Agents fail without erroring.** The most expensive production failures return HTTP 200 with the wrong outcome. Your eval suite sees the 200 and counts it as a pass. Traditional software testing catches exceptions; agent reliability requires catching behavioral failures at every layer of the execution chain.
- **Trajectory vs. outcome.** A task-completion eval tells you the destination was reached — not whether the agent took a reasonable path, wasted 40 tool calls getting there, or happened to arrive by accident. Both matter for different reasons, and most teams only measure one.
- **Eval staleness is silent.** Agents drift. Model updates, prompt changes, upstream API changes, and traffic pattern shifts all change agent behavior. An eval suite that was accurate in January can be misleading in April. Most teams have no mechanism to detect this.
- **The measurement imbalance is structural.** A systematic review of 84 papers from 2023–2025 found 83% report capability/technical metrics while only 30% report human-centered metrics and 15% report both. Teams measure what is easy to count, not what matters.
- **Public benchmarks don't translate.** MMLU, GSM8K, and HumanEval are model-level benchmarks — they test whether an engine is powerful. They have near-zero correlation with whether your agent reliably books the right flight, escalates correctly, or doesn't loop forever on edge cases.

## The move

Build a layered eval stack that evaluates agents at every level of the execution chain. Each layer answers a different question.

**Layer 1 — End-to-end task completion (start here).** Define a binary or rubric-based success criterion per task type. "Did the agent meet the user's goal?" Treat this as your ground truth. If this passes, everything below is optimization. If this fails, everything below is noise. Source these test cases from real production failures: tickets that required manual escalation, user complaints, edge cases your agent mishandled — not hypotheticals.

**Layer 2 — Trajectory metrics.** Instrument your agent to capture the full execution trace: tool selection decisions, intermediate reasoning steps, step count, and memory retrieval operations. Measure: tool selection accuracy (did it call the right tools?), path efficiency (did it take a reasonable route?), and memory hit rate (did it retrieve relevant context?). Amazon's agent framework evaluates across these four dimensions: accuracy of tool selection, coherence of multi-step reasoning, efficiency of memory retrieval, and overall task completion rate. Capturing traces is a prerequisite — you cannot debug what you cannot see.

**Layer 3 — Atomic unit evals.** Test individual tools and components in isolation: "Does the search tool return relevant results for X?" "Does the JSON parser handle malformed input gracefully?" These run fast, catch regressions early, and are easy to diagnose. DeepEval's pytest integration enables this pattern natively — wrap your agent with the `@agent` decorator to automatically capture span trees showing every LLM call and tool invocation.

**Layer 4 — LLM-as-judge for quality.** For aspects that resist programmatic scoring — "is this response on-brand?" or "did the agent communicate appropriately?" — use a separate LLM as judge. Run this on a sample of outputs rather than the full test suite; it is expensive and non-deterministic but catches things rules cannot.

**Layer 5 — Production sampling.** Dedicate a subset of eval capacity to anonymized samples from live traffic. This catches the distribution shift that calibration sets miss — production traffic always looks different from your hand-crafted test set after months of operation. AgentMode AI recommends 10–50 prompts per week sampled from production with manual scoring against the agent's intended-use rubric.

**Keep the eval suite alive.** Evals go stale. Set explicit triggers for recalibration: model changes, prompt updates, upstream API changes, OWASP Agentic Top 10 updates, or red-team findings. Update the eval set monthly at minimum.

## Evidence

- **Amazon engineering post:** "Thousands of agents deployed since 2025" required a fundamental shift from evaluating isolated prompts to assessing accuracy of tool selection decisions, coherence of multi-step reasoning, efficiency of memory retrieval, and overall task completion. Traditional black-box evaluation fails to decompose root causes across the execution chain. — [AWS AI Blog, "Evaluating AI Agents: Real-World Lessons from Building Agentic Systems at Amazon"](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **Academic survey:** Systematic review of 84 papers (2023–2025) found 83% report capability/technical metrics, ~30% human-centered metrics, ~30% economic metrics, and only 15% report both technical and human-centered dimensions. "This measurement imbalance undermines claims of deployment readiness." — [arxiv.org/html/2509.00115v2](https://arxiv.org/html/2509.00115v2), "Adaptive Monitoring and Real-World Evaluation of Agentic AI Systems," August 2025
- **HN practitioner discussion:** "No amount of evals will replace the need to look at the data… Add e2e evals, define a success criteria (did the agent meet the user's goal?) and make the evals output a simple yes/no value. This is much better than no evals." — [Hacker News, "Evaluating Agents" thread](https://news.ycombinator.com/item?id=45121547), linked article from aunhumano.com (Sep 2025)
- **Cleanlab enterprise survey (n=95 production deployments):** Only 5.2% of surveyed enterprises have AI agents live in production. Of those, 63% plan to improve observability and evaluation as their top investment priority. <1 in 3 teams are satisfied with their current observability and guardrail solutions. — [Cleanlab, "AI Agents in Production 2025"](https://cleanlab.ai/ai-agents-in-production-2025)
- **NVIDIA technical blog:** MMLU/GSM8K/HumanEval measure model-level capability in isolation; GAIA, SWE-bench, and WebArena measure end-to-end agent trajectories in dynamic environments. "A high MMLU score is a prerequisite, not a guarantee of reliable agent performance." — [NVIDIA Developer Blog, "AI Agent Evaluation"](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/), May 2026

## Gotchas

- **Binary pass/fail hides the failure mode.** A task-completion eval that returns "pass" because the agent eventually reached the right state does not tell you whether it took 3 steps or 47. Measure both.
- **LLM-as-judge evaluates the last step, not the trajectory.** A judge model grading a final response will miss intermediate failures — a tool called with wrong parameters, a loop that ran too long, a retrieval that returned noise. Use trajectory metrics at Layer 2 to catch these.
- **Evals built from hypotheticals don't catch production drift.** Test cases invented by engineers miss the edge cases that only appear in real traffic. Seed your eval set with real escalation tickets and customer complaints.
- **Public leaderboard scores are for model comparison, not production readiness.** A 92% on SWE-bench tells you something about your model's coding capability. It tells you nothing about whether your agent handles rate limiting, malformed API responses, or user off-topic pivots in a multi-turn conversation.
