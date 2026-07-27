# S-1742 · The Evaluation Stack: When You Can't Tell If Your Agent Is Working

Your agent ships. It calls tools, loops, returns results, and logs show zero errors. But you're not sure if it's doing the right things — you just know it's doing *things*. The gap between "the agent ran" and "the agent worked" is where teams waste months before they realize the deployment failed silently.

## Forces

- **Agents are systems, not models** — a single accuracy score on the final output is insufficient; agents plan, call tools, maintain state, and adapt across multiple turns, and each failure mode requires its own evaluation layer
- **The trajectory is the product** — unlike single-turn LLMs, an agent's path (which tools it called, in what order, with what arguments) determines whether it will succeed reliably; two agents with identical outputs can have wildly different failure profiles
- **Production data exposes benchmark gaps** — public benchmarks use clean, canonical inputs; real users send null values, Unicode names, malformed fields, and adversarial prompts that benchmarks never anticipated
- **Automated evals catch regressions, humans catch quality** — teams that rely exclusively on automated scoring miss tone, trust, and contextual appropriateness; teams that rely exclusively on human review can't iterate fast enough
- **Measuring "completion" ≠ measuring correctness** — one practitioner found their agent was completing 95% of tasks but only 70% of completions were actually correct; the 25-point gap was invisible without task-level ground-truth validation

## The move

Evaluate at three levels: outcome, trajectory, and component. Stack them diagnostically — outcome first to catch failures, trajectory next to localize them, component last to fix the root cause.

### Evaluation hierarchy

- **End-to-end (outcome)** — does the task actually succeed? Binary or graded pass/fail on the final result. Use for regression suites and acceptance criteria. Deterministic where possible; LLM-as-judge for judgment-heavy tasks.
- **Trajectory-level (process)** — did the agent take the right steps? Scores tool selection, ordering, argument correctness, and path efficiency. Catches silent failures where the output looks right but the reasoning was wrong. A 3-tool success vs. a 15-tool-with-2-retries-and-a-hallucinated-parameter are not equivalent.
- **Component-level (diagnosis)** — which specific piece broke? Tests individual retrievers, sub-agents, tool definitions, or prompt chains in isolation. Use when trajectory analysis pinpoints a failing stage.

### Core metrics to track

- **Task success rate** — fraction of tasks completed correctly (not just completed)
- **Trajectory accuracy** — were the right tools called with the right arguments in the right order?
- **Tool call precision** — did it select the correct tool? Did it parameterize it correctly?
- **Cost per task** — token count and dollar cost per completed task; catches efficiency regressions faster than latency alone
- **Failure mode distribution** — categorize failures: API timeout, wrong tool, hallucinated parameter, context overflow, prompt injection. This tells you where to invest.
- **Completion-vs-correctness gap** — track separately; teams are routinely surprised by this delta

### Operational signals as first-class evals

- Tool call error rates and timeouts
- Context window utilization trends (an agent silently misbehaving when context fills is a common failure mode)
- Step-count variance across similar tasks (sudden spikes indicate confusion loops)
- Cost per session trending upward without business rationale

### The human-in-the-loop cadence

- **Automated evals run on every commit** — catch regressions in tool selection, trajectory shape, and output format
- **Human review on sampled traces** — 5-10% sample of production runs reviewed for quality, tone, and edge-case handling
- **LLM-as-judge for intermediate scoring** — faster than human review for routine quality checks; flag low-confidence scores for human adjudication
- **Periodic deep-dive** — full trajectory review on failed tasks, new failure patterns, and any production incident

### Failure modes to detect specifically

- **Context limit surprises** — agent works for 95% of conversations, then silently misbehaves when context window fills; no error, just wrong behavior
- **Cascade failures** — tool call #1 succeeds, #2 fails, agent continues with stale data from #1 as if #2 succeeded; trace-level checking catches this
- **Hallucinated tool parameters** — agent invents parameters that don't exist in the tool schema; requires tool-schema validation in the eval harness
- **Prompt injection** — if the agent processes external content, adversarial input can hijack its behavior; red-teaming is a first-class eval category

## Evidence

- **Survey (306 practitioners, 86 deployed agents):** 74% of deployed agents rely primarily on human-in-the-loop evaluation — automated evals are the exception, not the norm, despite widespread awareness of the gap. 95% of surveyed teams reported explicit challenges with evaluation. — [arXiv:2512.04123 "Measuring Agents in Production"](https://arxiv.org/html/2512.04123v1)
- **Engineering post:** Anthropic's eval framework distinguishes Task (defined inputs + success criteria), Trial (single attempt), Grader (scoring logic with multiple assertions), and Transcript (the full agent trace). They recommend deterministic assertions for tool-call correctness and LLM-as-judge for reasoning quality, noting that behavioral evals beat benchmark scores — [Anthropic Engineering "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Survey (KDD 2025):** A systematic evaluation taxonomy classifies evaluation objectives along two axes: what to evaluate (agent behavior, capabilities, reliability, safety) and how to evaluate (interaction modes, datasets, metric computation, tooling). Enterprise-specific challenges include role-based data access, reliability guarantees, and compliance requirements that no public benchmark captures. — [arXiv:2507.21504 "Evaluation and Benchmarking of LLM Agents: A Survey"](https://arxiv.org/abs/2507.21504)
- **Practitioner report:** One team discovered their agent "completing" 95% of tasks with only 70% actually correct — a 25-point completion-vs-correctness gap that was invisible without ground-truth validation. — [Data Science Duniya "AI Agent Performance Evaluation: A Production Engineer's Guide"](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide)
- **InfoQ analysis:** Agents are composite systems, not models. Classical NLP metrics (BLEU, ROUGE) score static text, not dynamic multi-step behavior. Operational constraints — latency, cost per task, token efficiency, tool reliability, and policy compliance — are first-class evaluation targets alongside quality. — [InfoQ "Evaluating AI Agents in Practice"](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

## Gotchas

- **Final-answer scoring hides path quality** — a trajectory that calls 15 tools, retries twice, and hallucinated a parameter can produce a correct-looking output; score the path, not just the output
- **Public benchmarks don't predict production performance** — benchmark data is clean and canonical; production data is messy, domain-specific, and follows distributions benchmark designers didn't anticipate
- **LLM-as-judge has known biases** — it rewards verbose, confident-sounding outputs and penalizes terse, correct ones; calibrate with human review samples
- **Context overflow fails silently** — when the context window fills, the agent doesn't error; it just degrades in ways that look like reasoning failures
- **Tool-schema mismatches surface at eval time** — if your eval harness validates tool-call arguments against the schema, it catches hallucinated parameters before production does
