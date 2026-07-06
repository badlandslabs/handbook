# S-721 · The 4-Category Filter: Where Agents Actually Shipped vs. Where They Died

[Agents work in narrow, well-scoped domains with tight feedback loops. Everything else — open-ended research, ambiguous judgment calls, multi-stakeholder coordination — failed to reach production. The gap between the demo and production wasn't a tooling problem. It was a scope problem with a cost measurement attached.]

## Forces

- **The demo-to-production drop is real and severe.** One team documented a 92% success rate in testing collapsing to 55% in production — with costs 4x the budget. This isn't an edge case; it's the expected outcome when agents face real data chaos.
- **Agents that shipped share a common shape.** Four categories consistently graduated from pilot to production: developer tooling, internal operations, customer service automation, and structured data extraction. All share tight feedback loops, clear success criteria, and low blast radius on failure.
- **The categories that died share a common shape too.** Open-ended research, multi-stakeholder coordination, and anything requiring ambiguous judgment all stalled at the pilot stage — regardless of framework or budget.
- **Cost is a forcing function for scope discipline.** Teams that tracked costs weekly caught scope creep early. Teams that didn't, built expensive demos that failed in production.

## The move

Production-grade agents cluster into four domains — and staying within those boundaries is what separates shipping teams from expensive pilots:

- **Developer tooling** — the tightest feedback loop (compile → test → human review) made this the safest early beachhead. Multi-file refactors, PR review, and semi-autonomous issue resolution all shipped. The agent writes code; a compiler and CI gate correctness.
- **Internal operations automation** — ticket triage, access-request routing, runbook execution, onboarding checklists. Clear success criteria (did the right ticket get to the right person?) and low blast radius when the agent is wrong.
- **Customer service automation (structured)** — FAQ routing, refund eligibility checks, order status lookups. Narrow scope, high volume, reversible decisions. The moment a customer service agent needs to understand emotion or context, it breaks.
- **Structured data extraction** — pulling entities from documents, filling CRM fields, converting unstructured inputs into schema-compliant outputs. The LLM does the parsing; a validator does the enforcement.

The failure pattern is identical across all four categories when teams go outside the boundary: success rate drops 20-40 percentage points, costs 3-4x, and failure modes are non-deterministic.

## Evidence

- **Production breakdown by category:** Developer tooling, internal ops, customer service, and structured data extraction consistently shipped. Open-ended research and ambiguous judgment tasks consistently stalled. — [technspire.com — State of Agentic AI End-2025: Production Lessons and Patterns (Dec 2025)](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)
- **Real cost and quality gap:** One production app showed 92% test success vs. 55% production success, with monthly costs jumping from $200 budgeted to $847 actual. Root causes: 47 unanticipated data format issues, cascading failures from incorrect early matches. — [Calder's Lab — AI Agent 2025 Breakthrough: What $847/Month in Production Costs Taught Me (Jan 2025)](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough/)
- **AutoGen deprecated, Microsoft Agent Framework incoming:** AutoGen moved to maintenance mode October 2025. Its successor is the Microsoft Agent Framework (GA Q1 2026). Teams using AutoGen in production should plan migration. — [JetThoughts — LangGraph vs CrewAI vs AutoGen: Open Source AI Agent Frameworks 2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)

## Gotchas

- **"We can expand scope later" is the most expensive sentence in agent development.** The cost gap isn't caused by wrong frameworks — it's caused by scope creep into domains without tight feedback loops. Lock scope before choosing a stack.
- **Cost tracking is not optional.** Teams that don't track per-agent costs weekly will be surprised by 3-4x overruns in production. Budget for it from day one.
- **Human-in-the-loop is not a sign of weakness.** It's the correct architecture for any domain where failure is expensive. Gates between agent actions and irreversible outcomes are production hygiene, not a workaround.
- **LangGraph users (Klarna, Replit, Elastic) and CrewAI users represent two different risk profiles.** If your agent touches production money or needs durable state, default LangGraph. If you're still exploring scope and need fast iteration, CrewAI buys you time — but the migration to LangGraph is inevitable if the agent succeeds.
