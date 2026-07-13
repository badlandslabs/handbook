# S-1061 · The Generator-Evaluator Stack: When Your Agent Runs Too Long and Loses the Plot

A single agent working on a complex task for more than a few minutes does not simply slow down — it degrades. Models running long-horizon tasks exhibit two distinct failure modes that single-agent loops cannot fix: context window degradation (coherence collapses as context fills) and context anxiety (the model prematurely wraps up work when it senses context limits approaching). When you need an agent to produce quality work over a multi-hour run — writing a full-stack application, reviewing a legal contract, conducting multi-document research — a single-agent loop is not the right architecture. You need two agents in tension.

## Forces

- **Context degradation is structural, not a prompting problem.** Adding more instructions or better system prompts does not fix a model that has lost coherence after 100+ tool calls. The issue is how context accumulates, not what the prompt says.
- **Separation of concerns applies to agents, not just code.** The agent doing the work and the agent judging the work have different goals and should not be the same system prompt. Self-evaluation consistently underperforms independent evaluation.
- **The right architecture for a 5-minute task and a 5-hour task are completely different.** Teams that build a multi-agent supervisor for a simple demo discover they didn't need it. Teams that build a single loop for a complex task discover they needed something they didn't build.
- **Fan-out parallelism cuts latency 3×** (parallel execution of independent sub-tasks reduces wall-clock time from 60s to ~20s), but fan-out amplifies failure blast radius — one bad agent pollutes the aggregate result.

## The Move

The Generator-Evaluator harness, adapted from Generative Adversarial Networks (GANs) by Anthropic engineer Prithvi Rajasekaran, separates output generation from output evaluation into two distinct agent roles connected by a feedback loop:

- **Generator agent** — does the work. Produces code, text, analysis, or decisions. Receives structured feedback from the evaluator and revises. Has no visibility into the grading criteria.
- **Evaluator agent** — judges the work. Operates with full knowledge of the grading rubric. Navigates the live output (e.g., via Playwright MCP to visit a running app) and grades against concrete criteria. Feeds back what specifically failed.
- **Feedback loop** — Generator revises → Evaluator re-grades → repeat until passing score or hard round limit.

The key engineering decisions:

- **Grading criteria are the durable IP.** The teams that get the most from this pattern develop precise, measurable rubric dimensions (e.g., design quality, originality, craft, functionality — not "looks good") before wiring the harness. Teams that skip this wire the harness as a checkbox and discover their evaluator has approved mediocre work for a week.
- **Context resets between rounds.** Each Generator-Evaluator cycle starts with a fresh context window. The previous attempt's accumulated state is summarized and passed as structured input, not appended. This directly addresses context window degradation.
- **Hard round limits prevent infinite loops.** Set a maximum iteration count (Anthropic's example produced a working DAW application in ~4 hours at $124 token cost with an unspecified but finite round count). Teams without limits discover runaway costs the hard way.
- **Human-in-the-loop at boundaries.** For high-stakes outputs, the Evaluator's verdict gates a human approval step before the Generator continues. Anthropic applies this to Claude Cowork (customer-facing sends require human approval); the same trust boundary applies to any agent producing irreversible outputs.

Supporting patterns that compose with Generator-Evaluator:

- **Supervisor pattern** — a single orchestrator agent receives requests, decomposes tasks, routes to specialists (research agent, writing agent, code agent), collects results, and assembles final output. Used by LangGraph's canonical supervisor implementation at Uber, LinkedIn, and Klarna.
- **Parallel fan-out** — for tasks with independent sub-tasks (e.g., analyzing 50 documents), route each to a separate agent instance running concurrently. Reduces wall-clock latency from serialized O(n) to parallel O(1). The evaluator then aggregates.
- **Difficulty-aware routing** — a lightweight classifier estimates query complexity before committing to a pipeline depth. Simple queries go through a shallow chain; complex queries route to the full Generator-Evaluator loop. Delivers cost reductions without accuracy loss.

## Evidence

- **Anthropic Engineering Blog:** "Harness design for long-running application development" — describes the Generator-Evaluator architecture applied to frontend design (subjective quality) and full-stack autonomous coding (verifiable correctness), producing a working DAW application in ~4 hours and ~$124 in token costs — [https://www.anthropic.com/engineering/harness-design-long-running-apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- **LangChain Blog:** "Building LangGraph: Designing an Agent Runtime from first principles" — describes LangGraph's graph-based execution model (Pregel/BSP-inspired, typed state, explicit cycles), used in production at LinkedIn, Uber, and Klarna. Key quote: "We aimed to find the right abstraction for AI agents, and decided that was little to no abstraction at all. Instead, we focused on control and durability." — [https://www.langchain.com/blog/building-langgraph](https://www.langchain.com/blog/building-langgraph)
- **Jobsbyculture.com:** "AI Agent Orchestration Patterns" (May 2026) — documents six production-proven orchestration patterns with specific failure modes: 94% of production failures stem from 3 root causes (silent loops, cascading hallucinations, context overflow). Parallel fan-out delivers 3× latency reduction in production — [https://jobsbyculture.com/blog/ai-agent-orchestration-patterns-2026](https://jobsbyculture.com/blog/ai-agent-orchestration-patterns-2026)

## Gotchas

- **Wire the rubric before the harness.** Most teams implement the loop and defer the grading criteria. The rubric is the hard creative and organizational work. Without it, the evaluator has no coherent target and defaults to rubber-stamping.
- **Evaluator bias is a real failure mode.** If the evaluator consistently favors one model's style or confidence level, the debate produces higher-confidence wrong answers, not better answers. Use diverse judges or human calibration to prevent systematic bias from metastasizing.
- **Fan-out amplifies blast radius.** Each parallel branch can fail independently. Without per-branch retry policies, timeout budgets, and dead-letter queues, a single failing branch hangs the entire workflow. Implement chaos testing (simulate worker crashes, slow networks, corrupted messages) before production.
- **State persistence across handoffs is the most common production failure point.** The architectural decision that causes the most incidents in supervisor agent systems is how state persists across agent handoffs. Supervisor holds no in-memory state; reload context from store on every request. Use PostgreSQL or Redis for checkpointing so pods survive restarts without losing in-flight work.
- **Context resets are lossy.** Summarizing previous rounds into a context for the next round discards nuance. If your task requires tracking subtle state across iterations (e.g., evolving a codebase feature across 20 rounds of evaluation), use a vector store or structured log rather than a text summary as the inter-round handoff mechanism.
