# S-728 · Why Your Second Agent Is a Mistake: Multi-Agent Patterns That Actually Ship

[Every team adds a second agent thinking more agents means better results. Most are wrong. Multi-agent costs 2–5× more in tokens for the same task and compounds observability problems. The teams that get it right aren't the ones with the most agents — they're the ones who correctly identified which tasks genuinely need boundaries and chose the right coordination pattern for the shape of the work.]

## Forces

- **The intuition is backwards.** Most engineers add agents when a single agent makes mistakes. But mistakes usually mean: bad prompting, wrong model, or insufficient retrieval — not insufficient agents. Multi-agent compounds cost without fixing root causes.
- **Gartner tracked 1,445% growth in multi-agent inquiries** from Q1 2024 to Q2 2025. Despite the surge, most teams are implementing these systems incorrectly — splitting on fictional boundaries rather than real ones.
- **Multi-agent costs are non-linear.** A single complex task in a multi-agent pipeline costs $5–8 in inference. Agentic RAG (1–6 dynamic retrieval calls per turn vs. 1 for classic RAG) runs 3–8 LLM calls and 2–6 retrieves per query. Token costs compound fast.
- **The observability gap is real.** 89% of teams use tracing, but only 52% run evals. Multi-agent amplifies this: you need traces not just per-agent but per-handoff — and most teams don't instrument it.

## The move

**Default to single-agent. Split only when the work has a real boundary.**

Real boundaries that justify multi-agent:

| Boundary | Why it matters |
|----------|----------------|
| **Different access scopes** | Billing agent sees invoices; support agent sees support tickets. They can't share credentials. |
| **Different tools or tool counts** | Code agent needs bash + git + file system. Research agent needs web search + vector DB. Merging tool sets creates permission nightmares. |
| **Different models** | A $0.20/MTok extraction model doesn't need to run on Opus 4.6. Different tasks have different capability requirements. |
| **Different domains** | Legal, compliance, and creative reasoning have incompatible prompting and evaluation criteria. |

**Four coordination patterns cover most production use cases:**

1. **Supervisor (hierarchical)** — One controller agent delegates to specialized workers. Easiest to debug: the supervisor's trace shows the full decision path. Best for: one-to-many task decomposition.
2. **Pipeline (sequential)** — Output of agent A feeds into agent B feeds into agent C. No delegation, no branching. Best for: stage-based work (research → write → edit).
3. **Peer handoff** — Agents pass control based on context or user intent. Clean for stage-based workflows like sales → onboarding → support. Best for: customer lifecycle flows.
4. **Market (bidding)** — Multiple agents bid on tasks; one wins. Best for: load balancing across equivalent workers. Most complex to build and debug.

**Pick the pattern by the shape of the data flow, not by number of agents:**

- One input → many parallel sub-tasks → one output: **supervisor**
- Linear stage progression: **pipeline**
- Different agents own different stages of a lifecycle: **peer handoff**
- Multiple equivalent workers, best-one-wins: **market**

**Run evals before and after going multi-agent.** Measure quality improvement per dollar. If a single Sonnet 4.6 agent with better prompting gets 85% on your benchmark, a 3-agent pipeline getting 87% may not be worth 3× the cost.

## Evidence

- **Blog post, Gravity (May 2026):** Multi-agent costs 2–5× more in tokens for the same work. Cost is worth it only when specialization measurably improves quality. Default to single-agent; multi-agent earns its place when work has real boundaries. — https://gravity.fast/blog/ai-agent-multi-agent-coordination
- **Blog post, RaftLabs (Nov 2025):** Four coordination patterns cover production use cases: hierarchical, pipeline, orchestrator-worker, peer-to-peer. 89% of teams use tracing but only 52% run evals. Inference costs compound to $5–8 per complex task. — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **Survey, Cleanlab (2025):** Only 5% of 1,837 engineering leaders have AI agents live in production (95 of 1,837). 70% of regulated enterprises rebuild their agent stack every 3 months. < 1 in 3 teams satisfied with observability and guardrail solutions. — https://cleanlab.ai/ai-agents-in-production-2025

## Gotchas

- **Adding agents doesn't fix bad prompting.** If a single agent produces wrong output, a team of agents producing wrong outputs in parallel is worse. Fix the single-agent baseline first.
- **Handoffs are uncharted territory.** Every agent boundary is a potential observability gap. Log what was handed off, not just what came back. LangSmith's time-travel debugging and checkpointing help here.
- **Market patterns are rarely worth the complexity.** Bidding and competition between agents adds non-deterministic behavior that's hard to test and harder to explain to stakeholders.
