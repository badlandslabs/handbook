# S-1884 · The Planning Taxonomy Stack — When Your Agent Either Over-Thinks or Under-Plans

Your agent gets a complex task and immediately starts acting — taking the first plausible path without checking whether it's the right one. Or it freezes, spending 45 minutes mapping every edge case before touching anything. These are the two failure modes of agent planning: premature execution and analysis paralysis. The Planning Taxonomy Stack is how practitioners navigate between them, choosing the right architecture for the task's structure, the system's budget, and the failure cost.

## Forces

- **Planning and execution are separate cognitive jobs.** Treating them as one — interleaving reasoning and acting at every step — is simple to implement but burns tokens and creates context overflow on long tasks. Planning separately, then executing, reduces redundancy but risks executing a plan that became stale the moment the world changed.
- **Token cost compounds on long-horizon tasks.** A ReAct agent re-thinks every step through the full context. On a 20-step task, this can mean 2–5x the token cost of a Plan-Then-Execute agent that commits to a plan and executes it. This isn't theoretical — empirical measurements on coding agents show 39–60% input token reduction from trajectory pruning alone.
- **Not all tasks reward upfront planning.** A web research agent that needs to read results before knowing what to search next is fundamentally different from a code generation agent with a known target. Predictable, dependency-chained workflows (CI pipelines, data ETL, report generation) benefit from plan-then-execute. Unpredictable discovery tasks benefit from interleaved reasoning.
- **Context window degradation is real.** Agents performing beyond ~35 minutes of continuous execution show measurable quality degradation. Longer tasks need explicit checkpoint-and-resume mechanisms or hierarchical decomposition that limits how far an agent must look back.

## The Move

The core move is choosing the right point on the **planning-execution coupling spectrum** based on task structure, then implementing the chosen pattern with explicit failure recovery.

**1. Classify the task's planning sensitivity before choosing an architecture.**

- **High dependency / low surprise** (data ETL, report generation, CI pipelines): Plan-then-Execute. The plan is likely correct; re-planning adds cost without benefit.
- **High uncertainty / discovery-driven** (research, investigation, multi-source synthesis): Interleaved/ReAct. Each action reveals information that should shape the next action.
- **Complex multi-domain** (financial analysis, engineering design): Hierarchical Task Network (HTN). Decompose into sub-goals with separate planning processes for each domain.

**2. Use a capable model to plan, a cheap model to execute.** The Plan-and-Execute pattern's primary production advantage is this separation. A frontier model (o1, Claude 3.7, GPT-4.5) generates the plan; a smaller, faster model executes individual steps. This combination achieves up to 90% cost reduction compared to running everything through the frontier model. LangChain's benchmarks confirm that smaller models in the execution layer match larger models when given well-scoped, pre-planned steps.

**3. Implement plan validation before execution.** Don't execute a plan the agent generated without a sanity check. Validation includes: verifying step dependencies are satisfied, checking that prerequisites are met (file exists, API accessible, data loaded), and confirming the plan's final state matches the user's goal. This is the primary mechanism to prevent analysis paralysis from becoming a correctness failure — the plan gets reviewed and corrected at low cost before execution begins.

**4. Use hierarchical decomposition for tasks that span multiple domains.** HTN planning — originally from classical AI, now being applied to LLM agents — decomposes a goal into a tree of sub-tasks, each with its own planning process. Critically, a sub-task's failure can be recovered locally (replan just that branch) without invalidating the entire plan. This is the key advantage over flat linear plans where a step failure cascades.

**5. Add bounded stopping rules.** Without explicit limits, agents either loop forever or give up too early. Set: maximum plan length, maximum execution iterations per step, maximum total cost per task, and a minimum quality threshold for plan acceptance.

**6. Expose the plan to humans as a review point.** When the task has irreversible consequences (sending emails, modifying production systems, deleting data), the plan should be surfaced for human review before execution begins. Plan-then-Execute makes this trivially easy; ReAct makes it structurally awkward.

## Evidence

- **LangChain benchmarking study (Feb 2025):** Tested ReAct agents across tool counts and context sizes. Found that both more context and more tools degrade performance, and that agents with longer trajectory requirements degrade more quickly. Also found that o1, o3-mini, and claude-3.5-sonnet perform comparably in a different league than gpt-4o and llama-3.3-70B for agentic tasks. — [LangChain Blog](https://www.langchain.com/blog/react-agent-benchmarking)
- **Zylos Research, "Long-Running AI Agents" (Jan 2026):** Tracked 2-hour autonomous tasks across production deployments. Found that task duration doubles every 7 months, but doubling task duration quadruples failure rate. The Planner-Worker pattern enables up to 90% cost reduction on long-horizon tasks by using capable models for planning and cheap models for execution. — [Zylos Research](https://zylos.ai/en/research/2026-01-16-long-running-ai-agents/)
- **arXiv:2605.07707 (May 2026):** Applied Hierarchical Task Network planning to LLM agents. Found that HTN decomposition enables localized replanning — when a sub-task fails, only that branch replans — which is significantly more robust than flat plan recovery. — [arXiv](https://arxiv.org/html/2605.07707v1)
- **Gravity AI, "Planning vs Execution" (Jun 2026):** Formalized the cognitive architecture split between planning and execution. Key finding: splitting them saves money because you reason expensively once to make the plan, then execute steps cheaply. Also identified replanning as the primary safety mechanism — when the world changes mid-execution, the agent should regenerate the plan from the current state, not continue on a stale path. — [Gravity AI](https://gravity.fast/blog/ai-agent-planning-vs-execution/)
- **DEV.to practical comparison (Nov 2024):** Benchmarked ReAct, Plan-and-Execute, and Reflexion patterns on data analysis tasks. Found: ReAct is fastest/cheapest but plateaus on tasks needing verification; Reflection achieves 91% pass@1 on HumanEval but burns 3–5x more tokens; Plan-and-Execute is most token-efficient on predictable multi-step workflows. — [DEV.to](https://dev.to/jamesli/react-vs-plan-and-execute-a-practical-comparison-of-llm-agent-patterns-4gh9)

## Gotchas

- **Don't default to ReAct for everything because it's the simplest pattern.** The simplicity of the reasoning-acting loop is seductive, but it causes context bloat and redundant re-reasoning on tasks where the plan is likely correct. LangChain's data shows performance degrades significantly with trajectory length.
- **A plan generated with stale context will fail in execution.** If the world changed between planning and execution (data updated, API changed, file moved), the plan is wrong. Build in a "replan trigger" — a check before executing each major step that asks whether the current world state still matches the plan's assumptions.
- **Tool choice overload kills planning agents.** A Plan-then-Execute agent with 50 tools in scope will generate plans that are fragile and context-heavy. Keep the tool set scoped per execution step; let the planner call sub-planners for domains outside its core competency.
- **Analysis paralysis is a prompting problem, not a model problem.** Agents that over-deliberate usually received vague success criteria. Explicit step limits, budget constraints, and minimum viable outputs prevent infinite deliberation without changing the model's behavior.
