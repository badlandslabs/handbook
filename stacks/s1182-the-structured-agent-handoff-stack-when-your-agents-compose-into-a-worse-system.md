# S-1182 · The Structured Agent Handoff Stack — When Your Agents Compose Into a Worse System

Individually excellent agents. A team spent months tuning each one. Then you wire them together — lead planner, researcher, synthesizer, reviewer — and the composed system is worse than any single agent alone. Responses hallucinate context that wasn't in the previous agent's output. Retries double-charge. The handoff is where the system breaks.

## Forces

- **Agent excellence doesn't compose.** Each agent is a strong LLM with good tools. The failure mode lives entirely in the boundary between them — not in any individual agent.
- **Implicit contracts are time bombs.** When the output schema is "natural language summary," the receiving agent fills gaps with plausible-but-wrong details. This is hallucination propagation, not single-agent hallucination.
- **Coordination overhead grows super-linearly.** Adding agents increases pair-wise handoff complexity. Without infrastructure, you trade one agent's simplicity for N × (N-1) handoff failure modes.
- **Retries amplify without idempotency.** When a handoff fails and you retry blindly, side-effecting operations (API calls, database writes) double-execute. The retry mechanism makes the failure worse.
- **Context concatenation is the default and it's wrong.** The naive approach — shove Agent A's full output into Agent B's context — hits token limits and buries the signal in noise. The right approach (structured packaging) requires deliberate design.

## The Move

Build handoffs as explicit, typed, recoverable contracts — not as context concatenation.

- **JSON schema contracts at every boundary.** Every agent output has a published schema. The receiving agent validates input against that schema before processing. Non-conforming inputs are rejected at the boundary — never propagated silently downstream. "Implicit agreement on output format is a time bomb."
- **Structured context packaging, not raw concatenation.** Include: the task ID, the source agent's reasoning chain (not just the conclusion), a summary of the output, and metadata about the handoff envelope. Drop the raw text dump.
- **Idempotent handoffs with explicit envelope IDs.** Every task and handoff gets a unique ID. On retry, the receiving agent checks whether the task ID was already processed before re-executing side effects. Any operation with side effects must be safe to run twice.
- **Per-agent retry with lead-agent orchestration.** Subagents fail independently; the lead agent re-schedules the failed subagent without restarting the entire task. Recovery is scoped to the failure boundary, not the whole crew.
- **Explicit termination conditions in task descriptions.** Agent loops — agents repeatedly delegating back and forth — happen because tasks lack clear stop criteria. Every task definition includes: success condition, max iterations, and what "done" looks like for the output schema.
- **Tiered capability permissions per agent.** Rather than giving each agent full system access, implement capability-based scopes. High-stakes actions (refunds, data writes, external API calls) require explicit permission scope. This is trust infrastructure, not just security.

## Evidence

- **Engineering blog:** Anthropic's multi-agent research system uses parallel subagents that write findings to a shared filesystem — not message passing. The lead agent reads and synthesizes. Subagents retry independently without restarting the full research task. "A multi-agent system consists of multiple LLMs autonomously using tools in a loop, coordinated by a lead agent that plans the research process and spawns parallel subagents." — [Anthropic Engineering, June 2025](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Engineering blog:** Shopify Sidekick implements evaluation harnesses *before* architectural decisions — so architectural changes are measurable. Capability-based access control (not full access) and human-in-the-loop checkpoints for high-stakes operations. "Without a robust evaluation framework, architectural changes are unmeasurable." — [Shopify Engineering, August 2025](https://shopify.engineering/building-production-ready-agentic-systems)
- **Research report:** ~80% of production AI systems break at agent boundaries. Three survivable handoff principles: (1) structured contracts with validation at receiving side, (2) idempotent retry with task deduplication, (3) structured context packaging with reasoning chains. — [AI Navigate, June 2026](https://ai-navigate-news.com/en/updates/2026-06-22/handoff-failures-break-production-ai-systems)
- **Production field report:** Five CrewAI failure modes in production — agent loops (no termination criteria), token budget overruns (raw context concatenation), hallucinated context handoffs, silent failures, and schema drift. Recommended fix: per-agent output truncation with "summary + reference" pattern, not raw concatenation. — [Markaicode / Inductivee, 2025](https://community.cloud.astra.databricks.com/t5/technical-blog-posts/crewai-production-pitfalls-and-how-to-fix-them/ba-p/125706)
- **Architecture post:** "Agents as independent microservices with well-defined APIs" beats monolith agent architecture. Shared agent registry (not central router) — use-case-specific orchestrators compose agents from the registry. Agent versioning for consumer pinning. Cross-team governance for shared contracts. — [Techspire production lessons, December 2025](https://technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Assuming agents share context they don't.** Each agent operates in its own context window. Passing "obvious" shared context implicitly means the receiving agent reconstructs it — and gets it wrong. Make every handoff self-contained.
- **Adding agents for parallelism when coordination overhead dominates.** More agents mean more handoffs, more failure surface, more schema drift. Parallelism only helps when handoff infrastructure is already solid.
- **Hardcoding schema assumptions at authoring time.** Validation must run at *runtime* on the receiving side — not just checked when the sending agent was written. Non-conforming inputs must be rejected, not silently truncated.
- **Treating retries as free.** Without idempotency, retrying a failed handoff can double-execute a database write, send duplicate emails, or call a paid API twice. Every side-effecting operation in a handoff needs an idempotency key.
- **Benchmarks don't predict handoff quality.** Agent benchmarks (SWE-bench, WebArena) can be gamed with shortcut patterns. Real handoff quality only shows up in production with structured evaluation: human spot checks, A/B testing in staging, cost-per-task tracking. — [Berkeley RDI, April 2026](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont)
