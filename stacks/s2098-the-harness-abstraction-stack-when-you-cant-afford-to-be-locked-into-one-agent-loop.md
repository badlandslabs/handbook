# S-2098 · The Harness Abstraction Stack — When You Can't Afford to Be Locked Into One Agent Loop

You're evaluating agent frameworks. LangGraph looks production-ready. AutoGen feels fast for prototyping. Claude Code is powerful but expensive. Omnigent promises to run them all. And YC just open-sourced QM — a company-wide multiplayer harness. The problem isn't finding a framework. The problem is that agent runtimes are multiplying faster than your team's ability to evaluate them, and committing to one locks you out of the others. The real question is: should you abstract the harness layer itself?

## Forces

- **Agent runtimes are proliferating with no clear winner.** Claude Code, Codex, Cursor, Pi, OpenCode, and custom agents each have different strengths, costs, and operational characteristics. No single runtime dominates all use cases.
- **Harness code becomes legacy fast.** The code you write to drive an agent — tool definitions, state management, retry logic, output parsing — is substantial. Switching runtimes means rewriting it.
- **The orchestration problem is separate from the agent problem.** How you chain agents, manage state, handle failures, and route tasks is independent of which agent runtime executes each step. These concerns should be decoupled.
- **Company-wide vs. personal agent is a real fork.** Most frameworks target individuals. YC's QM is explicitly designed for teams — per-person scopes, shared rooms, and isolated workspaces. This is a different product category with different requirements.

## The move

The core move: **separate the harness (agent runtime) from the orchestration layer (workflow logic), and treat the harness as a swappable dependency.**

- **Define agents in config, not code.** YAML or JSON agent definitions that specify the runtime, model, tools, and policies — keeping harness-specific details out of your workflow logic.
- **Build your orchestration graph against an abstract interface.** Whether you use LangGraph, Temporal, or custom state machines, the nodes in your graph should call an abstract `AgentExecutor`, not a concrete `ClaudeCodeExecutor`. The interface stays the same; the implementation swaps.
- **Use multi-agent sessions for cross-functional workflows.** Omnigent's model — multiple agents reviewing each other's work, splitting tasks across specialized runtimes — is the production pattern. One agent gathers research, another writes code, a third reviews. They're different harnesses running the same policy layer.
- **Choose your orchestration framework based on state management, not agent support.** LangGraph wins on checkpointing and human-in-the-loop breakpoints. Temporal wins on durable execution and crash recovery. AutoGen wins on rapid multi-agent conversational prototyping. The agent runtime you plug into them is secondary.
- **For company-wide deployments, scope matters more than framework.** YC's QM solves the scoping problem: per-person workspaces so one employee's agent doesn't affect another's, shared rooms for team collaboration, and a shared memory layer so multi-agent coordination isn't an afterthought.
- **Real-time session sync across devices** is the production UX pattern emerging from Omnigent. Start a session in terminal → continue in browser → finish on mobile. The session state (messages, sub-agents, terminal output) stays synchronized.

## Evidence

- **GitHub README:** Omnigent — an open-source meta-harness (8,069 ★) that unifies Claude Code, Codex, Cursor, Pi, and custom agents under a single orchestration layer with policy enforcement, sandboxing, and cross-device session sync. Agents are defined in YAML; workflow logic is harness-agnostic. — [https://github.com/omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent)
- **GitHub README:** YC's QM — multiplayer agent harness (8,291 ★, MIT license) built for startups. Employees get isolated per-person workspaces plus shared channels and projects. Used across YC's own accounting, legal, events, and engineering. YC built QM using QM itself. — [https://github.com/yc-software/qm](https://github.com/yc-software/qm)
- **HN Ask:** Production teams scaling agents in Python/k8s environments recommend LangGraph as the orchestration layer, citing checkpointing and human-in-the-loop breakpoints as the decisive features over Temporal or custom queues. One respondent: *"People complain a lot about LangChain, but the general vibe around LangGraph is that it's a maturely designed framework."* — [https://news.mcan.sh/item/44909029](https://news.mcan.sh/item/44909029)

## Gotchas

- **Abstraction layers leak.** Tool schemas, tool call formats, and output parsing differ enough between runtimes that the abstract interface will need conditional handling. Define the abstraction at the level of workflow state transitions, not at the level of individual tool definitions.
- **Harness choice affects cost significantly.** Claude Code and Codex are expensive per-token. Pi and OpenCode are open-source. A routing policy that sends simple tasks to cheap agents and complex tasks to capable ones requires the abstraction to support model routing — not all harnesses expose this uniformly.
- **Checkpointing strategies vary by back-end.** LangGraph supports MemorySaver, SQLite, PostgreSQL, and Redis checkpointer back-ends. Your choice affects whether you can replay agent sessions, how long state is retained, and whether cross-device sync is feasible. Choose the back-end before choosing the harness.
