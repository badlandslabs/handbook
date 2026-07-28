# S-1794 · The Grain Size Stack — When Your Agent Chops Work Into Pieces That Are Too Big or Too Small to Handle

Your agent decomposes "build a customer portal" into three enormous steps. Each step exceeds what fits in a single tool-call loop, context fragments, and the agent loses track of what it was doing mid-execution. Or your agent decomposes "format this date" into seven micro-steps, spending more time on orchestration overhead than on the actual task. The problem isn't whether to decompose — it's choosing the right grain size, and having the discipline to adjust it when execution proves the initial decomposition wrong.

## Forces

- **Coarse decomposition makes subtasks too big for a single LLM loop.** The agent starts executing a step, runs out of tool-call budget, and returns mid-task with no way to resume cleanly. Context window pressure then forces the agent to compress earlier work, introducing drift.
- **Fine decomposition buries you in orchestration overhead.** Every boundary between subtasks is a coordination point, a context switch, and a potential failure surface. The cost compounds when parallelizable steps are serialized by over-decomposition.
- **The sweet spot shifts during execution.** What looked like a single step in the plan turns out to need four tool calls. What looked like a complex module turns out to be a one-line API call. Static decomposition at planning time ignores what execution reveals.
- **Runtime failures break static decomposition catastrophically.** A monolith step that partially succeeds leaves you with no recovery path. Micro-steps where one fails force a full restart. The granularity you chose determines which failure modes you can survive.

## The move

**Design decomposition by execution grain, not by task description.**

- **One subtask = one LLM reasoning cycle + its bounded tool calls.** The subtask should complete within 1–5 tool invocations, not 50. If you're writing "write the entire authentication system" as one step, you've defeated the purpose of decomposition. If you're writing "import the datetime library" as one step, you've created overhead with no benefit.
- **Target 3–7 subtasks per decomposition level.** Fewer than 3 means the steps are too coarse — break them. More than 7 means cognitive overhead from tracking dependencies overwhelms the benefit. Each subtask at this level should take a single agentic turn to complete (one reasoning + one action or one tool-call loop).
- **Use a "stop decomposing" heuristic.** If a subtask takes more than 5 agent iterations to complete, it needs further decomposition. If it completes in one tool call, it was probably over-decomposed at the parent level.
- **Interleave planning and execution for adaptive grain size.** Plan-and-Execute (plan all steps upfront) is predictable and auditable, but blind to execution realities. ReAct (think one step, act, observe, repeat) is adaptive but myopic. The hybrid that wins in production: plan all steps at a coarse level, execute with adaptive decomposition — expand a step into substeps only when the first tool call fails or returns partial results.
- **Runtime-structured decomposition externalizes control flow.** IBM Research (arXiv:2605.15425, May 2026) demonstrates that runtime-structured task decomposition — where task structure lives in executable control flow, not in prompts — enables selective retry at the failed subtask level. In agentic coding systems, this achieved up to a **73.2% reduction in retry cost** versus monolithic reruns and **51.7% reduction** versus static decomposition, because only the failed step reruns.
- **Include verification as a first-class subtask, not an afterthought.** Don't plan "write code, then test it." Plan "write code → verify it compiles → verify tests pass → verify it matches spec." Verification steps have the same grain-size discipline as execution steps.

## Evidence

- **{Codemia Course — Planning and Task Decomposition (2026):}** Over-decomposition splits a simple task into too many tiny pieces, adding orchestration overhead without benefit. Under-decomposition leaves subtasks that are still too complex for the agent to handle in one step. The sweet spot: **3–7 subtasks per level**, each taking **1–5 agent iterations** to complete. If a subtask takes more than 5 iterations, it probably needs further decomposition.
  — [codemia.io/courses/introduction_to_agentic_ai/planning_and_task_decomposition](https://codemia.io/courses/introduction_to_agentic_ai/planning_and_task_decomposition)

- **{IBM Research — Runtime-Structured Task Decomposition (arXiv:2605.15425, ACM CAIS 2026, May 2026):}** Dynamic task partitioning at runtime — re-decomposing a failed step into smaller substeps rather than rerunning the entire plan — achieved **up to 73.2% cost reduction** over monolithic reruns and **51.7% cost reduction** over static decomposition in agentic coding benchmarks (RCA workload and multi-file debugging). The key insight: task structure belongs in executable control flow, not embedded in prompts.
  — [arxiv.org/html/2605.15425v1](https://arxiv.org/html/2605.15425v1)

- **{Astro Agent Orchestrator — HN Discussion (4 months ago):}** Astro generates a **dependency DAG** at planning time, with each node as an isolated `git worktree` environment. Tasks run in parallel with explicit dependency ordering. One practitioner noted: "DAG-based task decomposition and the runtime orchestration layer are actually two different problems — the DAG handles *what runs in what order*, the orchestration handles *what actually happens inside each node*."
  — [news.ycombinator.com/item?id=47355676](https://news.ycombinator.com/item?id=47355676)

- **{AgentEngineering.org — Planning and Task Decomposition (March 2026):}** "Planning chooses where the system is trying to go next. Task decomposition chooses the size and shape of the work units used to get there. These are not interchangeable." Key decomposition decision points: What has to happen before something else? What information is missing? What can be done in parallel? What should be verified before moving on?
  — [agentengineering.org/articles/planning-and-task-decomposition/](https://agentengineering.org/articles/planning-and-task-decomposition/)

- **{Stanford HAI, 2026 — cited by Velocity Software Solutions (June 2026):}** **68% of enterprise AI agent failures in production trace back to recovery loops** (replanning, retry, re-execution) rather than the original failed step. Poor decomposition granularity is a primary driver — when a failed step is too coarse, the entire recovery loop restarts from an invalid state. When steps are too fine, recovery loops spin through micro-steps endlessly.
  — [velsof.com/ai-automation/ai-agent-replanning-2026/](https://www.velsof.com/ai-automation/ai-agent-replanning-2026/)

## Gotchas

- **Don't decompose at the planning level and then forget about it.** The first decomposition is a hypothesis, not a fact. Runtime execution is what reveals whether grain size was right. Build in a "re-decompose on partial failure" path.
- **Decomposition depth compounds quickly.** A task decomposed into 5 subtasks, each with 5 sub-subtasks, is a 25-node graph. Map this explicitly before you hit 200 nodes with untracked dependencies. The DAG is your friend — it makes dependencies visible before they bite you.
- **Human-observable tasks break decomposition discipline.** When a human is watching the agent work, there's pressure to make the decomposition match human intuition ("this should be one step"). Trust the execution grain heuristic instead: if the step needs more than 5 iterations, decompose it regardless of how natural it looks as a single step.
- **Verification steps are the first thing engineers skip under time pressure.** They treat "verify" as optional. It isn't — unverified steps accumulate undetected errors that surface three decomposition levels later as mysterious failures.
