# S-2258 · The Token Budget Stack — When Your Agent Runs for a Week and Costs More Than Your Engineer

Your agent didn't crash. It didn't error. It ran for eleven days, accumulated $47,000 in API charges, and nobody noticed until the billing statement arrived. You had monitoring. You did not have a kill switch. This is the gap between seeing what your agent costs and controlling what it costs.

## Forces

- **Token cost is not observable until it is catastrophic.** Teams instrument latency and accuracy religiously. Spend-per-task often goes unmeasured until a billing incident. A single agent looping at $0.74/task for 8 hours a day looks fine in monitoring dashboards that don't show cumulative cost.
- **Agents cost ~50x more than a comparable chat call.** Each reasoning step, tool call, intermediate output, and retry consumes tokens. A workflow that seems modest in a 10-message test generates orders of magnitude more spend in a production session. The LeanOps audit (Mar–May 2026) found a 35-engineer team posting an $87,000 monthly bill — with no one having set a per-task cost target.
- **60–85% of AI spend is recoverable.** Prompt caching, model routing, and hard budget enforcement can cut costs dramatically. Teams discover this after the first runaway incident, not before. The recovery is real; the path to finding it is expensive.
- **Monitoring ≠ enforcement.** An alert that fires after the billing cycle closes is a post-mortem tool, not a control. Agents need hard caps that execute, not dashboards that inform.

## The move

Build cost control into the agent runtime as a first-class architectural concern, not a post-launch addition.

- **Hard per-task token budgets.** Set an absolute token cap per agent task invocation — not a soft alert, a hard stop. When the cap is hit, the agent terminates, the task is flagged for review, and the circuit breaker fires. A measured $0.74/task with a $5.00 cap per task means a stuck agent costs $5, not $47,000.
- **Structured output with explicit `max_tokens` per step.** Many "agent rambling" failures are actually a default `max_tokens` of 4096 when the tool arguments only need 200. Cap output tokens per step so the model cannot over-generate when it is confused.
- **Per-agent spend limits at the orchestration layer.** Set spend limits per agent, not per organization. A code-review agent that loops has a $10/day cap. A data-synthesis agent that needs more headroom has a $200/day cap. Limits are enforced by the orchestrator, not by hoping the agent self-limits.
- **Prompt caching as a default, not an optimization.** Read-only tools (knowledge base, RAG, document retrieval) should cache aggressively — cache hits can reach 94% on input tokens. Cache only pure read tools; never cache tools with side effects.
- **Multi-model routing by task complexity.** Route Haiku-class tasks (classification, routing, simple transforms) to cheap models. Route complex reasoning to Opus-class. A measured routing layer can recover 60–85% of spend without degrading output quality — verified by tracking success rate per model per task type.
- **Cost attribution to the task level.** Track spend per agent, per task type, and per user cohort. Without attribution, you cannot know which agent is the budget sink. The LeanOps audit found that without attribution, teams discover cost problems only when the bill arrives.
- **Shadow token accounting.** System prompts, function schemas, safety wrappers, and output format instructions appear in every request but are invisible in back-of-envelope estimates. A typical production agent carries 2,000–5,000 shadow tokens per call. Count them.

## Evidence

- **Incident report:** Multi-agent LangChain system entered a retry loop, ran undetected for 11 days, accumulated $47,000 in API charges — discovered via billing statement, not monitoring. Root cause: no per-agent spend limit, no runtime timeout, no token-anomaly detection. The organization had the right technology; zero runtime infrastructure to detect or stop broken execution. — [Kognita Blog](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch)
- **Field data:** Enterprise AI operational costs average $85,521/month (2025). 60–85% of that spend is recoverable through prompt caching, model routing, and budget enforcement. Runaway incidents range from $15 in 10 minutes to $47,000 over 11 days. — [Zylos Research, 2026-05-02](https://zylos.ai/en/research/2026-05-02-ai-agent-cost-engineering-token-economics/)
- **Production measurement:** A support-ticket agent (5 tools, 800-word average input) was measured before/after optimization: cost dropped from $0.74 to $0.09 per task (88% reduction) through caching (94% input cache hit), structured output, and step reduction (14 steps → 9 steps). Latency improved 63%. Success rate improved 10%. — [AnhTu.dev, 2026](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **Enterprise survey:** 4.7 distinct models per enterprise account in 2026 (up from 2.1 in Q1 2025). 38% of enterprise token volume on open-source models. Enterprise token costs dropped 67% year-over-year through multi-model routing and caching discipline. — [RockB Blog, 2026-05-13](https://baeseokjae.github.io/posts/ai-developer-cost-optimization-2026)

## Gotchas

- **Alerting without enforcement is theater.** Teams add spend alerts to dashboards and feel covered. The $47,000 incident had "monitoring" — it did not have a kill switch. Add both, or accept that your budget is a suggestion.
- **The dev-to-production multiplier is 2–5x.** Dev uses toy data and short conversations. Production has full history, larger inputs, more tool calls, and longer outputs. Estimate budgets based on production traces, not prototype sessions.
- **Default `max_tokens` is a hidden cost amplifier.** Leaving it at 4096 means a confused agent can generate up to 4096 output tokens per step — far more than needed for a tool call that should produce 200 tokens of structured JSON. Set it explicitly per tool.
- **Model routing without attribution is guesswork.** Without per-model, per-task cost tracking, you cannot know whether the "cheaper model" actually handles the task at the same quality level. Route first, then measure success rate per route to confirm the savings.
