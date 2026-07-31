# S-1907 · The Retry Storm Stack — When Every Failed Tool Call Costs 200× More Than a Successful One

Your agent ran for 47 minutes, made 127 API calls, and produced nothing. A missing retry cap let 1,279 concurrent Claude Code sessions execute 50+ consecutive compaction failures each — burning 250,000 API calls in a single day. No error message. No crash. Just a process that kept trying to succeed and never did. The bill arrived before the cause did.

This is the Retry Storm: a failure mode unique to LLM agents where retry logic doesn't just waste time — it compounds token spend at a rate that bears no resemblance to traditional distributed system retries.

## Forces

- **Agent retries re-process the entire conversation.** A microservice retry costs ~kilobytes. An agent retry at step 10 re-sends 8,000+ tokens of context before the LLM even re-attempts the tool. Ten retries doesn't cost 10× — it costs 200× (Tian Pan, 2026). The LLM also re-reasons about the failure, potentially generating verbose chain-of-thought on each attempt, adding yet another layer of token amplification.

- **Exponential backoff makes it worse.** In distributed systems, backoff spreads retries over time so the system recovers gracefully. In agentic systems, backoff introduces idle time that the LLM fills with more reasoning — more tokens, more cost. The backoff doesn't cap exposure; it just delays when the bill arrives.

- **Retries are invisible until they're catastrophic.** Standard observability tracks successful/failed tool calls, not the cumulative cost of retry chains. An agent retrying a single flaky endpoint 30 times looks like 30 discrete events in your trace — not one escalating incident burning through your budget.

- **The agent isn't broken — it's doing exactly what you told it.** The Claude Code incident wasn't a bug. The agent was executing the recovery logic it was given. The logic just had no ceiling. This is the central paradox: the mechanisms designed to keep agents running are the mechanisms most likely to run them off a cliff.

## The move

**1. Budget-aware retry caps (non-negotiable).** Every tool call needs an explicit max_attempts that halts the entire agent loop, not just the individual call. Cap retries at 2–3, then escalate to human review or dead-letter. A missing ceiling is a runaway bill.

```python
from dataclasses import dataclass, field
from enum import Enum

class Escalation(Enum):
    RETRY = "retry"
    ESCALATE = "escalate"
    ABORT = "abort"

@dataclass
class ToolCallBudget:
    max_retries: int = 3
    max_token_budget: int = 50_000  # input tokens for this task
    max_wall_clock_seconds: int = 300  # 5 minutes

    accumulated_cost: int = 0
    attempt_counts: dict[str, int] = field(default_factory=dict)

    def record_attempt(self, tool_name: str, input_tokens: int) -> Escalation:
        self.accumulated_cost += input_tokens
        self.attempt_counts[tool_name] = self.attempt_counts.get(tool_name, 0) + 1

        if self.accumulated_cost > self.max_token_budget:
            return Escalation.ABORT
        if self.attempt_counts[tool_name] > self.max_retries:
            return Escalation.ESCALATE
        return Escalation.RETRY

budget = ToolCallBudget(max_retries=2, max_token_budget=30_000)

# Inside your agent loop:
escalation = budget.record_attempt("database_query", len(prompt_tokens))
if escalation == Escalation.ABORT:
    raise AgentBudgetExceeded(f"Token budget exceeded: {budget.accumulated_cost}")
elif escalation == Escalation.ESCALATE:
    queue_for_human_review(task_id, failure_context)
    break
```

**2. Idempotent tools as the primary defense.** If every tool call is safe to re-execute, retries become cheap. Use idempotency keys, conditional execution guards, and read-before-write patterns. The goal: a retry of a completed action costs zero additional side effects.

```python
import hashlib, time

class IdempotentTool:
    def __init__(self, tool_fn):
        self.tool_fn = tool_fn
        self.cache = {}

    def call(self, tool_name: str, params: dict, task_id: str) -> dict:
        key = hashlib.sha256(
            f"{tool_name}:{json.dumps(params, sort_keys=True)}".encode()
        ).hexdigest()[:16]

        if key in self.cache:
            return {"cached": True, "result": self.cache[key]}

        # Check if this operation was already completed
        result = self.tool_fn(**params)
        self.cache[key] = result
        return {"cached": False, "result": result}

    def was_already_done(self, tool_name: str, params: dict) -> bool:
        key = hashlib.sha256(
            f"{tool_name}:{json.dumps(params, sort_keys=True)}".encode()
        ).hexdigest()[:16]
        return key in self.cache
```

**3. Event-sourced state so recovery starts from the last clean state, not from scratch.** Every tool call, decision, and output is a log entry with task_id + step_num. The "current state" is the last entry, not a mutable record. On recovery, the agent loads the event log and replays only from the last committed checkpoint.

```python
import json
from datetime import datetime

class AgentEventLog:
    def __init__(self, task_id: str, storage):
        self.task_id = task_id
        self.storage = storage  # Postgres, S3, Redis — whatever

    def append(self, step: dict):
        event = {
            "task_id": self.task_id,
            "step": step["step_num"],
            "tool": step.get("tool"),
            "params": step.get("params"),
            "result": step.get("result"),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.storage.append(event)

    def last_checkpoint(self) -> dict | None:
        events = self.storage.read(self.task_id)
        checkpoints = [e for e in events if e.get("is_checkpoint")]
        return checkpoints[-1] if checkpoints else None

    def resume_from(self) -> int:
        events = self.storage.read(self.task_id)
        return max((e["step"] for e in events), default=0)
```

**4. Cost-aware backoff, not time-based backoff.** Replace exponential backoff with cost-capped backoff: each retry attempt gets a shrinking token budget, not a growing time window. After the second failure, start degrading gracefully (lower model, simpler prompt, human-in-the-loop).

## Receipt

> Verified 2026-07-31 — Research sources: Tian Pan "The Retry Storm Problem in Agentic Systems" (April 10, 2026, tianpan.co); AgentMarketCap "Self-Healing Agent Pipelines 2026" (April 10, 2026); Agent Native "Checkpoint and Resume Pattern for Long-Running Agents" (agentnative.dev, updated 2026-07-26); hailports/self-healing-agent GitHub repo (200-line dependency-free reference implementation); McKennaconsultants "Production AI Agent Observability" (estimated runaway exposure $155K/year per agent fleet with no enforcement). Real incident cited: 1,279 Claude Code sessions ran 50+ consecutive compaction failures — 250K API calls in one day (AgentMarketCap). Pattern confirmed: cost amplification factor of 200× for agentic retries vs. ~10× for microservice retries (Tian Pan). The fix patterns (idempotency keys, budget governors, event sourcing) are confirmed across LangGraph checkpointers, Temporal workflow primitives, Microsoft Agent Framework, and Diagrid Catalyst 2.0.

## See also

- [S-1000 · The Agent Recovery Stack](stacks/s1000-the-agent-recovery-stack-when-your-agent-goes-off-the-rails.md) — Circuit breakers, watchdogs, and recovery ladders for off-rail agents
- [S-1047 · The Agentic Dead Letter Queue](stacks/s1047-the-agentic-dead-letter-queue-when-your-agent-fails-mid-task-and-the-task-just-disappears.md) — What to do with tasks that can't be recovered
- [S-1654 · The Stale Amplification Stack](stacks/s1654-the-stale-amplification-stack-when-caching-makes-wrong-answers-faster.md) — How caching compounds failure (same amplification logic, different axis)
