# S-2275 · The Token Budget Stack — When Your Agent Will Spend Until the Money Runs Out

You ship an agent. It works. Then the invoice arrives. The problem is not cost-per-token — it dropped ~80% in 18 months. The problem is token volume: agents make 3–10× more LLM calls than chatbots, and without hard controls, they will spend until the money runs out. A 4-agent LangChain loop once ran 11 days and produced a $47,000 bill. Nobody noticed until it was over.

## Forces

- **Agents are unbounded cost optimizers.** Given a task, an agent will keep calling the LLM until the task is done — regardless of accumulated spend. Unlike humans who check the clock, agents have no built-in cost awareness.
- **The cost curve is quadratic in conversation length.** As context grows, cache reads — which providers charge at ~10% of base input rate — begin to dominate total spend. At 50,000 tokens, cache read costs often exceed inference costs. Teams that didn't model this find their cost-per-turn doubling silently.
- **Routing gains dwarf other optimizations.** A ~100× price spread exists between cheapest and most capable models. This is larger than the gains from caching, compression, or batch processing combined. Most teams leave it on the table because routing adds perceived complexity.
- **Alerts don't prevent overspend.** Budget alerts fire after spending has occurred. In a loop scenario, the damage is already done. Enforcement — hard pre-call blocks — is what actually stops runaway agents.

## The Move

Treat token spend as a first-class engineering variable with three interlocking controls:

- **Model routing: send each request to the cheapest capable model.** RouteLLM (ICLR 2025) achieved 85% cost savings at 95% GPT-4 quality on MT Bench, with the strong model needed on only 14% of queries. Five routing strategies matter in production: rule-based (fastest, lowest overhead at <1ms), embedding-based (~5ms), intent-based (classify before routing), cascading (fallback chains), and load-balancing. Start with rule-based and add sophistication only when eval data shows quality regressions.

- **Hard cost caps with pre-call enforcement, not post-hoc alerts.** Block the LLM call *before* it executes if the budget is exceeded. Use per-agent, per-session, and per-fleet limits. The key primitive is a BudgetLedger that atomically decrements before each call and rejects requests that would exceed the ceiling. Tools like llm-budget (GitHub, MIT) and veronica-core provide this as a runtime containment kernel. Per-user spend tracking with automatic blocking is the only reliable way to prevent individual users from running up $50 sessions.

- **Caching as a compounding multiplier.** Prompt caching provides ~90% discount on cached tokens. Semantic caching skips LLM calls for near-duplicate inputs. Combined with model routing, teams report 60–80% token spend reduction. Tag every LLM call with feature/workflow identifier, user segment, agent name and version, and task type — this attribution data enables cost-aware product decisions and identifies efficiency regressions before they compound.

- **Context window management as a cost lever.** Agents that read files in chunks vs. full reads change both the cost curve and quality. For agentic tasks, a single full read at the start often beats paginated reads: it avoids redundant context re-processing and lets the model see the full picture. Use context truncation policies that expire old turns once they exceed a threshold, not just when the window fills.

- **Output length constraints and stop conditions.** Agent tasks often generate verbose reasoning traces that inflate output tokens at 5× the input rate. Token-per-request caps (via provider limits or client-side truncation) combined with explicit stop conditions (max iterations, max tool calls) prevent runaway output generation.

## Evidence

- **Research paper:** RouteLLM (ICLR 2025) — 85% cost savings at 95% GPT-4 quality on MT Bench; strong model required on only 14% of queries — https://arxiv.org/abs/2406.11028
- **Engineering blog:** Waxell — 4 LangChain agents ping-ponged for 11 days in November 2025, $47,000 bill; "alerts don't stop runaway agents — enforcement does" — https://www.waxell.ai/blog/ai-agent-token-budget-enforcement
- **Engineering blog:** exe.dev — quadratic cost curve: at 50K tokens, cache reads dominate API call costs; input/output/cache cost ratios from Anthropic Opus pricing — https://blog.exe.dev/expensively-quadratic
- **Research report:** Zylos Research (April 2026) — 96% of enterprises report costs exceeded projections; full-stack optimization yields 60–80% token spend reduction — https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing
- **Engineering guide:** Digital Applied (June 2026) — ~100× price spread between cheapest and most capable models makes routing the largest cost lever; five production-ready tools; <1ms router overhead vs 500–2,000ms LLM inference — https://www.digitalapplied.com/blog/llm-model-routing-2026-cost-quality-optimization-engineering-guide
- **GitHub:** mattbusel/llm-budget — open-source Rust primitives for hard budget enforcement across agent fleets; BudgetLedger with hard/soft limits, FleetGovernor for cross-agent aggregation — https://github.com/Mattbusel/llm-budget

## Gotchas

- **Routing degrades quality on long-tail tasks.** The 14% of queries needing the frontier model are not randomly distributed — they cluster around edge cases, novel domains, and adversarial inputs. RouteLLM's 95% quality figure is benchmark-averaged; your traffic mix may differ. Always run parallel evals on routed vs. non-routed traffic before shipping.
- **Hard caps create failure modes of their own.** A hard cap mid-task leaves the agent in a partially completed state with no clear recovery path. Design rollback: when a hard limit triggers, return a structured "budget_exceeded" response with the partial result and required action, not a silent failure.
- **Per-user caps require identity resolution.** Without stable user identifiers tied to each request, per-user spend tracking is impossible. Agents that multiplex sessions under a shared key will accidentally share budgets across users, or fail to attribute spend correctly.
- **Batch API and prompt caching require compatible workloads.** Batch API offers 50% discounts but has latency trade-offs (hours-long turnaround). Prompt caching requires session continuity — it breaks on stateless request patterns. Neither applies to one-off agent tasks that don't repeat context.
