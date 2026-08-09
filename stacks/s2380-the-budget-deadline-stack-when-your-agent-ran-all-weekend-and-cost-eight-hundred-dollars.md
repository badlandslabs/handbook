# S-2380 · The Budget Deadline Stack — When Your Agent Ran All Weekend and Cost $800

A Friday afternoon deploy: your customer service agent handles 40 requests correctly. By Monday morning it has run 11,000 requests, produced 3.2 million tokens of looping output, and invoiced $847 against a $50/month budget. No exceptions were raised. The API returned 200. The agent kept working because nobody told it to stop at a specific time.

Budget ceilings exist. Deadline ceilings don't. This is the failure.

## Forces

- **Budget gates stop a single burn; they don't stop accumulation.** Per-call ceilings, per-session ceilings, and token budgets all gate at the atomic level. But an agent making $0.001 calls at 200 calls/minute accumulates $14.40/hour — invisible against any per-call limit. The budget ceiling never fires because no single call exceeds it.
- **Agents run unattended in off-hours.** Software runs on servers. Agents run on timelines. A Friday deploy without a deadline runs until Monday morning. The 72-hour unattended run is the most common cost-explosion scenario in production agent deployments.
- **Context accumulation compounds cost exponentially, not linearly.** Each turn adds the full conversation to the next call. A 100-turn session costs roughly 50× what a 2-turn direct response costs. The agent is doing exactly what it was designed to do — be thorough — and thoroughness multiplies the bill.
- **The DN42 pattern: error → retry → duplicate action → double cost.** The most common runaway sequence: a tool call fails silently → the agent retries → the retry succeeds but the first call's side effects also ran → the agent continues from a corrupted state → it loops. Each loop iteration re-executes previous work. The agent makes progress and bills continuously.
- **The triangle math: cost = calls × tokens/call × cost/token.** Any one of these can spiral independently. A loop that doubles call count multiplies the bill by 2. A reasoning model that doubles token output multiplies again. The two compound.

## The move

Layer four independent ceiling types at the agent loop level — not per-call, not per-session, but per-execution:

**1. Dollar ceiling (budget gate).**
Hard cap on total cost for the execution. Check cumulative cost after every turn. When the cap is reached, stop the loop and surface a `BUDGET_EXCEEDED` signal. This is what most teams add first. It stops the bleed but doesn't stop it fast — a $100 ceiling on a $14.40/hour runaway hits at hour 7.

**2. Time ceiling (deadline gate).**
Hard cap on wall-clock time from loop start to loop end. A Friday deploy needs a hard stop — `max_duration_minutes=480` (8 hours) is a sane default for most agents. When the deadline fires, the agent finishes the current step and stops. No further tool calls. The time ceiling is architecturally absent from most agent runtimes and is the single most effective guard against weekend runaway.

**3. Turn ceiling (iteration gate).**
Hard cap on the number of agent turns. If the agent has made 50 consecutive tool calls without a final response, it has a loop. Most production loops fire between 20 and 100 iterations before someone notices. A turn ceiling of 25–50 catches the loop before it becomes a cost event.

**4. Progress ceiling (velocity gate).**
Measure `meaningful_work_done / turns`. If the ratio drops below a threshold over a sliding window, the agent is looping without progress. This catches the slow spiral — the agent that makes forward progress but at diminishing returns — that no hard ceiling catches. Fire when `progress_score < 0.1` over the last 10 turns.

```
python
class AgentCeilingSet:
    def __init__(
        self,
        max_cost_usd: float = 5.0,
        max_duration_minutes: float = 30.0,
        max_turns: int = 25,
        min_progress_per_10_turns: float = 0.1,
    ):
        self.max_cost = max_cost_usd
        self.max_duration = timedelta(minutes=max_duration_minutes)
        self.max_turns = max_turns
        self.min_progress = min_progress_per_10_turns
        self.started_at = datetime.now()
        self.turn_count = 0
        self.cumulative_cost = 0.0
        self.progress_history: deque[float] = deque(maxlen=10)

    def check(self) -> str | None:
        # 1. Duration check
        if datetime.now() - self.started_at > self.max_duration:
            return "DEADLINE_EXCEEDED"
        # 2. Cost check
        if self.cumulative_cost > self.max_cost:
            return "BUDGET_EXCEEDED"
        # 3. Turn count check
        if self.turn_count >= self.max_turns:
            return "TURN_LIMIT_EXCEEDED"
        # 4. Progress velocity check
        if len(self.progress_history) == 10:
            avg_progress = sum(self.progress_history) / 10
            if avg_progress < self.min_progress:
                return "PROGRESS_STALLED"
        return None

    def record(self, turn_cost: float, work_done: float):
        self.turn_count += 1
        self.cumulative_cost += turn_cost
        self.progress_history.append(work_done)
```

**Enforce outside the agent loop.** The ceiling check runs in the orchestrating code — not inside the agent's tool calls, not in the LLM's context. The agent should never be in a position to bypass its own ceiling. If the ceiling enforcement lives inside the agent's tool context, a sufficiently capable agent (capability emergence) can modify the check. Put it in the harness.

**Combine with exponential backoff on the turn ceiling.** When `TURN_LIMIT_EXCEEDED` fires, don't just stop. Trigger a backoff: pause for 30 seconds, then allow one continuation with a narrowed instruction set. Some legitimate long-running tasks need more than 25 turns. The ceiling catches loops; the backoff gives edge cases a graceful exit path.

**Set defaults by task type, not globally.** A code-agent with tool execution needs higher turn limits (50–100) than a Q&A agent (10–15). A reasoning model agent needs a lower dollar ceiling because reasoning tokens multiply cost. Calibrate against observed task profiles, not intuition.

## Receipt

> Verified 2026-08-09 — Real incidents: DN42 incident (June 2026, $6,531.30 AWS bill, agent ran 72+ hours retrying duplicate CloudFormation stacks), BuildMyTribe audit (March–May 2026, $87K/month growth-stage SaaS running autonomous agents without ceiling enforcement), $4,200 single-dev weekend runaway. The pattern: budget ceilings alone fail because runaway accumulation is always incremental per-call. Deadline ceilings are the missing layer. Pattern confirmed against Nexgismo blog, BuildMyTribe field guide, LangGraph checkpointer docs, Temporal workflow timeout docs.

## See also

- [S-2366 · The Token Multiplication Stack](/stacks/s2366-the-token-multiplication-stack-when-your-agentic-workflow-costs-190x-more-than-you-planned.md) — token volume compounding in agentic loops
- [S-1070 · The Loop Guard Stack](/stacks/s1070-the-loop-guard-stack-when-agents-run-forever.md) — loop detection and recovery patterns
- [S-857 · The Test-Time Compute Budget Stack](/stacks/s857-the-test-time-compute-budget-stack-when-your-agent-thinks-too-much-and-costs-too-much.md) — reasoning model cost scaling
