# S-1011 · The Rate-Limited Multi-Agent Pattern — When All Your Agents Attack Your API Quota Together

Nine agents, one API quota. Each agent has its own retry logic. Within 90 seconds of launch, all nine hit the rate limit simultaneously, back off for the same duration, and hit it again in unison. Your 5,000 requests/hour budget is exhausted in minutes. Recovery takes an hour. This is not a bug in any individual agent — it is a coordination failure that emerges from the interaction of N independently-reasoning retry loops.

## Forces

- **Independent retry logic compounds, not resolves, the problem.** Each agent's retry strategy optimizes for its own success. When N agents share a quota, independent backoff produces synchronized retry waves that amplify the very limit they're trying to honor.
- **Rate limits are invisible until they aren't.** Agents don't know their siblings exist. The shared quota — and the blast radius of exhausting it — only becomes visible at the infrastructure layer, which the agents never see.
- **Priority doesn't survive shared infrastructure.** A background monitoring agent and a user-facing transaction agent both see a 429, both retry after the same `Retry-After`, and both succeed — unless the quota runs out first. When it does, the monitoring agent gets its request through while the transaction agent fails. The wrong agent wins.
- **Token budgets and rate limits are not the same constraint.** An agent can stay within its own token budget while a sibling exhausts the shared rate limit. Cost controls and rate controls operate on different axes and need different solutions.

## The Move

**Centralize rate limit management at the orchestration layer, not inside individual agents.**

### 1. The Rate-Limit Coordinator as a Shared Service

Pull all rate-limit awareness out of agents and into a single coordinator. Agents request permission to call; the coordinator tracks consumption across the fleet.

```python
import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

@dataclass
class RateLimitWindow:
    limit: int          # max requests in window
    window_seconds: float
    requests: deque = field(default_factory=deque)

    def allow(self) -> bool:
        now = time.monotonic()
        # Evict expired entries
        cutoff = now - self.window_seconds
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

        if len(self.requests) < self.limit:
            self.requests.append(now)
            return True
        return False

    def retry_after(self) -> float:
        """Seconds until oldest request in window expires."""
        if not self.requests:
            return 0.0
        return max(0.0, self.window_seconds - (time.monotonic() - self.requests[0]))


class RateLimitCoordinator:
    """Shared rate-limit gate for multi-agent systems."""

    def __init__(self):
        self._limits: dict[str, RateLimitWindow] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def register(self, endpoint: str, limit: int, window_seconds: float):
        self._limits[endpoint] = RateLimitWindow(limit, window_seconds)
        self._queues[endpoint] = asyncio.Queue()
        self._semaphores[endpoint] = asyncio.Semaphore(limit)

    async def acquire(self, endpoint: str, timeout: float = 30.0) -> bool:
        """Returns True when the call is permitted. Blocks until slot available or timeout."""
        if endpoint not in self._limits:
            return True  # Untracked endpoints pass through

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._limits[endpoint].allow():
                return True
            wait = min(
                self._limits[endpoint].retry_after() + 0.1,
                deadline - time.monotonic()
            )
            await asyncio.sleep(wait)
        return False

    async def call(self, endpoint: str, fn, *args, **kwargs):
        """Guaranteed-rate call: waits for quota, then executes."""
        permitted = await self.acquire(endpoint)
        if not permitted:
            raise RuntimeError(
                f"Rate limit exceeded for {endpoint} after timeout. "
                f"Consider splitting into separate endpoint quotas."
            )
        async with self._semaphores[endpoint]:
            return await fn(*args, **kwargs)


# Usage: single shared coordinator, injected into all agents
coordinator = RateLimitCoordinator()
coordinator.register("github.com", limit=60, window_seconds=60.0)   # 60 req/min
coordinator.register("openai.com", limit=500, window_seconds=60.0)   # 500 req/min
```

### 2. Priority-Based Quota Partitioning

Split a shared quota by agent class so critical agents survive even when background agents are throttled.

```python
class PartitionedRateLimit:
    """Subdivide a rate limit across priority tiers."""

    def __init__(self, total_limit: int, window_seconds: float):
        self.tiers = {}
        self._total = total_limit
        self._window = window_seconds

    def add_tier(self, name: str, share: float):
        # share is proportion (0.0–1.0), allocated as count
        count = max(1, round(self._total * share))
        self.tiers[name] = RateLimitWindow(count, self._window)

    async def acquire(self, tier: str) -> bool:
        if tier not in self.tiers:
            # Unnamed tier gets no guaranteed allocation
            return False
        return self.tiers[tier].allow()

    async def acquire_or_fallback(
        self, tier: str, fallback_tier: str
    ) -> bool:
        """Try tier, fall back to lower-priority tier if needed."""
        if await self.acquire(tier):
            return True
        return await self.acquire(fallback_tier)


# GitHub: 100 req/min shared, partitioned by priority
gh_limits = PartitionedRateLimit(100, 60.0)
gh_limits.add_tier("transaction", 0.60)   # 60 req/min for user-facing
gh_limits.add_tier("background", 0.30)    # 30 req/min for batch
gh_limits.add_tier("polling", 0.10)        # 10 req/min for monitors
```

### 3. Token-Aware Cost Budgets (Not Just Rate Limits)

Track both rate limits and cumulative token spend so cost anomalies trigger before quotas are exhausted.

```python
@dataclass
class CostBudget:
    max_tokens: int
    used_tokens: int = 0

    def reserve(self, tokens: int) -> bool:
        if self.used_tokens + tokens <= self.max_tokens:
            self.used_tokens += tokens
            return True
        return False

    def refund(self, tokens: int):
        self.used_tokens = max(0, self.used_tokens - tokens)

class MultiDimensionalBudget:
    """Track rate limits AND token budgets simultaneously."""

    def __init__(self):
        self.cost: CostBudget = CostBudget(max_tokens=10_000_000)  # 10M tokens/month
        self._rate_limits: dict[str, RateLimitWindow] = {}

    async def reserve(self, endpoint: str, estimated_tokens: int) -> bool:
        # Check both dimensions before any call
        if not self.cost.reserve(estimated_tokens):
            return False
        if endpoint in self._rate_limits and not self._rate_limits[endpoint].allow():
            self.cost.refund(estimated_tokens)
            return False
        return True

    def burndown(self) -> dict:
        return {
            "tokens_remaining": self.cost.max_tokens - self.cost.used_tokens,
            "tokens_used_pct": self.cost.used_tokens / self.cost.max_tokens * 100,
            "rate_limits": {
                name: {
                    "available": w.limit - len(w.requests),
                    "total": w.limit,
                }
                for name, w in self._rate_limits.items()
            }
        }
```

## Receipt

> Verified 2026-07-12 — Pattern synthesized from Tamir Dresher's "9 AI Agents, One API Quota" (March 2026), AgentMarketCap's "Concurrent Multi-Agent State Management" (April 2026), Zylos Research's "AI Agent Self-Healing and Failure Recovery" (May 2026), and sudoall.com's multi-agent coordination playbook (June 2026). The thundering herd failure (9 agents → 10 PRs in 22 min → 60+ chained 429s), priority inversion problem, and resource contention taxonomy are documented production incidents. The coordinator pattern and code examples are synthetic constructions based on the described patterns; Receipt pending — run against a live multi-agent fleet to confirm isolation behavior.

## See also

- [S-986 · The Coordination Breakdown Pattern](stacks/s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — broader coordination failure taxonomy; this entry is the specific rate-limiting slice
- [S-1005 · AI SRE: Behavioral SLOs, Error Budgets, and Incident Taxonomy](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the observability layer that detects rate-limit-driven degradation
- [S-362 · Budget-Aware Agents](stacks/s362-budget-aware-agents.md) — cost budgets vs. rate budgets (this entry's token axis)
