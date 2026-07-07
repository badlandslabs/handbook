# S-752 · The Reliability Cliff — How Multi-Step Agents Go from 95% to 36% Success Rate

Every agentic system starts with a confident demo: the agent routes a query, calls a tool, generates a response, done. Then you ship it, and somewhere around step 4 or 8 you start seeing silent failures — wrong routes, hallucinated citations, duplicate API calls, responses that look right but aren't. The culprit is not bad code or weak models. It is arithmetic: compound probability on chained LLM steps. Teams that don't know the math ship systems that fail in ways they can't reproduce, can't debug, and can't explain to stakeholders.

## Forces

- **Reliability compounds multiplicatively, not additively.** A 95%-reliable single step sounds fine. Twenty chained steps: 0.95²⁰ = 35.8% end-to-end reliability. Every team that builds multi-step agents hits this wall — most don't see it coming because each individual step passes testing.
- **The failure is invisible during development.** Single-step tests pass. Two-step tests pass. Five-step tests start showing rare failures that get attributed to randomness. By the time you see the pattern in production, the architecture is entrenched.
- **Adding agents multiplies the surface area.** Each new agent adds its own step chain. A crew of 5 agents, each averaging 6 steps, produces a coordination graph where failure probability compounds on failure probability. This is why multi-agent systems often underperform single agents on reliability even when they outperform on capability.
- **Observability gaps hide the cliff.** Without distributed tracing through each step, you can't tell whether a failure originated in tool execution, state routing, or LLM reasoning. `console.log` is not a debugging tool for agents — you need semantic, structured traces or the failures look random.

## The move

Treat every step in an agent pipeline as an explicit reliability budget, and architect before you scale.

- **Set a step budget per workflow.** If a workflow requires more than 8-10 steps, split it into sub-agents with explicit handoff contracts. Budget the total failure probability, not individual step quality.
- **Add checkpoints with explicit fallbacks.** After every 3-4 steps, insert a routing node that either continues, escalates, or returns a partial result with a confidence flag. Never let a step execute without knowing what happens if it fails.
- **Measure step-level reliability in staging.** Use golden datasets with known inputs and expected outputs for every step. Track step-level P95/P99 latency, not just end-to-end latency — tail latency at the step level compounds into catastrophic end-to-end latency.
- **Prefer fewer, more capable tools over many fragile tools.** A tool with 99% reliability × 4 steps = 96% for that segment. Four tools each at 95% × 4 steps = 81%. Consolidation reduces the multiplication surface.
- **Instrument with structured traces from day one.** Use LangSmith, Phoenix, or custom OTEL spans for every LLM call, tool call, and state transition. Correlate trace IDs across steps. The goal is a flamegraph, not a log dump.
- **Build semantic caching to shortcut chains.** Exact-match prompt caches don't help when inputs vary. Use semantic similarity caching (embed the intent, not the text) to short-circuit repeated workflows before they hit step 1. This simultaneously improves latency and cuts cost.

## Evidence

- **Tech Blog — QubitTool:** "The 17x Error Trap is real: A 95% reliable single step becomes 35.8% reliable over 20 chained steps — most enterprise workflows hit this wall silently." — [QubitTool — AI Agent: 10 Pitfalls from POC to Production](https://qubittool.com/blog/ai-agent-poc-to-production-pitfalls)
- **Medium — Deepak Babu Piskala:** "At scale, an enterprise agent is not 'a model plus a UI.' It is a distributed system that happens to include an LLM. It inherits the entire reliability problem set of distributed systems — timeouts, retries, tail latency, partial failures, stale caches, inconsistent state." — [Data Science Collective — Lessons Learned from Building Enterprise AI Agents for Millions of Users](https://medium.com/%40prdeepak.babu/lessons-learned-from-building-enterprise-ai-agents-for-millions-of-users-cfd6a1ad3f56)
- **Research — Inventiple:** Tracked 4 production agentic systems for 6 months. Found LLM API costs dominate at 60-80% of total operating cost, with "model choice × step count" as the primary cost formula — confirming that step count is both a reliability risk and a cost driver. — [Inventiple — Agentic AI Production Cost: 6 Months of Real Data](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)
- **Research — Zylos Research:** "72% of enterprise AI projects now involve multi-agent systems (up from 23% in 2024). Token duplication is a major concern: MetaGPT 72%, CAMEL 86%, AgentVerse 53%." — [Zylos Research — Multi-Agent Orchestration Patterns 2025](https://zylos.ai/research/multi-agent-orchestration-2025)
- **Blog — Gheware DevOps:** "65% of teams hit a wall within 12 months and have to rewrite — choosing the orchestration framework upfront is critical. LangGraph for complex stateful workflows; CrewAI for fast prototyping." — [Gheware — LangGraph vs CrewAI vs AutoGen: Best AI Agent Framework 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **Demo success is not a reliability signal.** Agents are non-deterministic — they work in demos on friendly inputs. The failure modes only appear with real data, real users, and real stakes. Build evaluation infrastructure before you demo, not after.
- **The cliff appears at scale, not in testing.** A workflow that runs 100 times/day looks reliable in week one. At 10,000 runs/day, a 0.95⁵ reliability means 77% of runs have at least one failure. Budget for the scale you'll actually hit.
- **Token costs scale with step count AND with retry loops.** Every failed step that retries adds another full LLM call. A 4-step workflow that retries once on step 3 costs as much as a 5-step workflow. Budget retries explicitly, not as exceptional cases.
- **Checkpoint fallbacks require honest partial-result design.** If a step fails and you fall back to a partial result, that partial result must be something the user can act on. Returning an error message is not a fallback — it is an admission of failure. Design the partial output before you need it.
