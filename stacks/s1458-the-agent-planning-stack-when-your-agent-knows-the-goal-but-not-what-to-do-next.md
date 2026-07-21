# S-1458 · The Agent Planning Stack — When Your Agent Knows the Goal But Not What to Do Next

Your agent gets a complex task — write the report, fix the bug, book the trip. It responds fast and confidently. Then you check the output and find it stopped halfway, drifted from the actual goal, or confidently produced something that was plausible but wrong. The model wasn't the problem. The agent had no plan.

## Forces

- **Reasoning degrades over distance.** A 5-step task and a 20-step task don't just require more steps — the agent's coherence about what it's doing decays with each additional hop. Without explicit planning, longer tasks reliably produce drift, loops, and half-finished work.
- **Different task shapes need different planning strategies.** Sequential dependency, branching alternatives, and failure-prone environments each call for different architectures. Teams default to one approach (usually ReAct) and apply it everywhere, missing the cases where it costs them.
- **Planning has a cost.** Explicit planning adds LLM calls, token consumption, and latency. Choosing the right planning strategy is also an efficiency decision.
- **Most benchmarks don't predict real-world planning quality.** High MMLU or HumanEval scores do not predict WebArena or SWE-bench performance. Planning capability is a distinct capability from raw model performance that requires its own evaluation.

## The Move

Match the planning architecture to the task shape. Five patterns cover most cases:

**Chain-of-Thought (CoT)** — The baseline. Append "think step by step" and let the model trace its own reasoning before acting. Right starting point for everything; not sufficient alone for tasks over ~8 steps or with branching.

**ReAct (Reason + Act)** — Tight coupling of reasoning and tool use. The agent alternates: reason about what to do → call a tool → observe the result → reason about what comes next. Best for interactive tasks where the environment responds: browser agents, API interactions, code execution. Failure mode: reasoning drift — the model reasons itself into a wrong assumption and doubles down.

**Plan-and-Execute** — Hierarchical decomposition. A planner model first breaks the goal into steps, then an executor model runs them. Separates "what's the plan" from "do the work." Best for complex, multi-step workflows where the full plan is knowable upfront. Avoid when the environment is unpredictable — a rigid plan becomes a liability when conditions change mid-execution.

**Tree of Thoughts (ToT)** — Exploratory branching. Generate multiple candidate reasoning paths, evaluate each with a scorer, keep the top-k, repeat. Best for tasks where multiple approaches are plausible and evaluation can discriminate among them (e.g., strategic decisions, creative constraints, optimization problems). Cost compounds fast — each branch is a separate LLM call.

**Reflexion** — Learning from failure across trials. After a failed attempt, the agent critiques its own performance using natural language feedback, stores the insight in persistent memory, and applies it on the next run. Best for iterative environments (code debugging, writing drafts, test-and-revise workflows). Very high cost — multiple trials × multiple calls per trial.

**Verification checkpointing** — A universal overlay to any planning strategy. After each significant step, the agent asks "did this step actually work?" and verifies output before proceeding. An agent that plans without verifying is a driver who never checks mirrors.

## Evidence

- **Engineering blog:** Laxaar Engineering documented that planning technique is as important as model choice. They identified three signals that planning is needed: tasks over 8 steps, tasks where one action affects subsequent ones, and tasks where incorrect intermediate steps are costly or irreversible. Their conclusion: "An agent without a planning strategy is just an LLM with tools." — [Laxaar Engineering, "Agent Planning Techniques for Reliable Execution"](https://laxaar.com/blog/agent-planning-techniques-1748650000006), May 2026

- **Practitioner reference:** AgentEngineering.org formalized the distinction between planning (choosing where to go next) and task decomposition (choosing the size and shape of work units). Their framework maps planning failures to: missing dependency awareness, lack of verification gates, and absence of re-planning triggers. — [AgentEngineering.org, "Planning and Task Decomposition"](https://agentengineering.org/articles/planning-and-task-decomposition), March 2026

- **Community survey:** AI Study Room compared all four frameworks across axes of cost, complexity, and task fit. Their practitioner takeaway: use ReAct for execution, Plan-and-Execute for structure, ToT for exploration, and Reflexion for improvement — and combine them in a single agent. — [AI Study Room, "Agent Planning Frameworks"](https://aidev.fit/en/ai/agent-planning.html), February 2026

- **Benchmark failure analysis:** UC Berkeley researchers (Wang et al.) demonstrated that automated agents can achieve near-perfect scores on SWE-bench, Terminal-Bench, and other agent benchmarks via exploit strategies — pytest hooks, binary wrapper trojans, container parser overwrites — without solving a single actual task. The finding underscores that benchmark scores do not measure genuine planning or task completion ability. — [UC Berkeley RDI, "How We Broke Top AI Agent Benchmarks"](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont), April 2026

## Gotchas

- **ReAct is not the universal default.** Most agent frameworks ship ReAct as the default, and teams leave it there for every task type. ReAct excels at reactive tool use but poorly at tasks requiring upfront decomposition or exploration of alternatives.
- **Plan-and-Execute plans become stale.** If a step fails in Plan-and-Execute, the remaining plan is often invalid. Always wire in a re-planning trigger on failure — re-decompose from the current state, not from the original plan.
- **Tree of Thoughts cost is non-linear.** Each expansion level multiplies LLM calls. Set explicit depth limits and early-exit conditions before starting.
- **Verification is the most-skipped step.** Teams implement planning but forget verification, so the agent confidently proceeds from failed intermediate steps. A 1-call verification check (schema check, existence check, smoke test) after each significant step catches the majority of downstream failures.
- **Benchmarks measure exploitability, not planning quality.** SWE-bench Verified scores can be gamed via test-hook exploits. Real-world planning quality requires custom eval sets grounded in actual task traces, not leaderboard rankings.
