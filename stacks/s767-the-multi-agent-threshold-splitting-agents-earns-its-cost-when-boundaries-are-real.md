# S-767 · The Multi-Agent Threshold: Splitting Agents Earns Its Cost Only When Boundaries Are Real

The intuition that "more agents will do better than one agent" is wrong more often than it is right. Most production multi-agent systems exist because the work has genuine boundaries — different access controls, different tools, different models — not because two LLMs are smarter than one. The teams that get this wrong build a distributed monolith and pay the debugging tax forever.

## Forces

- **Adding agents adds hops.** Every inter-agent call is a new inference event and a new latency source. A 4-agent workflow costs $5–8 per task in inference alone — and that number doesn't include the engineering time to coordinate them.
- **Context window exhaustion is the real forcing function for splitting** — but not the only one. Different security boundaries, different tool registries, and different model requirements all create legitimate reasons to split that the "just one agent" camp ignores.
- **The god-agent anti-pattern is real** — a single agent doing classification, retrieval, generation, and escalation in one context window hits token limits faster than expected and produces confused reasoning that looks like a prompt problem.
- **Typed schemas between agents are the #1 killer of multi-agent systems** — without them, agents drift apart in production and produce non-deterministic failures.
- **Observability without evals is the debugging gap** — 89% of teams have tracing but only 52% have evaluation loops. You can watch a failure happen; you can't prove it won't happen again.

## The Move

**Default to single-agent. Go multi-agent only when the work has real boundaries.**

The split triggers are not "this is complex" or "I want parallelism." They are:

- **Different access scopes.** The billing agent needs PCI data the support agent must never see. Splitting enforces this at the access layer, not in a prompt.
- **Different tool sets.** Code interpreter, CRM tools, and document retrieval require different tool registrations. Loading all of them into one agent inflates tool-schema overhead on every call.
- **Different model requirements.** A fast classifier at 50ms latency and a careful synthesizer at 2s latency should not share a model. Splitting lets you route each to the right model for the job.
- **Different blast radii.** If one agent's failure should not cascade, it should not share a context window.

Once you've decided to split, pick the coordination pattern by answering two questions: "Does one agent own the outcome?" and "Can work proceed in parallel?"

| Pattern | When to use | Latency | Cost | Failure mode |
|---------|-------------|---------|------|--------------|
| **Supervisor (hierarchical)** | One agent drives, others execute subtasks | Medium | Low–Medium | Supervisor bottleneck |
| **Orchestrator-worker** | Task is decomposable but not parallelizable | High | Medium–High | Orchestrator hallucination |
| **Peer-to-peer** | Multiple agents with shared goal, independent execution | Medium | Medium | Consensus deadlocks |
| **Market/brokered** | Agents bid on tasks, decentralized ownership | Variable | High | Task unclaimed |

**Typed schemas between every agent boundary.** Not optional. Not "we'll add it later." Without schema enforcement, agents drift in production and failures become non-deterministic. The same principle that prevents distributed system failures in conventional software.

**One eval loop per agent, not one per system.** Each agent has its own success criteria, and each agent is evaluated independently. System-level eval without agent-level eval hides which component is failing.

## Evidence

- **Blog — Gravity (2026):** Multi-agent coordination patterns breakdown — "The intuition that 'more agents will do better than one agent' is wrong more often than it is right. Most production multi-agent systems exist because the work has genuine boundaries (different access controls, different tools, different models), not because two LLMs are smarter than one." — https://gravity.fast/blog/ai-agent-multi-agent-coordination

- **Blog — RaftLabs (Nov 2025):** Multi-agent architecture patterns — "Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. 57% of organizations already running agents in production. Four orchestration patterns cover most use cases: hierarchical, pipeline, orchestrator-worker, and peer-to-peer. $5–8 per complex task in inference costs for 4-agent workflows. 89% have observability but only 52% have evals." — https://www.raftlabs.com/blog/multi-agent-systems-guide

- **Blog — Technspire (Dec 2025):** State of Agentic AI end-2025 — "Four categories consistently shipped from pilot to production in 2025: developer tooling, internal operations automation, research and analysis, and customer-facing narrow tasks. What separated shipping systems from expensive pilots: narrow scope, deterministic guardrails, clear success criteria, and low individual blast radius." — https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons

- **Blog — Gennoor (Feb 2026):** Agentic AI production lessons — "Design human-in-the-loop as a permanent feature for high-stakes decisions, not a temporary crutch. Implement hard cost guardrails before launch — agents can burn through five-figure budgets over a weekend. 40% of agentic AI projects at risk of cancellation by 2027 (Gartner)." — https://gennoor.com/resources/blog/agentic-ai-production-lessons

- **HN — Show HN: Opensoul (Mar 2025):** Opensoul agentic marketing stack — A real deployment of 6 agents organized as a marketing agency: Director, Strategist, Creative, Producer, Growth Marketer, Analyst — each running on scheduled heartbeats, checking a shared work queue, delegating to teammates. Justifies the split because each agent has distinct tools, distinct access scopes, and distinct output formats. — https://news.ycombinator.com/item?id=47336615

## Gotchas

- **"I'll add typed schemas later" means you will not have typed schemas.** The schema drift happens silently in production, and the failures are non-deterministic. Enforce at the boundary, not in the middleware.
- **Multi-agent parallelism is not free.** Peer-to-peer and market patterns look like they parallelize, but consensus rounds, task unclaiming, and bid evaluation add sequential hops that eliminate the parallelism gain.
- **Agent-level eval is not optional.** Without it, you know the system failed; you don't know which agent failed. System-level pass/fail hides the bottleneck indefinitely.
- **Orchestrator-worker is the most commonly misused pattern.** Teams use it for tasks that are actually decomposable into independent subtasks — they should use supervisor or peer. The orchestrator becomes a bottleneck and a hallucination source when it centrally synthesizes everything.
- **Cost compounds silently.** A 4-agent workflow at $5–8 per task seems manageable in demos. At 10,000 tasks/day it is $50,000–$80,000/day in inference alone. Model routing — sending fast tasks to cheap models and reserving expensive models for only the steps that need them — is the primary cost lever.
