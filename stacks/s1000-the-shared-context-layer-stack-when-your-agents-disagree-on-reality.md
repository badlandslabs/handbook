# S-1000 · The Shared Context Layer Stack — When Your Agents Disagree on Reality

You built a multi-agent system. Support issues a refund for a product marked out-of-stock. Pricing extends a 20% discount that fulfillment voids. Risk management blocks a transaction that sales already closed. Each agent was individually correct. The system failed collectively. The root cause: every agent queried a different data source with a different refresh lag, and nobody defined which source was authoritative or when its data was considered current.

## Forces

- **Each agent optimizes locally.** An agent that reads Redis (hourly refresh) and one that reads Snowflake (overnight refresh) will reach opposite conclusions about the same inventory level — and both will be right, by their own definition.
- **Latency tolerance varies by agent type.** A fraud-detection agent needs millisecond-fresh data; a reporting agent can tolerate minutes. Giving every agent the same data source either over-costs the cheap tasks or under-delivers for the critical ones.
- **Agents make irreversible commitments before validation.** A support agent promising a refund, a sales agent confirming a price — these actions propagate downstream and become constraints that other agents treat as facts. By the time the authoritative source is queried, the commitment is already in the system.
- **Adding more agents amplifies inconsistency.** Each new agent brings its own data source, its own refresh cadence, and its own assumptions about what "current" means. A system that works at 3 agents fails at 7.

## The move

The fix is a **shared context layer** — a single, authoritative, time-bounded data serving layer that every agent queries before acting. Not shared state (agents don't all write to the same database), but shared *read semantics*: the same query always returns the same answer, with an explicit staleness bound.

- **Define one authoritative source per entity.** For each business entity (customer, order, product, inventory), designate one system as the source of truth. All agents read from that source, not their preferred shard or replica.
- **Serve through a unified context API.** Every agent calls `get_customer(id, staleness_max=0)` or `get_order(id, staleness_max="5m")`. The API enforces the staleness parameter and raises an error if the requested freshness cannot be met. Agents never bypass this API to read raw replicas.
- **Tag every data read with a freshness contract.** A `5m` freshness contract means the agent accepts data up to 5 minutes old. An agent making an irreversible commitment (refund, price lock, inventory deduction) must declare `staleness_max=0` — it gets current data or an error it must handle.
- **Use event-driven updates to keep the context layer fresh.** Rather than polling each source on every request, push updates via events (Kafka, SQS, Redis Streams) when authoritative data changes. The context layer subscribes and updates its cache, keeping lag bounded by event delivery time.
- **Implement conflict detection at write time, not read time.** When an agent submits a committed action (discount applied, order modified), the context layer checks whether the state it has seen has been superseded since the agent read it. If a conflict exists, the action is rejected with the current state — forcing the agent to re-evaluate.
- **Expose staleness to the agent as a first-class signal.** An agent that receives `stale_warning: true` alongside its data can make an informed decision: proceed with a flag, escalate to human, or retry with fresh data. This is better than the agent operating on silently outdated information.

## Evidence

- **Case study (Fortune 100 retailer, 12-agent supply-chain copilot):** Devsatva documented a production deployment achieving 99.6% task completion using the orchestrator-worker pattern with explicit state-sharing contracts. The key architectural decision was routing all cross-agent reads through a unified context service rather than allowing agents to query their own data sources. Agents still owned their specialized tools; the coordination layer owned truth. — [Devsatva Blog: Multi-Agent Coordination Patterns 2026](https://devsatva.com/blog/multi-agent-coordination-patterns-2026)
- **Real failure scenario (2025 retail production incident):** A support agent queried Redis (hourly-refreshed snapshot), pricing pulled Snowflake (overnight), and inventory checked a Postgres replica (15-min lag). Result: refunds issued for orders already reshipped, discounts on out-of-stock items, fulfillment promises against phantom inventory. The fix described: agents query a single authoritative context service with explicit staleness bounds on every read. — [Tacnode: Multi-Agent Architecture — 8 Coordination Patterns That Actually Work (2026)](https://tacnode.io/post/multi-agent-architecture)
- **Real-world multi-agent Claude Code deployment with 3 roles:** A solo developer (yego) building growity.ai with Claude Code as a "virtual engineering team" discovered the hard way that assigning broad authority without coordination constraints causes agents to over-engineer and contradict each other. The solution was a tight 3-role setup (architect, coder, reviewer) with Markdown-mediated handoffs and Docker isolation — explicit boundaries replaced implicit trust. The "CEO incident" where an agent spun up 20 roles and wrote memos to itself became a canonical cautionary tale on HN. — [Hacker News: Multi-agent Claude Code setup – 3 roles, Markdown coordination, Docker](https://news.ycombinator.com/item?id=47245373)

## Gotchas

- **The context layer becomes a single point of failure.** If it goes down, every agent blocks. You need it HA, and you need agents to have a defined fallback behavior (escalate, retry, or degrade gracefully) when they can't reach it — not just fall back to reading their old source directly.
- **Staleness contracts require business buy-in, not just engineering.** Declaring that a refund agent must have `staleness_max=0` means engineering must guarantee sub-second data freshness for that path. That has infrastructure and cost implications that need a product decision, not just an architecture one.
- **Agents will still try to bypass the context layer for "quick reads."** You must make the context API the path of least resistance — fast, low-latency, and always available — or agents will find shortcuts that reintroduce the inconsistency problem you were solving.
