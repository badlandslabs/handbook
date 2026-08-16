# S-2749 · The Magentic Orchestration Stack — When Your Agent Needs to Figure Out Its Own Plan

Your task is too complex for a fixed pipeline. You don't know the execution path in advance — the agent needs to decompose it, route to specialists, and adapt as it goes. Sequential chains break. Group chat creates noise. What you need is a managing agent with a shared ledger that decides who acts next.

## Forces

- **The problem shape is unknown at design time.** Sequential, concurrent, and handoff patterns all assume you know the workflow. Real-world tasks — "find the root cause of this production incident," "build a competitive analysis from scratch" — have emergent paths that only reveal themselves mid-execution.
- **Specialist agents are both necessary and dangerous.** Splitting agents by role (researcher, writer, editor) prevents context bloat and role blurring, but without a central coordinator, they duplicate work or hand off incorrectly.
- **Static orchestration can't handle iteration.** When an agent's output is wrong or incomplete, a fixed pipeline has no mechanism to loop back — it just passes bad output downstream.
- **The manager itself can fail.** A central coordinator is a single point of failure. If the manager misroutes or misses a task completion signal, the whole system stalls silently.

## The Move

Magentic orchestration (from Microsoft's Magentic-One system) uses a **managing agent** that dynamically decomposes tasks, selects specialist agents, tracks progress on a shared ledger, and determines when work is complete. Unlike sequential patterns where the path is fixed, the manager adapts in real time.

**How it works:**

- A **Magentic manager** maintains a shared working state (the ledger) visible to all agents — current progress, what's done, what remains, what's blocked.
- The manager dynamically decides which specialist to invoke next based on evolving context, not a predetermined sequence.
- Specialists operate in a sandboxed mode by default — they can use tools to query or modify external systems, but the manager controls handoffs.
- A **task ledger** (implemented as a shared data structure in Semantic Kernel or similar frameworks) tracks todos, completion status, and dependencies — preventing the "did we finish?" ambiguity that plagues loop-based agents.
- When a specialist returns, the manager evaluates: is the task complete? Should another specialist be invoked? Is more information needed? The loop continues until the manager signals done or hits a defined boundary (max iterations, cost limit, time limit).

**Key differentiators from other patterns:**

- **vs. Sequential:** Path is dynamic, not predetermined. Agents can be re-invoked in different orders.
- **vs. Concurrent:** There's still a coordinator — results aren't merged arbitrarily.
- **vs. Group Chat:** Read-only participants in group chat don't take actions in external systems. Magentic agents do.
- **vs. Handoff:** Handoff hands off control entirely. Magentic keeps the manager in the loop throughout.

## Evidence

- **Microsoft Research (primary):** Magentic-One paper describes the original system achieving "statistically competitive performance to state-of-the-art methods on GAIA and AssistantBench benchmarks" on open-ended web and file tasks. Uses an Orchestrator agent with a shared task ledger and specialized sub-agents (WebSurfer, FileSurfer, etc.). — [https://www.microsoft.com/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/](https://www.microsoft.com/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/)
- **Microsoft Learn / Azure Architecture Center:** Documents magentic orchestration as one of five core patterns alongside sequential, concurrent, group chat, and handoff. Explicitly frames it for "open-ended and complex problems that don't have a predetermined plan of approach." — [https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- **Azure AI Foundry practitioner post:** Demonstrates the five-pattern comparison in code on Azure AI Foundry, showing the manager's real-time decision loop and task ledger pattern in practice. — [https://www.azizjarrar.com/blog/azure-ai-foundry-multi-agent-orchestration-patterns](https://www.azizjarrar.com/blog/azure-ai-foundry-multi-agent-orchestration-patterns)

## Gotchas

- **The task ledger is the critical component — don't skip it.** Without an explicit shared ledger, the manager can't track what's done. Teams often implement the manager logic but forget the ledger, then wonder why the system redoes work or never terminates.
- **Manager routing quality is the ceiling of the whole system.** If the manager misclassifies a task or routes to the wrong specialist, the entire pipeline degrades. Invest in the manager's prompt and few-shot examples disproportionately.
- **Iteration limits are non-negotiable.** Open-ended tasks can loop indefinitely. Set hard boundaries on max turns, total cost, or time — and make the boundary behavior explicit (return what's done, signal failure, escalate to human).
- **Magentic orchestration is experimental in Semantic Kernel.** Microsoft marks it as pre-release. For production use, either build on the AutoGen Magentic-One reference implementation directly, or wait for stable APIs.
