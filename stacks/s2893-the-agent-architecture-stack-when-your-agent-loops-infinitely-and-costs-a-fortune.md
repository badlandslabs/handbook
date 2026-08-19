# S-2893 · The Agent Architecture Stack — When Your Agent Loops Infinitely and Costs a Fortune

You have a task that needs an agent. You know there are three dominant patterns — ReAct, Plan-and-Execute, and Graph Agents — and every framework defaults to one. But you don't know which one fits your workload, and choosing wrong means either a runaway loop that bills $47,000 before anyone notices, or a brittle pipeline that can't handle a wrong turn.

## Forces

- **ReAct and Plan-Execute are both right, for different workloads.** The architecture that handles a dynamic exploratory task will over-engineer a stable pipeline, and vice versa.
- **The step cap is not the hard problem.** Every developer adds `max_steps` and feels safe. The real failure is the verifier stall: a ReAct agent that calls the same tool with slightly different arguments 20 times because it has no memory of past failures.
- **Token cost is quadratic, not linear.** Eight to 30 steps per task, each resending the full context stack, means a 5K-token input balloons to 80K–200K tokens. A single SWE-Bench task averages $2.40. A misconfigured loop ran 11 days and billed $87,000 before detection.
- **Framework choice is secondary.** LangGraph, LlamaIndex, CrewAI, and custom Node.js stacks all appear in production. The pattern matters more than the framework.

## The Move

Match the orchestration pattern to the workload's dependency structure — not the model's capability.

**For deterministic multi-step pipelines** (stable inputs, known path):
→ Plan-and-Execute: generate the full plan upfront, hand each step to an executor. Replan only when the executor surfaces an unexpected observation. This is a DAG in disguise — you know the steps, you just want a planner to decompose them.

**For dynamic exploratory tasks** (next step genuinely depends on prior output):
→ ReAct: interleave reasoning and acting. The agent observes each result before choosing the next action. Critical safeguard: per-tool call cap in addition to a global step cap.

**For complex interdependent tasks** with branching or parallel sub-problems:
→ Graph Agents (LangGraph, AutoGen): explicit state machines or DAGs where edges encode dependencies. Enables fan-out/fan-in, parallel tool execution, and supervisor routing.

**The non-negotiable budget layer regardless of pattern:**
- Global `max_steps` (the floor — stops runaway loops)
- Per-tool call cap (stops the verifier stall)
- Per-task hard cost cap with hard enforcement, not alerts
- Token accounting per step: track cumulative context size and alert at thresholds
- Structured output schemas for all tool responses (prevents the "slightly different argument" failure)

## Evidence

- **HN Ask Thread (2026):** Practitioners shared real stacks: Node.js + MongoDB for custom stateful pipelines (Express endpoints in V8 isolates, JSON docs with pipeline IDs), LangGraph for DAG-based orchestration, raw Python for lightweight use cases. Key theme: observability is the most underinvested part — logging every run's input, output, token usage, and latency beats framework choice every time. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **DEV Community / dasroot.net (April 2026):** ReAct costs more per task (sequential re-sending of context at every step) but adapts to unexpected observations mid-execution. Plan-Execute front-loads planning for lower per-task cost but needs a re-planning trigger to recover from surprises. Graph Agents handle parallel fan-out efficiently but introduce orchestration overhead for simple linear tasks. — [dasroot.net/posts/2026/04/agent-architectures-react-plan-execute-graph-agents](https://dasroot.net/posts/2026/04/agent-architectures-react-plan-execute-graph-agents)
- **AnhTu.dev / Morph / MightyBot (2026):** AI agents consume 50–500× more tokens than basic RAG due to iterative loops resending full context. A Singapore fintech burned $87,000 in 11 days from a recursive self-invocation loop. Identical models and tasks can differ by 3×–10× in cost per decision depending on architecture. — [anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257), [mightybot.ai/blog/token-economics-of-ai-agents-2026](https://mightybot.ai/blog/token-economics-of-ai-agents-2026/)
- **Atlan / Agentika (2026):** ReAct is right when "the next step genuinely depends on what you learned" — web research, live data fetching, interactive debugging. Plan-and-Execute is right when "the task has a known shape but the steps are complex" — report generation, multi-document synthesis, multi-step API pipelines. — [atlan.com/know/ai-agent/react-vs-plan-and-execute-agent-architecture](https://atlan.com/know/ai-agent/react-vs-plan-and-execute-agent-architecture)

## Gotchas

- **The `max_steps` guard is necessary but not sufficient.** The verifier stall is a distinct failure: a ReAct agent calls `verify_result` twice, three times, twenty times with minor rewording — it has no memory of past failed verifications beyond the context window. Add per-tool call caps, not just a global step limit.
- **Framework defaults lie.** LangGraph's default examples use ReAct loops. If you want Plan-and-Execute you have to build it — it's not the path of least resistance. Know what your framework's mental model is before committing.
- **Multi-agent is not always better.** Token usage in multi-agent systems is 15× higher than chat interactions. Fan-out patterns multiply cost at every branching point. The orchestrator-with-isolated-subagents model (Anthropic/OpenAI/CrewAI's default) is the survivor because it limits agent count.
- **Prompt caching helps asymmetrically.** Cached input tokens bill at ~10% of base rate, but output tokens are never cached. Chatty architectures (high tool-call volume, long reflection loops) stay expensive even with perfect cache discipline.
- **The observability floor is minimal:** per-run input, output, token count, latency, step count, error. Anything less and you cannot diagnose why a run cost $12 instead of $0.40.
