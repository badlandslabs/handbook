# S-1276 · The Infrastructure-First Agent Stack — When You Build the Model First and the System Last

When your agent is a demo in production — it calls the right tools and says sensible things, but quietly fails in ways nobody notices until a user complains.

## Forces

- **The "just add a model" trap** — the 2023–2024 framing treated agents as one entity: one reasoning loop, everything handled by the LLM. That mental model persists even though it doesn't survive contact with production.
- **The invisible infrastructure problem** — most production agent failures aren't model failures. The model is fine. What breaks is the scaffolding around it: context preparation, tool result validation, permission boundaries, recovery paths, and observability.
- **Architecture follows hype, not requirements** — teams pick orchestration patterns (hierarchical, pipeline, supervisor) based on blog posts rather than their actual failure modes. The pattern that worked for Anthropic's research agents is the wrong pattern for your customer-service bot.
- **Evaluation gaps hide silent failures** — output-only scoring misses 20–40% of regressions (Confident AI, 2026). An agent can produce a perfectly formatted wrong answer and pass every automated check.

## The move

Build the control layer *before* you optimize the model. The stack that ships in production:

**1. Tool validation layer — not just schemas, but contracts.**
Don't just define what a tool returns. Define what *valid* output looks like: required fields, acceptable value ranges, what an empty response means. Wrap every tool call in schema validation. When a tool returns unexpected data, the agent gets an explicit error with a recovery hint, not a silent null.

**2. Context preparation as a first-class layer.**
The LLM's job is to decide what to do next, given *prepared* context. That means retrieval, formatting, relevance filtering, and noise removal happen *before* the inference call — not inside it. Benjamin Nweke (TDS, 2026) frames this as a four-layer architecture: Decision (LLM) → Context → Feedback → Monitoring. The LLM is only the decision layer.

**3. Typed schemas at every agent handoff.**
RaftLabs (2026) finds untyped handoffs kill multi-agent workflows faster than any other issue. Every agent-to-agent boundary needs a validated schema with version numbering. Schema drift between agents is a silent failure mode — everything looks fine until the aggregate output is wrong.

**4. Explicit permission boundaries, not reflex approvals.**
93% of agent permission prompts get approved reflexively in production (BeConfident Labs, 2026). Treat permission prompts as infrastructure, not conversation. Define permission scopes statically, log every decision, and surface anomalies — don't rely on the model to self-limit.

**5. Tracing as the backbone of debuggability.**
Hadil Ben Abdallah (DEV Community, 2026) identifies six production failure modes, all invisible without trace-level observability: silent tool call failures, context drift, hallucinated tool calls, permission scope creep, loop detection misses, and budget exhaustion without alerts. Tracing every tool call, decision, and context mutation is not optional — it's the only signal you have.

**6. Eval the behavior, not just the output.**
Confident AI (2026) evaluates at three levels: end-to-end (did the task succeed?), trajectory-level (was the path efficient?), and component-level (which retriever, tool, or sub-agent broke?). Output-only scoring is the weakest eval tier. LLM-as-judge works for output quality; deterministic checks work for tool correctness and schema compliance.

**7. Failure budgets and circuit breakers.**
Every tool call should have a timeout, retry count, and fallback. When a tool fails three times, the agent should get a structured error with the original tool name, the failure reason, and a suggested alternative — not a generic failure message that lets it improvise.

## Evidence

- **TDS Blog Post:** "Most AI Agents Fail in Production Because They're Built Backwards" — defines the "built backwards" pattern (building top-down from goal to tools to model) and the four-layer alternative (Decision → Context → Feedback → Monitoring). Benjamin Nweke, May 27, 2026 — https://towardsdatascience.com/most-ai-agents-fail-in-production-because-theyre-built-backwards
- **DEV Community:** "Why AI Agents Fail in Production (And How Engineering Teams Are Fixing It in 2026)" — catalogs six production failure modes (silent tool call failures, context drift, hallucinated tool calls, permission scope creep, loop detection misses, budget exhaustion) and their fixes. Hadil Ben Abdallah, June 4, 2026 — https://dev.to/hadil/why-ai-agents-fail-in-production-and-how-engineering-teams-are-fixing-it-in-2026-job
- **Confident AI Blog:** "LLM Agent Evaluation Metrics in 2026" — three-tier eval framework (end-to-end, trajectory-level, component-level). Kritin Vongthongsri, June 1, 2026 — https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide
- **RaftLabs:** "Multi-Agent Systems: Architecture Patterns for Production AI" — typed schemas at agent handoffs as the #1 reliability requirement; 89% of teams have observability but only 52% have evals. Ashit Vora, March 27, 2026 — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **Hacker News Discussion:** "Ask HN: How are you orchestrating multi-agent AI workflows in production?" — practitioner discussion on state management, observability, and framework choices (LangChain, CrewAI, custom). swrly, ~3 months ago — https://news.ycombinator.com/item?id=47660705
- **47Billion:** "AI Agents in Production: Frameworks, Protocols, and What Actually Works in 2026" — phased roadmap from tool prototyping to MCP/A2A adoption. KamalPreet Singh, February 24, 2026 — https://47billion.com/blog/ai-agents-in-production-frameworks-protocols-and-what-actually-works-in-2026

## Gotchas

- **The demo-to-production gap is invisible until it isn't.** Your agent looks like it's working during development because the failure modes (schema drift, empty tool responses, permission scope creep) only manifest under real data distribution.
- **Picking an orchestration pattern for the wrong reasons.** The right pattern depends on your failure modes, not on what Anthropic or OpenAI used. Sequential works for linear workflows. Supervisor/hierarchical works when one agent needs to coordinate others. Pipeline works for embarrassingly parallel stages. Peer-to-peer rarely works in production.
- **Eval once and call it done.** Agent behavior shifts with every prompt change, model version, and tool schema update. Eval coverage needs to grow with the agent — production executions should seed test cases automatically.
