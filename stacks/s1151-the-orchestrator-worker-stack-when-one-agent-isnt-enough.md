# S-1151 · The Orchestrator-Worker Stack — When One Agent Isn't Enough

A single agent works fine for "summarize this email" and "rewrite this paragraph." It falls apart the moment a task has independent sub-problems that can run in parallel — like researching 65 companies, checking 40 documents, or validating data across 3 systems simultaneously. Sequential processing burns time you don't have to spend.

## Forces

- **Token cost vs. capability tradeoff.** Multi-agent beats single-agent by 90.2% on hard tasks (Anthropic, June 2025) but costs ~15× the tokens. The question isn't "more agents = better" — it's whether the task value clears the token tax.
- **57% of AI project failures trace to orchestration design, not model weakness** (Anthropic analysis of 200+ enterprise deployments, April 2026). The individual models are fine; the coordination is broken.
- **Framework immaturity vs. production reliability.** LangGraph, CrewAI, AutoGen, and smolagents all solve different problems and none are universal. HN practitioners report rolling custom solutions because "0 framework out there that's good enough for serious work" (segmondy, HN comment, 2025).
- **Race conditions and infinite loops.** Multiple agents touching shared state without coordination produce non-deterministic failures — agent A overwrites agent B's output, or agents ping-pong between each other indefinitely.

## The move

The **orchestrator-worker pattern**: a lead agent plans and delegates; specialized workers execute in parallel and return structured results; the orchestrator synthesizes.

### Key implementation decisions

- **Give every subagent an explicit contract:** objective (what to accomplish), output format (how to return results), and context window (what it can and cannot do). Without all three, subagents wander off-task.
- **Run independent tasks in parallel, dependent tasks in sequence.** Research across N sources = parallel. Synthesis after research = sequential. Most orchestration bugs come from parallelizing things that need to be ordered.
- **Route by estimated difficulty.** Classify queries before committing pipeline depth. Simple queries (factual lookup, format conversion) get a single agent. Complex queries (multi-source research, analysis requiring cross-referencing) get the full orchestrator. Teams report 30–60% cost reduction from routing this way.
- **Use structured output schemas (Pydantic) for agent-to-agent data passing.** Don't pass freeform text between agents — pass typed objects. This makes failures explicit and traceable instead of silently drifting.
- **Persist orchestrator state to a durable store (Redis, Postgres, MongoDB) before each delegation step.** Multi-agent systems crash mid-execution; without checkpointing, you restart from zero.
- **Build a supervisor review step.** The orchestrator should validate worker outputs before synthesizing. Worker returns malformed data → re-call with corrective context, don't pass garbage downstream.

## Evidence

- **Anthropic engineering blog:** Their production multi-agent research system (Claude's Research feature) uses an orchestrator-worker architecture with parallel subagents searching web and enterprise sources simultaneously. Internal evals showed 90.2% improvement over single-agent Opus 4, at ~15× token cost. Key finding: token usage alone explained 80% of performance variance on BrowseComp — not prompt phrasing, not model rank. — [URL](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Hacker News Ask thread (11 comments):** Practitioners in production reported: custom Node.js + V8 isolates + MongoDB stacks, LangGraph with custom orchestrators, AGNO for its isolation and control plane design, and "Swirl" pattern with separate agent vs. session memory scopes. One respondent (segmondy): "There's absolute 0 framework out there that's good enough for serious work." Data passing between agents used JSON with MongoDB persistence, shared Postgres schemas, or in-memory state. — [URL](https://news.ycombinator.com/item?id=47660705)
- **Production validation (Fountain City Tech, May 2026):** Validated Anthropic's blueprint in real enterprise deployments. Confirmed the 90.2% / 15× numbers. Found that the four-part subagent contract (objective, output format, context window, review flag) was the most portable pattern — it survived contact with non-Anthropic stacks and different model families. — [URL](https://fountaincity.tech/resources/blog/anthropic-multi-agent-blueprint-production)

## Gotchas

- **Don't parallelize everything.** Two agents doing related work will produce redundant output. Use parallel only when sub-problems are independent — otherwise you pay the token tax twice and get conflicting results.
- **The orchestrator becomes the bottleneck.** If the lead agent is slow or the synthesis step is complex, parallel workers finish and sit idle waiting. Profile the orchestration overhead before assuming parallel is faster.
- **Context window pressure compounds across agents.** Each worker carries its own system prompt + context. A 200K context window sounds large but splits across 5 workers + orchestrator synthesis, you burn most of it on framing. Budget context per agent, not globally.
- **Supervisor-worker is not the same as supervisor-only.** A supervisor that only decides who does what (no workers executing) is a router, not an orchestrator. Real multi-agent value comes from parallel execution, not just delegation.
- **Benchmark ceilings don't reflect production reality.** Berkeley RDI broke 7 of 8 major agent benchmarks to ≥99% in April 2026 without solving a single real task. Any framework "SOTA" claim is conditional on already-exploited evals — measure against your own task distribution.
