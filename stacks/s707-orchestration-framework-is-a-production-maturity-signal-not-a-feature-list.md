# S-707 · The Orchestration Framework Is a Production-Maturity Signal, Not a Feature List

[Every team picks an orchestration framework by comparing features. They pull up a comparison table, note that CrewAI has nice role-based agents, that LangGraph has state machines, that AutoGen has human-in-the-loop — and they pick the one that seems most capable. Six months later they either can't ship because they over-architected, or they can't debug because the "simple" framework obscures what's happening. The real question isn't "which framework has the best features" — it's "where is my team in the production-maturity curve, and which framework matches that stage."]

## Forces

- **Feature comparisons miss the real trade-off.** LangGraph, CrewAI, and AutoGen are not competing on features — they're competing on the mental model they impose, and that model either accelerates or fights your team's current stage.
- **Demo-grade and production-grade are different problems.** A framework that ships a stunning demo can actively obstruct production reliability. CrewAI's agent-as-team-role abstraction is fast to scaffold but obscures control flow in ways that make debugging multi-step failures painful. LangGraph's graph model is harder to set up but gives you traversal-level observability.
- **Framework switching has a compounding cost.** Once you've structured your agents, prompts, and tool definitions around one mental model, migrating is not just "changing imports" — it's re-architecting state management and rewriting half your prompts. Pick the stage-appropriate framework the first time.
- **The "start simple" principle is the most violated in multi-agent.** Data-Gate's production lessons document it explicitly: teams over-engineer from day one, spending months debugging agent coordination instead of solving user problems. Multi-agent adds 2x cost, 3x latency, and 5x debugging complexity. You pay all of that on day one if you decompose too early.

## The Move

Map your team stage to the right orchestration mental model. The selection criteria are: how fast do you need to ship, how complex is the workflow, and what happens when it breaks in production.

- **Ship a demo this week → CrewAI.** Role-based team abstraction gets you a working multi-agent in hours. Agents are roles, delegation is ` Crew().kickoff()`. The gap: control flow is implicit inside the LLM's routing decisions, which makes step-level debugging nearly impossible for complex flows.
- **Run in production next month → LangGraph.** Graph-based state machines give you explicit control flow, checkpointing, and LangSmith's time-travel debugging. The cost: you write the graph topology yourself. Worth it when a broken agent means a broken user workflow.
- **Complex multi-agent reasoning with human-in-the-loop → AutoGen.** Conversation-based orchestration where agents negotiate tasks. Built-in group chat with human as participant. The cost: the conversation model can produce non-deterministic agent loops if the termination conditions aren't tight.
- **Avoid a framework entirely → Raw Claude API + tool use.** For linear, well-scoped tasks with clear success criteria. The control is pure code. The gap: you own all state management, retry logic, and observability from scratch.

The framework choice is also an indicator of what problem you're actually solving:

| Your problem | Framework signal |
|---|---|
| Can't get agents to coordinate | You probably need one agent with better tools, not two agents |
| Can't debug what the agent did | You need LangGraph's checkpointing, not more agents |
| Human needs to steer mid-flow | You need AutoGen's group chat, not a supervisor agent |
| Shipping a PoC to investors | CrewAI's team visualization is the right tool for that job |

## Evidence

- **Blog post (Technspire, Dec 2025):** The four categories that shipped from pilot to production in 2025 were developer tooling, internal ops automation, research/analysis, and customer support augmentation — all narrow, well-scoped domains. Twelve months of deployment data showed the teams that shipped started with a single agent handling the core workflow end-to-end, then decomposed only after establishing baseline reliability. — [technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons)
- **HN post (phil, 2025):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — The observation that orchestration, sandboxing, and tool integration are stratifying into independent concerns, each with different defensibility profiles. — [news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **GitHub decision guide (@agentsthink, Apr 2026):** Decision matrix: "Ship a demo this week → CrewAI. Run in production next month → LangGraph. Complex multi-agent reasoning → AutoGen. Avoid a framework entirely → Raw Claude API + tool use." — [github.com/benconally/ai-agent-framework-decision-guide](https://github.com/benconally/ai-agent-framework-decision-guide)

## Gotchas

- **CrewAI's simplicity is a trap at scale.** The role-based abstraction works beautifully for 2-3 agents. At 5+, the implicit delegation routing becomes a black box. Teams hit this around month two and then attempt a migration to LangGraph under production load — the worst possible time.
- **LangGraph's graph is not your workflow.** Writing a LangGraph graph is programming. If your team is expecting a "declare agents and go" experience, LangGraph will feel like over-engineering. It's not — but the onboarding tax is real and should be accounted for in the timeline.
- **AutoGen's conversation model is non-deterministic by design.** Group chat agents can generate loops where agents re-delegate to each other indefinitely. You need explicit termination conditions (max turns, explicit stop messages) before going to production. Teams that skip this get runaway agent loops that burn through tokens fast.
- **Framework lock-in is real.** LangSmith tracing is designed around LangChain/LangGraph workflows — it doesn't translate smoothly to CrewAI or custom orchestrators. If observability is critical and you're framework-agnostic, Braintrust (13+ framework integrations) or Phoenix (open-source) may be the better observability layer regardless of orchestration choice.
