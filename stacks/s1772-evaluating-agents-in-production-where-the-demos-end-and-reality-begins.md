# S-1772 · Evaluating Agents in Production — Where the Demos End and Reality Begins

AI agents look trustworthy in demos. They fail silently in production — corrupting data, taking wrong tool calls, running 10x longer than expected, and returning outputs that look plausible but are subtly broken. Traditional ML metrics (accuracy, F1, AUC) don't apply. Evaluating agents requires measuring trajectories, not just outcomes — and that changes everything about the stack.

## Forces

- **Traditional ML metrics assume a single correct answer** — agents have unbounded output spaces and stochastic behavior, making pass/fail non-obvious
- **Final-output evaluation misses most failure modes** — an agent can reach a correct answer through a catastrophic reasoning path, or fail at the last step after a perfect trajectory
- **Eval is underspecified until you run agents** — the failure modes that matter only emerge from tracing real executions, not from designing tests upfront
- **Human evaluation doesn't scale** — production agents handle thousands of requests/day; human review is a sampling strategy, not a quality system
- **Eval is the last thing teams build and the first thing they regret** — observability and guardrails are the top planned investment (63%) yet fewer than 1 in 3 teams are satisfied with what they have today

## The Move

A layered eval system with four orthogonal dimensions, run at two cadences (offline on datasets, online on production traffic):

**Four dimensions to measure:**
- **Trajectory quality** — Did the agent take a sensible reasoning path? Step count, wasted actions, loops, and recovery behavior. Use tool-call trace analysis and step-count benchmarks.
- **Tool-call accuracy** — Did the agent select the right tool and parameterize it correctly? The Berkeley Function-Calling Leaderboard (BFCL) is the canonical benchmark; SWE-bench Verified covers code agents.
- **Task completion** — Did the agent actually accomplish the goal? End-state evaluation using LLM-as-judge that reads the full execution trace, not just the final output.
- **Multi-turn quality** — Did the agent handle conversation turns coherently? Rootedness (does each turn reference prior context?), relevance, and handoff quality across turns.

**Two evaluation cadences:**
- **Offline (pre-deploy):** Fixed eval datasets, pytest-style test suites (DeepEval, AgentEval), deterministic assertions for decidable checks, LLM-as-judge for semantic quality. Gate on pass rates before shipping.
- **Online (production):** Sample 1–5% of production traffic, score with LLM-as-judge, cache verdicts on (input, output, rubric version) hashes, version all rubrics since a rubric change is a measurement change.

**Layered verification:**
- Deterministic code assertions for decidable items (exact matches, schema validation, API response codes)
- LLM-as-judge for semantic judgment (tone, reasoning quality, helpfulness) — targeting 0.80+ Spearman correlation with human judgment
- Human annotation to calibrate judges and cover edge cases

**CI/CD integration:**
- Run eval suites on every commit (commit-triggered)
- Scheduled regression runs against historical datasets (weekly/daily)
- Event-triggered evals on A/B model changes or prompt updates

## Evidence

- **Survey (Cleanlab, 2025):** 95 enterprise engineering/AI leaders with agents live in production. Key finding: fewer than 1 in 3 teams are satisfied with observability/guardrails; 63% plan to improve in the next year. Regulated industries rebuild their AI stack every 3 months at a 70% rate — eval and observability gaps drive churn. — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)

- **Company engineering post (Twilio Segment):** Built an LLM-as-Judge eval framework for their CustomerAI audiences feature (LLM-generated audience queries compiled to ASTs). Achieved >90% alignment with human evaluation for AST correctness, 3x improvement in audience creation time, 95% feature retention. Used synthetic eval data generation + structured scoring with multi-tier rubric. — [https://segment.com/blog/llm-as-judge/](https://segment.com/blog/llm-as-judge/) (via [https://www.zenml.io/llmops-database/llm-as-judge-framework-for-production-llm-evaluation-and-improvement](https://www.zenml.io/llmops-database/llm-as-judge-framework-for-production-llm-evaluation-and-improvement))

- **Engineering guide (Langfuse):** Documents the four-dimensional eval framework (trajectory, tool use, task completion, multi-turn) with offline/online cadence split. Notes that teams should start with manual trace review before building automated evals — patterns observed in traces inform what metrics matter. Recommends scoring 100% of CI traffic against fixed datasets and sampling 1–5% of production plus 100% of flagged responses. — [https://langfuse.com/resources/engineering/ai-agent-evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)

- **Benchmark research (Zylos, 2026):** Analyzes the "benchmark crisis" — UC Berkeley researchers found all eight of the most prominent AI agent benchmarks could be exploited to achieve near-perfect scores without solving the underlying tasks. Static task-completion scores fail to capture reliability, cost efficiency, safety, and long-horizon competence. Tool-calling accuracy identified as the single dimension most discriminates production-ready agents from demoware. — [https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)

- **Framework (NVIDIA, 2026):** AI model evaluation (MMLU, HumanEval) tests capability in isolation; AI agent evaluation tests the system end-to-end. Key shift: from measuring knowledge to measuring outcomes. Introduces trajectory efficiency, tool-call accuracy, and planning quality as agent-specific metrics beyond static benchmarks. — [https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)

## Gotchas

- **Evaluating only the final output is the most common mistake** — the agent can fail spectacularly on every intermediate step and still land on a plausible answer. Always inspect traces.
- **LLM-as-judge has systematic biases** — position bias (preferring first or last answer in comparative mode), self-preference bias (judges from the same provider favoring their own outputs), verbosity bias. Calibrate with 100+ human-annotated samples before trusting judge scores in high-stakes domains.
- **Benchmark gaming is real** — if your eval set is static and known, agents (or their underlying models) can overfit to it. Rotate eval sets, use adversarial test cases, and cross-reference against production signal.
- **Eval without observability is guesswork** — you can't improve what you can't measure, and you can't measure what you can't trace. Tracing infrastructure (Langfuse, Phoenix, etc.) is a prerequisite, not an afterthought.
- **Rubric version control matters** — comparing LLM-as-judge scores across rubric versions is comparing different rulers. Version every rubric and pin verdicts to (input, output, rubric_version) tuples.
