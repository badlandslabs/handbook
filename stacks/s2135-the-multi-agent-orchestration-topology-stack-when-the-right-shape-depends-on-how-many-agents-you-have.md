# S-2135 · The Multi-Agent Orchestration Topology Stack — When the Right Shape Depends on How Many Agents You Have

When you need multiple agents to collaborate, but wiring them together in the wrong topology turns a tractable problem into a fragile, slow, or expensive mess.

## Forces

- **Supervisor bottlenecks** — a single coordinator is a single point of failure, and its context window fills up fast as N workers report back
- **Swarm chaos** — peer-to-peer handoffs are natural for conversational routing, but become undebuggable when you need deterministic execution order
- **Hierarchical overhead** — multi-level management trees scale to 50+ agents, but the added latency and coordination plumbing are overkill for a 4-agent research pipeline
- **Context collapse** — "Lost in the Middle" degrades LLM reasoning by up to 73% on buried facts in long contexts, making topology a first-order concern, not a detail
- **The selection equation** — agent count × task dynamism × fault-tolerance requirement = topology; getting any factor wrong produces a system that either over-engineers or under-performs

## The Move

Match orchestration topology to the actual shape of the work. The three canonical patterns serve different regimes:

**Supervisor (3–8 agents, deterministic):** A central coordinator assigns tasks and aggregates results. Workers never talk to each other — only to the supervisor. Best when the task graph is known upfront and execution order matters. Single point of failure is the main risk. Implemented in LangGraph with conditional edges or OpenAI Agents SDK handoffs.

**Swarm (2–15 agents, dynamic/conversational):** Agents hand off to each other peer-to-peer via a `transfer_to_X` tool call. No central coordinator — the LLM decides routing at each step. OpenAI Swarm (Oct 2024, 21.9k GitHub stars) and its successor the OpenAI Agents SDK (Mar 2025) implement this as two primitives: *routines* (prompt + tools as a system prompt) and *handoffs* (a tool that returns another Agent). Stateless Chat Completions API means no shared state by default — pass what the next agent needs in the handoff payload.

**Hierarchical (10–50+ agents, enterprise-scale):** A management tree where a top-level manager delegates to team leads who delegate to specialists. Handles genuinely complex workflows with multiple sub-domains. Google Agent Bake-Off: distributed multi-agent cut processing from **1 hour → 10 minutes** (6× speedup). AdaptOrch (2026): orchestration topology impacts SWE-bench performance more than model choice, delivering **12–23% gains**.

**Blackboard (any count, opportunistic):** A shared workspace (shared memory, scratchpad doc, or vector store) that all agents read and write. No direct agent-to-agent messaging — agents volunteer contributions based on what they see on the blackboard. Originally from the 1977 Hearsay-II speech-recognition project; resurfacing in LLM stacks for research-and-synthesise tasks. Reduces N² mesh communication to O(n) reads/writes against one store. Risk: stale reads, lost updates, and conflicting contributions when multiple agents modify shared state concurrently.

**Hybrid (most real systems):** Supervisor for the outer orchestration, sequential pipeline within a stage, swarm within a sub-domain. The Paiteq 2026 production survey found most shipping systems use a hybrid of supervisor (outer) + sequential (inner stages).

**Model layer split:** Production systems commonly route to different model tiers — Claude Opus 4.7 for high-reasoning tasks (supervision, planning), Haiku 4 for fast workers (scraping, simple transformations). Mixer-and-match outperforms a single model across all roles.

**Production essentials across all patterns:** Hard timeouts per agent, observability hooks on every handoff, graceful degradation when an agent fails (don't stall the whole run), and a mechanism to prevent infinite handoff loops.

## Evidence

- **Google Agent Bake-Off:** Distributed multi-agent processing cut task time from **1 hour → 10 minutes** (6× speedup) — proving topology delivers more than model tuning — [Source: MACGPU 2026 Multi-Agent Architecture Guide](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)
- **Microsoft ISE (Jun 2026):** Real production case study of a retail customer migrating from a modular monolith chatbot (single-agent router) to a microservices-based multi-agent architecture enabling agent reuse across teams. Documents the coordinator pattern evolution and performance trade-offs in detail — [Source: Microsoft ISE Developer Blog](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **NinjaTech AI "Show HN" (2026):** 4-agent team (Scout, Pixel, Bolt, unnamed) designed and shipped a complete news-to-video platform in 36 hours for $270. Agents self-selected tech stack, debated story selection, collaborated on video prompts, deployed to production, and created CI/CD pipeline — entirely autonomous from goal to ship — [Source: Hacker News Show HN](https://news.ycombinator.com/item?id=47059153)
- **OpenAI Swarm ecosystem:** 21,732 GitHub stars, 2,317 forks. Swarm distilled orchestration to two primitives (routines + handoffs) that became the conceptual foundation for the OpenAI Agents SDK (Mar 2025) — [Source: TrendingBots / GitHub](https://github.com/openai/swarm)
- **AdaptOrch (2026):** Orchestration topology selection delivers 12–23% SWE-bench gains independent of model choice — [Source: MACGPU 2026 Guide](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)
- **Multi-Agent Memory Failures:** 36.9% of multi-agent production failures stem from inter-agent misalignment (structural), not model quality — [Source: Mem0 blog, Jul 2026](https://mem0.ai/blog/multi-agent-memory-systems)
- **SE-Blackboard (IEEE, 2025):** Modular shared-state blackboard architecture applied to multi-agent software engineering — [Source: IEEE Xplore](https://ieeexplore.ieee.org/document/11527206)

## Gotchas

- **Handoffs are stateless by default** — in Swarm/OpenAI Agents SDK, each handoff starts fresh unless you explicitly thread context through the payload. Teams lose state between handoffs and spend days debugging why the second agent "forgets" what the first one found.
- **Supervisor context window is the hidden bottleneck** — every worker report, tool result, and intermediate artifact flows through the supervisor's context. A 5-agent supervisor system quietly degrades once the shared task memory exceeds ~30k tokens.
- **Swarm handoff loops are real** — without a max-hops guard, agents can transfer control back and forth indefinitely. Set `max_turns` or equivalent.
- **Blackboard write conflicts are silent data corruption** — two agents simultaneously writing to the same shared doc can silently clobber each other's contributions. Implement optimistic locking or serialized write queues.
- **The hype-to-reality gap on Swarm is real** — TrendingBots rates Swarm at hype 51 vs reality 39. Most production systems use LangGraph or CrewAI for supervisor/pipeline patterns; Swarm remains popular for experimentation and prototyping rather than enterprise deployments.
