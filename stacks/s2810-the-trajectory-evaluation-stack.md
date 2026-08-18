# S-2810 · The Trajectory-Evaluation Stack

When your agent works in demos but fails silently in production — and you have no idea which step broke.

## Forces

- **Final-answer accuracy lies.** The agent can produce a correct output via a broken, wasteful, or unreliable path. Passing a final-output check tells you nothing about whether the agent will replicate that success.
- **Agent behavior is non-deterministic.** Identical inputs produce different reasoning paths, tool choices, and retrieval strategies. One passing run is not a signal.
- **Traditional metrics don't map.** BLEU, ROUGE, and even MMLU were designed for single-turn tasks. Agents require measuring multi-step trajectories, tool selection, and recovery.
- **The belief-execution gap is massive.** 72% of AI teams believe comprehensive evaluation drives reliability; only 15% achieve it in practice. Most teams prototype hard and eval weakly.

## The move

Measure the entire trajectory, not just the destination. A three-layer evaluation architecture covers what single-layer checks miss:

- **Layer 1 — Final-answer evaluation.** Score the last output against an expected result. Every benchmark does this. It is necessary but insufficient. The answer can be right while the path to it was wrong.
- **Layer 2 — Trajectory evaluation.** Inspect the complete sequence: plan, tool calls, intermediate reasoning steps, retries, and outcomes. Measure: task success rate, total steps to completion, tool-call accuracy, and path efficiency. This is where the actual reliability signal lives.
- **Layer 3 — Per-turn evaluation.** Score each individual decision: was the right tool selected, was the error handled gracefully, was the context window used efficiently. Catch failure modes before they compound.

**The metrics that matter:**

- Task success rate (percentage of tasks completed correctly) — the anchor metric
- Tool-call accuracy (percentage of tool calls that were correct and useful)
- Steps per task (fewer steps = better reasoning efficiency)
- Cost per task (LLM calls + tool calls + retrieval)
- Latency per task
- Self-aware failure rate (how often does the agent recognize and flag its own failure vs. silently continuing)

**The LLM-as-judge pattern.** Use a separate LLM to score trajectory quality against a rubric. Target 0.80+ Spearman correlation with human judgment. This scales evaluation beyond manual review without abandoning qualitative judgment.

**Eval as product spec.** A well-designed eval suite should let someone understand product direction just by reading it. Evals serve double duty: as regression warnings ("don't deploy if this fails") and as milestones ("we shipped this capability"). Teams that treat evals as first-class artifacts improve faster.

**Trace everything.** Full trajectory traces — plans, tool calls, intermediate reasoning, outcomes — are the raw material for evaluation. Open-source tooling (AgentTrace for LangGraph, LangSmith for LangChain/LangGraph) captures these automatically. Without trace-level data, you cannot evaluate trajectories.

**CI/CD integration.** Evaluation must run automatically on commit, schedule, and deployment events — not just manually. Commit-level triggers catch regressions before they reach production.

## Evidence

- **HN Discussion (128 points):** Practitioners report evals are "vital for improving performance" and serve as either regression gates or milestones. Without evals, teams cannot know if changes improve or degrade the agent. — [Hacker News — "Principles for production AI agents"](https://news.ycombinator.com/item?id=44712315)
- **HN Discussion:** Building AI agents for a year, a developer documented that evaluating only final output is fundamentally broken — you need to evaluate the path, not just the destination, because an agent can reach a correct answer via a flawed or non-replicable process. — [Hacker News — "Are we evaluating AI agents all wrong?"](https://news.ycombinator.com/item?id=46215574)
- **Industry Survey (Galileo, 2025):** 72% of AI teams strongly believe comprehensive testing drives reliability, yet only 15% achieve elite eval coverage (90–100% of behaviors tested). The 57-percentage-point gap is the primary driver of production failures. — [Galileo — "AI Agent Metrics: How Elite Teams Evaluate"](https://galileo.ai/blog/ai-agent-metrics)
- **NVIDIA Technical Blog (2026):** Agent evaluation measures end-to-end system behavior (task success, tool call accuracy, trajectory efficiency) versus model evaluation which measures foundation model capabilities (knowledge, reasoning). Trajectory-level tracking is required — static benchmarks like MMLU and HumanEval measure the engine, not the journey. — [NVIDIA — "Mastering Agentic Techniques: AI Agent Evaluation"](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)
- **InfoQ (March 2026):** Classical NLP benchmarks (BLEU, ROUGE) fail to capture agent-specific failure modes. Hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis) with human judgment is non-negotiable for production systems. — [InfoQ — "Evaluating AI Agents in Practice"](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **GitHub — AgentTrace:** Open-source observability platform for LangGraph agents providing real-time trace visualization, cost tracking, and interactive replay — making trajectory-level evaluation accessible without enterprise tooling. — [AgentTrace GitHub](https://github.com/liam-ringstad/agenttrace)
- **arXiv (2026):** RealClawBench introduces evaluation from live developer-agent sessions — success means completing the user's intended task in the actual environment where the task arose, not a synthetic proxy. — [arXiv:2606.03889](https://arxiv.org/abs/2606.03889)

## Gotchas

- **Final-answer pass ≠ reliable agent.** A correct answer achieved via a broken trajectory will not replicate. The next run may fail.
- **Eval inflation.** Agents can overfit to eval suites, especially narrow ones. Rotate test cases and inject distribution shift to keep evals honest.
- **Trajectory data is expensive to store.** Full trace capture at production scale generates significant volume. Budget storage and implement selective trace retention (full fidelity for failures, summary for successes).
- **LLM-as-judge has its own failure modes.** Judges can be biased, inconsistent across providers, and sensitive to prompt framing. Validate judge quality against human-labeled samples before relying on it.
- **Coverage is harder than it looks.** Reaching 90% behavioral coverage takes sustained investment. Many teams declare victory at 40% and ship agents that fail on the uncovered cases.
