# S-2857 · The Circuit Breaker Stack

When your agent silently drains $47,000 in 11 days while returning HTTP 200 and nobody notices until the bill arrives — or when you lose $200 to a single loop and build a product from the scar tissue.

## Forces

- **Agents fail without throwing errors.** A loop that returns HTTP 200 and produces nothing still costs tokens. The standard "is it crashing?" health check misses the most expensive failure mode.
- **Multiplication is the real threat.** One $5 Opus call looks fine. 100 of them looks fine individually. In aggregate they cost hundreds — and rate limits don't help because the requests themselves are normal-sized.
- **Provider account caps are backstops, not solutions.** They stop the bleeding but can't identify which task failed, save partial state, or stop one loop without taking down unrelated agents.
- **The gap between what "normal" costs and what "runaway" costs is invisible until it isn't.** Teams discover their budget model is wrong the hard way — when the invoice arrives.
- **Build costs are estimated well; operational costs are consistently underestimated.** Agentic systems include categories traditional software doesn't: prompt maintenance, eval labor, human review that persists post-launch, and periodic re-evaluation as providers update models.

## The Move

**Layer five hard limits at the orchestration level, before the agent ever runs.**

1. **Pre-call budget gate.** Reserve capacity before every model call — don't just check whether you have account credit, check whether this specific run has headroom. Record actual token usage after every call.

2. **Per-run spending cap.** Set a hard dollar limit per task or per session, independent of the account-level cap. This is the circuit breaker that stops one runaway loop from taking down the whole system.

3. **Multi-axis stopping signals.** Budget gates are necessary but not sufficient — track five signals together: iteration count, wall-clock time, cost delta (change in spend since last meaningful output), error count, and context utilization ratio.

4. **Cost velocity monitoring.** Single snapshots miss slow bleeds. Measure spend over time — agents that accumulate cost gradually (context growing, same tool called repeatedly with no new output) are just as dangerous as explosive loops.

5. **Graceful degradation on trip.** When a circuit breaker trips, capture partial state and surface a meaningful error — not just "exceeded limit." Partial output + clear signal is worth more than silence.

## Evidence

- **DEV Community engineering post:** A team running 9 agents across ~62 scheduled jobs daily (normal spend $15–20/day, $600/month budget) suffered a LangChain retry loop that ran for 11 days before detection. Final bill: **$47,000**. Reddit shared a similar incident at **$30,000**. Root cause in both cases: many individually-normal requests multiplied into an invisible cost spiral — rate limits would not have caught it. — [DEV Community: The Cost Circuit Breaker](https://dev.to/sebastian_chedal/the-cost-circuit-breaker-how-we-prevent-runaway-spending-across-9-ai-agents-4i5k)

- **Show HN post:** A developer left an agent running unattended and lost **$200** to a looping request pattern. The incident directly motivated building per-tool AI budget controls as a product. — [Hacker News: I lost $200 from an agent loop](https://news.ycombinator.com/item?id=46991656)

- **GitHub / engineering blog:** AgentBreaker (open-source, 2026) monitors token spend, iteration count, and cost velocity across multi-step LLM orchestration at the orchestration layer — "most teams only set max_tokens on a single LLM call. AgentBreaker works across multiple LLM calls." AgentBrake (MIT license) offers circuit breaking in 3 lines of code for LangChain/LangGraph. — [GitHub: AgentBreaker](https://github.com/vixde8/agentbreaker), [GitHub: AgentBrake](https://github.com/BOSSMETALIQUE/agentbrake)

## Gotchas

- **Setting `max_tokens` on a single LLM call is not a circuit breaker.** It controls one response, not a multi-turn loop. The budget needs to live at the orchestration layer, above the individual calls.
- **Cost accumulation is often slow before it's catastrophic.** The $47k incident ran 11 days — not an explosive spike. Measure spend delta over time, not just absolute spend.
- **Per-run caps are more useful than account-level caps for debugging.** Account caps protect you from total ruin; per-run caps tell you *which task* failed and let you save partial state.
- **Error loops are distinct from cost loops.** An agent can loop without spending much (hitting a cheap endpoint repeatedly) or spend without looping (one very large call). Budget controls need to catch both shapes — cost and iteration are separate axes.
- **Build-time budgets are not the same as run-time budgets.** The AI Agentic Engineering Academy notes that initial budgets consistently underestimate ongoing operational costs (prompt maintenance, eval labor, human review overhead, model re-evaluation). Budget for the second year, not just the first.
