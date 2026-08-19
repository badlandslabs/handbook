# S-2862 · The Token Budget Circuit Breaker Stack — When Your Agent Burns $50,000 and Logs Show No Errors

Your agent ran for 5 hours. Logs: zero errors. Status: HTTP 200, healthy. The bill: $41,000. A self-evaluation loop consumed 1.67 billion tokens generating an output nobody asked for. No alert fired because no alert condition was ever met. This is not a monitoring gap — it is a missing layer of the stack. You need a token budget circuit breaker.

## Forces

- **Agents fail forward.** Unlike a crashed service, an agent that loops keeps returning 200. Traditional APM (error rate, latency p99, CPU saturation) was designed for crashes. None of those metrics detect a $4,000/hour recursion loop that produces syntactically valid output.
- **Cost compounds super-linearly with loop depth.** A self-evaluation bug — the agent flagging its own output as "needs more detail" on an already-sufficient response — creates a refinement loop. Each iteration adds the previous output to context. By iteration 30, each round costs $80-90. The last 17 iterations cost more than the first 30 combined.
- **Agent spend is invisible by default.** Token cost is scattered across model API calls, tool calls, context growth, and sub-agent fan-outs. Standard FinOps dashboards aggregate by service, not by task or run. You cannot control spend you cannot attribute.
- **Per-run budget enforcement must be non-negotiable.** Soft alerts (2× p95, notify) and hard stops (5× p95, halt) must be implemented at the orchestration layer — not as optional configuration. Every framework ships with "infinite loops are possible" by default.

## The Move

**Layer 1 — Per-Task Budget Cap (hard stop)**
Set a token-and-dollar ceiling per individual task run. Any single agent invocation that exceeds the cap gets killed immediately. State is checkpointed so you can inspect where it diverged. Hard caps prevent the catastrophic blowup — the $41,000 incident — while allowing normal variation.

```python
class TokenBudgetCircuitBreaker:
    def __init__(self, soft_usd: float, hard_usd: float, soft_tokens: int, hard_tokens: int):
        self.soft_usd = soft_usd
        self.hard_usd = hard_usd        # e.g. $15.00 per task
        self.soft_tokens = soft_tokens  # e.g. 50_000 tokens
        self.hard_tokens = hard_tokens  # e.g. 200_000 tokens
        self._tripped = False
        self._trip_reason = None

    def check(self, run_record: RunRecord) -> "TripResult":
        """
        Called after every LLM call + tool execution cycle.
        Returns TripResult indicating: OK, SOFT_TRIP, or HARD_TRIP.
        """
        cost = run_record.cumulative_cost_usd
        tokens = run_record.total_tokens_consumed

        if cost >= self.hard_usd or tokens >= self.hard_tokens:
            self._tripped = True
            self._trip_reason = f"hard_cap_exceeded: ${cost:.2f}, {tokens:,} tokens"
            return TripResult.HARD_TRIP  # kill run, capture checkpoint

        if cost >= self.soft_usd or tokens >= self.soft_tokens:
            return TripResult.SOFT_TRIP   # alert, log, continue

        return TripResult.OK

    def checkpoint_state(self, agent_state: dict) -> str:
        """Serialize agent memory + context for post-mortem debugging."""
        import json, uuid
        checkpoint_id = str(uuid.uuid4())
        with open(f"/tmp/agent_checkpoint_{checkpoint_id}.json", "w") as f:
            json.dump({"state": agent_state, "reason": self._trip_reason}, f)
        return checkpoint_id
```

**Layer 2 — Per-Agent Rolling Budget (24h window)**
Aggregate spend per agent per rolling 24-hour window. Prevents slow-burn cost accumulation where individual runs stay under budget but the agent is called 500 times a day with a per-call leak. Trigger alerts at 80% of daily quota, halt at 100%.

**Layer 3 — Global Kill Switch**
A cluster-level circuit breaker that halts all agent runs when total spend crosses a threshold (e.g., $10,000/day across all agents). This is the last resort against cascade failures where one agent's loop triggers downstream agent runs that compound the blowup. Implement as a feature flag with a human-readable name — `FEATURE_AGENT_RUNS_ENABLED` — so any team member can flip it.

**Layer 4 — Cost Attribution Per Task**
You cannot optimize what you cannot see. Tag every agent run with: task type, user/customer ID, model, and agent version. Emit cost per run as a first-class metric (not an afterthought log). Route to your FinOps dashboard. Set p50 and p95 baselines per task type over 2-3 weeks, then set soft caps at 2× p95, hard caps at 5× p95.

**Layer 5 — Loop Detection via Cost Velocity**
A budget circuit breaker alone is reactive — it trips after cost is already accumulating. Add a cost-velocity check: if tokens-per-minute exceeds 3× the rolling average for the current task type, trip immediately. The $4,217 overnight Planner incident saw costs jump from ~$3/call to $80-90/call in iteration 30 — a 25× velocity spike that should have triggered a kill before iteration 40.

## Receipt
> Verified 2026-08-19 — DevOS blog (devos.team) documents a $4,217.43 overnight incident with 47 iterations, escalating cost per round. AgentMarketCap documents the $16k-$50k Claude Code recursion incident (1.67B tokens, July 2025). CloudZero data shows agents use ~4× tokens vs. chat, multi-agent ~15×. AgentBreaker (github.com/vixde8/agentbreaker) is an open-source real-time circuit breaker implementation. DevOS recommends p50/p95 baseline → soft at 2× p95 → hard at 5× p95. Circuit breaker must preserve state for post-mortem — kills without checkpoints lose all debugging signal.

## See also
- [S-1003 · Agent Failure Recovery Stack](/stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — loop detection and cost spirals are the failure modes this pattern prevents
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — error budgets for agents are the organizational layer above this enforcement mechanism
- [S-200 · Agent Reliability Compounding](/stacks/s200-the-agent-reliability-compounding-problem-or-why-your-agent-team-keeps-getting-less-reliable-as-you-add-capabilities.md) — cost compounds multiplicatively just like reliability compounds inversely
