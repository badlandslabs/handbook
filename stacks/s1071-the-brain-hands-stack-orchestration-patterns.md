# S-1071 · The Brain-Hands Stack: Decoupling Decision from Execution

You've built an agent that works in demos. Scale it to production and it either burns through tokens chasing irrelevant tool calls, or it one-shots the entire task at once and leaves half-finished work when context runs out. The fix isn't a smarter model — it's separating *what the agent decides* from *how it executes*.

## Forces

- Agents that control their own execution accumulate assumptions that go stale as models improve — every "the model can't do X so we add a harness rule" becomes dead weight
- One-shotting: agents attempt the entire task in a single context window, exhausting it mid-implementation with no recovery plan
- Premature victory: agents see existing progress, declare completion, and stop before finishing all sub-tasks
- Token costs spiral when agents receive every possible tool definition upfront rather than discovering tools on demand
- Framework choice (LangGraph, CrewAI, AutoGen) locks you into an orchestration model that may not match your production needs
- ~20% of multi-agent tasks fail on first attempt — you need a recovery strategy, not just a retry button

## The move

**Separate the brain (decision/planning) from the hands (execution/tools).** This is the pattern Anthropic describes as the core architectural shift behind their Managed Agents service, and it appears independently across multiple production deployments discussed on HN.

- **Virtualize execution.** The brain operates through stable interfaces that don't change when underlying tools or model capabilities evolve. When Claude Opus 4.5 removed "context anxiety" behaviors that Sonnet 4.5 needed, Anthropic's harness rules became no-ops — because the abstraction layer kept them decoupled.
- **Use on-demand tool discovery, not upfront definitions.** Anthropic's Tool Search Tool reduced token costs by 85% by letting the model discover tools at call time rather than receiving all 80+ tool definitions upfront. GitHub MCP alone costs ~26K tokens before any work begins.
- **Layer deterministic gates over probabilistic agents.** One HN practitioner describes the pattern: sequential plan → design → code stages, with deterministic checks (compile, lint) at each boundary plus agentic reviewers. The hard gates provide guarantees; the agentic gates provide flexibility. ~20% task failure is assumed — failed tasks are wiped and re-run, not patched.
- **Checkpoint long-horizon work with a scratchpad.** Agents working across multiple context windows need to record progress externally. The scratchpad survives context resets and lets the next session resume without reprocessing completed steps.
- **Route by difficulty.** Instead of running every query through a full multi-agent pipeline, use a classifier to estimate difficulty and allocate compute proportionally — shallow chain for simple queries, deep multi-agent pipeline for complex ones. Zylos Research reports significant cost reductions without accuracy loss.
- **Choose orchestration model by production need, not popularity.** LangGraph for stateful graph-based workflows with observability (Klarna, Replit, Elastic use this). CrewAI for rapid prototyping and role-based teams. AutoGen is in maintenance mode as of October 2025 — successor is Microsoft Agent Framework.

## Evidence

- **Anthropic Engineering — "Scaling Managed Agents" (Apr 8, 2026):** Core philosophy is decoupling the brain from the hands. "Harnesses encode assumptions that go stale as models improve. Managed Agents is built around interfaces that stay stable as harnesses change." Describes the Abstraction Layer pattern as the solution. — [URL](https://www.anthropic.com/engineering/managed-agents)
- **Anthropic Engineering — "Effective Harnesses for Long-Running Agents" (Nov 26, 2025):** Identifies two failure modes of agents operating across sessions: one-shotting (attempting everything at once) and premature victory (declaring done when seeing partial progress). Documents the scratchpad/checkpoint approach as mitigation. — [URL](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **Hacker News — "Multi-Agentic Software Development Is a Distributed Systems Problem" (2025, 119 points):** Practitioner describes verification gates combining deterministic checks + agentic reviewers. "You can't make the agent reliable on its own, but you can make the protocol reliable by checking at every boundary." Assumes ~20% task failure; retries via wipe-and-repeat. — [URL](https://news.ycombinator.com/item?id=47761625)
- **Anthropic Engineering — "Advanced Tool Use" (Nov 24, 2025):** Tool Search Tool achieves 85% token reduction vs upfront definition loading. Programmatic Tool Calling (code-based orchestration rather than model-generated tool calls) achieves 37% token reduction and 44% latency improvement. — [URL](https://www.anthropic.com/engineering/advanced-tool-use)
- **Zylos Research — "Agent Workflow Orchestration Patterns" (Apr 14, 2026):** Documents three patterns (DAG, Event-Driven, Actor Model), difficulty-aware dynamic routing, and federated orchestration. Reports significant cost reduction from routing by difficulty. — [URL](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)
- **JetThoughts — "LangGraph vs CrewAI vs AutoGen" (2025):** LangGraph in production at Klarna, Replit, Elastic. AutoGen entered maintenance mode Oct 2025. CrewAI at v0.98+ with active development. — [URL](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025/)

## Gotchas

- **Approval fatigue kills human-in-the-loop containment.** Anthropic measured ~93% approval rate for permission prompts — humans approve reflexively, defeating the safety purpose. Policy-based guardrails (OPA, structured constraints) enforce boundaries without requiring human attention.
- **"Framework agility" is a trap.** Plano's HN launch (Katanemo team) argues teams rebuild the same infrastructure concerns (model routing, observability, policy enforcement) inside every framework. The modular approach is a proxy/dataplane that stays constant across framework changes.
- **Scratchpad data must be machine-readable, not prose.** If the checkpoint summary is written as narrative, the next session wastes tokens re-parsing it. Structured formats (JSON, task lists, state machines) survive context resets better.
- **Difficulty routing classifiers add latency.** The classifier itself is a model call. The cost savings only materialize if the ratio of simple-to-complex queries is high enough to amortize the classifier overhead.
