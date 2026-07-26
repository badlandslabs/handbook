# S-1688 · The Orchestration Decision Stack — When One Agent Is Not Enough but Five Are Too Many

You have a multi-step task. The LLM chains work in demos. Then production hits: an intermediate step produces a malformed output, two agents step on each other, the workflow crashes with no way to resume, and nobody can trace what happened because the chain lives in a Python loop with print statements. The question isn't whether to use orchestration — it's how to choose the right orchestration model for your actual problem, and when the answer is "don't."

## Forces

- **LLM output is non-deterministic — and so is everything downstream.** A classification error at step 2 compounds through steps 3–8. The more agents in a chain, the more the error surface grows. Sequential pipelines amplify noise.
- **Formal orchestration adds upfront complexity that feels like over-engineering until production day.** State machines, checkpointing, and DAG definitions cost real engineering time. Teams resist until they lose a Friday to debugging a 6-hour workflow that crashed at step 47 with no resume.
- **The agent capability ceiling is real but hard to measure.** A single agent can handle ~3 tool calls coherently before context degradation. Beyond that, specialization pays off. But "beyond that" varies wildly by model, task type, and prompt quality.
- **Framework choice is sticky.** Switching from CrewAI to LangGraph mid-project costs weeks. Defaulting to LangGraph for every project is over-engineering for a 2-agent prototype. Choosing the right model upfront prevents painful rewrites.

## The move

The field has converged on four distinct orchestration models — each optimized for different complexity thresholds:

**Model 1: Sequential / Prompt Chaining**
Chains LLM calls in a fixed linear order. Each step's output becomes the next step's input.
- Use when: workflow steps are fixed, deterministic, and the domain is well-bounded. One step must complete before the next begins.
- Stack: bare LLM API + Python loop, or LangChain LCEL chains.
- Limit: Do not call this "orchestration" if you're doing it in a for-loop. Real orchestration implies state, error handling, and visibility — even in sequential flows.

**Model 2: Stateful Graph / State Machine**
Workflows modeled as graphs with explicit nodes (agents/tools), edges (transitions), and state. Supports branching, conditional routing, and checkpointed resume.
- Use when: you need branching logic (different next steps based on classification, confidence, or tool output), crash-safe resume, or human-in-the-loop approvals.
- Stack: LangGraph (graph-based state machine with checkpointing) or Temporal (durable execution for long-running workflows).
- Key feature: checkpoint/rollback — if a step fails, resume from the last checkpoint without re-executing completed steps.

**Model 3: Role-Based Team**
Agents assigned explicit roles with goals, tools, and autonomy. Agents delegate to each other based on role boundaries.
- Use when: you have distinct domain expertise areas (researcher, writer, reviewer) and want agents to collaborate autonomously.
- Stack: CrewAI (fastest path from idea to working team), LangGraph supervisor pattern, or OpenAI Swarm.
- Key feature: natural handoff — roles delegate without explicit routing logic.

**Model 4: Event-Driven Fan-Out / Fan-In**
Tasks dispatched to multiple agents in parallel, results collected, then merged for a final synthesis step.
- Use when: the task decomposes into independent subtasks that can run concurrently (e.g., parallel research across N sources, N product reviews, N code reviews).
- Stack: LangGraph's Send API, Temporal workflows with activity fan-out, or custom event bus (Kafka + A2A + MCP).
- Key feature: linear cost reduction — N parallel branches at roughly the cost of one sequential step.

**The decision matrix:**

| Condition | Recommended Model |
|-----------|-------------------|
| Fixed pipeline, < 3 steps | Sequential (no framework needed) |
| Branching, resume, or approvals needed | Stateful graph (LangGraph) |
| Long-running workflow, durability needed | Temporal |
| Distinct expert roles, natural delegation | Role-based team (CrewAI) |
| Independent parallel subtasks | Event-driven fan-out |
| Complex multi-dimension problem | Combine: role-based team → graph state machine → fan-out |

**GitHub's Mission Control pattern** (Dec 2025): orchestrating multiple agents as workers — assign tasks, stream logs, steer mid-run, pause and refine — represents the mental model shift from "call and wait" to "assign and monitor." This maps to Model 2 or 4 with active human oversight.

## Evidence

- **Anthropic engineering blog (Dec 2024):** "The most successful implementations use simple, composable patterns rather than complex frameworks." Distinguishes "workflows" (predefined code paths, predictable, consistent) from "agents" (dynamically directed, flexible, best in open-ended domains). Recommends starting with a single LLM call and adding complexity only when the problem demands it. — [URL](https://www.anthropic.com/engineering/building-effective-agents)

- **Microsoft Multi-Agent Reference Architecture (2026):** Framework for orchestrating, governing, and scaling systems where multiple specialized agents interact. Explicit focus on governance as a first-class concern alongside capability. GitHub: microsoft/multi-agent-reference-architecture. — [URL](https://microsoft.github.io/multi-agent-reference-architecture/index.html)

- **Databricks State of AI Agents report (Q4 2025):** Multi-agent workflows grew 327% between June and October 2025. Technology companies building multi-agent systems at 4× the rate of other industries. Over 126,000 GitHub stars across major orchestration frameworks. — [URL](https://mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide)

- **Zylos Research (Apr 2026):** Three architectural schools have crystallized: DAG-based (LangGraph, Temporal, Dagster), event-driven (Kafka + A2A + MCP), and actor model (AutoGen/MAF, Akka, Elixir/OTP). "By 2025, ad-hoc agent chaining had collapsed under its own complexity." — [URL](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)

- **r/LangChain and r/LocalLLaMA consensus (2026):** "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." Framework comparison data shows teams that defaulted to LangGraph avoided 6-12 months of painful rewrites. — [URL](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026)

- **GitHub Blog / Mission Control (Dec 2025):** Unified interface for managing Copilot coding agents across repositories: assign tasks, watch real-time session logs, steer mid-run (pause, refine, restart), jump into resulting pull requests. Represents shift from sequential to parallel agent workflow management. — [URL](https://github.blog/ai-and-ml/github-copilot/how-to-orchestrate-agents-using-mission-control)

- **Production case study — ruegreen/llm-agent-orchestration-architecture (Feb 2026):** Enterprise on-premises multi-agent stack on GPU hardware. Dual agent modes (simple chat vs full tool-use), FastAPI REST API, MCP for enterprise tools, health monitoring, and per-request rate limiting. — [URL](https://github.com/ruegreen/llm-agent-orchestration-architecture)

## Gotchas

- **Don't call it orchestration if it's a for-loop.** If you can solve it with a single LLM call + retrieval, do that. Real orchestration adds state, error handling, and observability — use it when the problem demands those, not preemptively.
- **CrewAI → LangGraph migration is painful.** CrewAI is excellent for demos and prototypes. Teams that ship with CrewAI and later need branching, checkpointing, or crash-safe resume discover that migration is non-trivial. Default to LangGraph if you anticipate needing any of those features within 90 days.
- **Over-agent is the new over-engineering.** The most common new mistake in 2025–2026 is building a 5-agent team when a 2-agent team with a better prompt would outperform it. More agents means more coordination overhead, more failure modes, and more cost — measure whether the specialization gain justifies it.
- **Framework choice is load-bearing.** LangGraph, CrewAI, AutoGen, and Temporal have fundamentally different mental models (state machines, role-based teams, conversations, durable execution). Switching costs weeks. Choose based on the complexity of your workflow, not the popularity of the framework.
- **Checkpointing is not optional for long-running workflows.** A workflow that cannot resume after a deploy or crash is not production-ready — it's a demo with extra steps. LangGraph checkpointing or Temporal's durable execution handles this. Without it, a 6-hour workflow failure costs the entire run.
