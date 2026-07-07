# S-775 · The Untyped Handoff Problem Killing Multi-Agent Systems

The moment you add a second agent, you inherit a new class of failure: the untyped handoff. Two agents agree on nothing — not schema, not intent, not failure modes — and the downstream agent silently inherits whatever the upstream one decided to pass along. This is the single largest source of multi-agent production failures, and most teams don't discover it until they're deep in debugging.

## Forces

- **Multi-agent adoption is surging but success rates aren't.** Gartner tracked a 1,445% increase in multi-agent inquiries from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production. Yet ChatDev achieves only 33.3% correctness on real programming tasks, and AppWorld shows 86.7% failure on cross-app workflows. Adoption is ahead of the engineering discipline needed to make it reliable.
- **Pattern choice is the primary lever — bigger models aren't.** MultiAgentBench found smaller models with better coordination consistently outperform larger models with worse coordination. Pattern choice matters more than model capability for most multi-agent tasks. Logistics systems using the right pattern demonstrate 27% throughput gains and 22% cost reduction.
- **The four production patterns each have a narrow fit window.** Hierarchical, pipeline, orchestrator-worker, and peer-to-peer each excel in specific conditions and fail when misapplied. Teams that default to one pattern for everything accumulate invisible debt.
- **Cost compounds non-linearly.** A single-agent task averages $0.14 in API fees. A 4-agent orchestrator-worker workflow hits $5–8 per task. Without explicit cost modeling, teams discover their unit economics are broken only at billing time.

## The Move

**Match the coordination pattern to the failure mode, not to the workflow shape.**

**1. Use Pipeline (sequential) when:** Steps have strict order and no branching. Think Unix pipes — each agent transforms the output of the previous one. Great for research synthesis, document processing, content workflows. Failures are linear and easy to trace. Avoid when any step needs to route based on content.

**2. Use Hierarchical when:** A director agent delegates to specialists. The director doesn't do the work — it assigns, reviews, and routes. Shopify Sidekick runs this pattern: a coordinator orchestrates tool-calling agents that each own a domain. Optimal tool inventory per agent is 20–50 — beyond 50, maintainability collapses (Shopify's data). Fit for: multi-domain business processes, marketing agencies (Director → Strategist → Creative → Producer), customer service escalation chains.

**3. Use Orchestrator-Worker when:** The task has conditional branches that can't be predetermined. One orchestrator plans and dynamically assigns sub-tasks to workers, then synthesizes results. This is the highest-overhead pattern — use only when the workflow genuinely requires runtime routing decisions. The failure mode is orchestrator exhaustion: if the coordinator model can't hold the full task state, outputs degrade silently.

**4. Use Peer-to-Peer when:** Agents are equal specialists that need to collaborate without a central coordinator. Each agent can request help from any other. Most fragile pattern: requires typed message schemas and explicit timeout/error propagation, otherwise agents deadlock or diverge. Reserve for: research agent swarms, distributed monitoring, parallel exploration with synthesis.

**5. Always define typed handoff schemas.** The #1 killer of multi-agent systems is untyped handoffs (RaftLabs, 2025). Every inter-agent message must have: a defined schema, an intent field, a failure mode field, and a TTL. Without this, downstream agents silently inherit ambiguity and fail in non-deterministic ways.

**6. Instrument token budgets per agent per task.** Track cost at the agent level, not the system level. An orchestrator-worker workflow at $5–8 per task is acceptable for high-value tasks but catastrophic for commodity ones. Route cheap tasks to cheap models (Claude Haiku, GPT-4o-mini) — only route complex reasoning to premium models.

## Evidence

- **Gartner (Q2 2025):** 1,445% surge in multi-agent inquiries Q1 2024→Q2 2025; 57% of organizations already have agents in production; 40% of agentic AI projects at risk of cancellation by 2027 — [Gartner via RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **MultiAgentBench (production research, 2025):** Smaller models with better coordination outperform larger models with worse coordination; pattern choice matters more than model capability; logistics systems show 27% throughput gains and 22% cost reduction when the right pattern is applied — [Thread Transfer](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns)
- **Shopify Sidekick engineering post (Aug 2025):** Hierarchical pattern with 20–50 tools per agent is the optimal maintainability window; beyond 50, behavior becomes unpredictable; their director-agent coordinates domain-specialist agents through explicit tool delegation — [Shopify Engineering](https://shopify.engineering/building-production-ready-agentic-systems)
- **Zylos Research (2026):** Single agent conversation averages $0.14; 4-agent orchestrator-worker workflow runs $5–8 per task; 96% of teams report costs exceeding initial projections; 3–10x more LLM calls per agent vs. simple chatbots — [Zylos Research](https://zylos.ai/research/2026-02-19-ai-agent-cost-optimization-token-economics)
- **RaftLabs production survey (Nov 2025):** 89% of teams have observability tooling but only 52% have evals; untyped handoffs between agents are the #1 reliability killer in multi-agent systems — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **Adding a second agent doesn't make a system more capable — it multiplies failure modes.** Multi-agent systems require typed contracts, explicit error propagation, and observability per agent. Without these, a second agent adds more problems than it solves.
- **Pipeline is not the safe default — it's the trap.** Teams default to sequential pipelines because they're easy to reason about. But they break the moment any step needs conditional routing, which is most real-world tasks. Pipeline is right for <10% of production multi-agent use cases.
- **The "demo works, production breaks" gap is usually the handoff.** The handoff between agents never appears in demos because demos use hand-crafted inputs. In production, agents generate inputs for each other, and without typed schemas, the downstream agent receives a structure it wasn't expecting. Test handoffs specifically, not just agent outputs in isolation.
- **Cost observability lags cost reality by months.** Most teams discover their agent bill is 3–10x projections only at the end of the first billing cycle. Instrument per-agent token budgets before deploying to production, not after.
