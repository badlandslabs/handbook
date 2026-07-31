# S-1942 · The Agent Failure Recovery Stack

*When your agent completes successfully and everything is broken — and you have no way to undo it, detect it, or stop it from happening again.*

Your agent finishes a batch job, returns HTTP 200, and produces output that looks correct. Twelve hours later you learn it deleted the wrong S3 prefix, hallucinated a refund policy, and charged three customers for orders that were never placed. The agent "completed successfully" on every metric your dashboard was watching. This is not a bug. It is the default behavior of production AI agents in 2026.

## Forces

- **Agents fail with the confidence of success.** Unlike a crashed API or a 500 error, a degraded agent produces outputs that look plausible. Standard APM — error rates, latency, HTTP status — is blind to this class of failure.
- **The blast radius grows with autonomy.** The more the agent can write, delete, send, or execute, the more catastrophic each silent failure becomes. The agent that handles read-only research is low-risk; the one that touches your database is not.
- **Rollback is not a database concept anymore.** Agents execute across multiple systems simultaneously — a database write, an email, an API call — with no shared transaction boundary. A `DROP TABLE` inside an agent is not a rollback problem; it is a backup restore problem.
- **"Done" is not a model concept.** LLMs have no intrinsic sense of completion. The model keeps generating until the context fills or it hits a stop token. An agent that should have stopped at step 5 will happily continue to step 500, burning tokens and repeating tool calls.
- **Failures cascade invisibly.** An error at step 2 propagates into a wrong decision at step 8. By the time the output reaches the user, the causal chain is unreadable from the surface.

## The move

### 1. Classify every tool by blast radius before giving it to an agent

Tag tools as **read-only**, **side-effect-light** (sends emails, creates records), or **destructive** (deletes, overwrites, migrates). Destructive tools require pre-execution confirmation gates regardless of how confident the agent appears.

```python
TOOL_TAGS = {
    "s3_delete": ["destructive", "irreversible"],
    "db_execute": ["destructive", "requires_checkpoint"],
    "send_email": ["side-effect-light"],
    "rag_query": ["read-only"],
}

def requires_guardian_check(tool_name):
    tags = TOOL_TAGS.get(tool_name, [])
    return "destructive" in tags or "requires_checkpoint" in tags
```

### 2. Checkpoint state before every destructive operation

Serialize the agent's working state and the target system's pre-mutation snapshot before any write. Rollback targets a known-good state, not a diff.

```python
def execute_with_checkpoint(agent_state, tool_call, target_system):
    checkpoint = target_system.snapshot()          # pre-mutation image
    step_id = record_step(agent_state, tool_call, checkpoint)  # durable log

    result = tool_call.execute()

    if result.is_destructive and not result.confirmed:
        target_system.restore(checkpoint)
        emit_alert("destructive_tool_reverted", step_id=step_id)
        return result

    return result
```

This pattern — [snapshot → execute → confirm → commit or revert](https://agentmarketcap.ai/blog/2026/04/11/agent-checkpoint-rollback-engineering-2026) — appears across production teams working on agent rollback engineering in 2026. The Replit database deletion incident ([DROP TABLE with no confirmation gate](https://tianpan.co/blog/2026-04-20-ai-agent-data-rollback-production)) is the canonical example of what happens without it.

### 3. Detect loops with action-sequence fingerprinting

Track a rolling hash of the last N tool calls (tool name + key arguments). If the same fingerprint appears more than 2–3 times in a sliding window, the agent is looping — regardless of what it says it is doing.

```python
from collections import deque
import hashlib

class LoopDetector:
    def __init__(self, window=5, threshold=2):
        self.history = deque(maxlen=window)
        self.threshold = threshold

    def record(self, tool_name, args):
        fingerprint = hashlib.md5(
            f"{tool_name}:{sorted(args.items())}".encode()
        ).hexdigest()[:12]
        count = sum(1 for f in self.history if f == fingerprint)
        self.history.append(fingerprint)
        return count >= self.threshold  # True = loop detected
```

Loops are [repeat failures, not model failures](https://matrixtrak.com/blog/agents-loop-forever-how-to-stop). Prompts can nudge behavior but cannot enforce budgets. The solution is structural: step limits, token budgets, and circuit breakers.

### 4. Implement tiered circuit breakers

```python
class CircuitBreaker:
    def __init__(self):
        self.tool_errors   = Counter()   # per-tool error counts
        self.global_errors = 0
        self.tool_limit   = 3           # trips per tool
        self.global_limit = 10          # trips entire run

    def record(self, tool_name, error):
        self.tool_errors[tool_name] += 1
        self.global_errors += 1

        if self.tool_errors[tool_name] >= self.tool_limit:
            raise ToolCircuitOpen(f"Tool '{tool_name}' exceeded error limit")
        if self.global_errors >= self.global_limit:
            raise GlobalCircuitOpen("Run exceeded total error budget")
```

From [Agents.NET on production error handling](https://agents.net/blog/ai-agent-debugging-error-handling-production): "A single agent interaction might involve parsing user intent, retrieving context from a vector database, calling an external API tool, generating a response with an LLM, validating that response against grounding sources, and formatting the final output. Each step introduces distinct failure modes, and an error at any stage can cascade through the entire pipeline."

### 5. Expose structured run logs — not just outputs

Every agent step should emit: tool called, arguments, result, timestamp, token count. This is the minimum required to reconstruct causality after a silent failure. Without execution traces, you're debugging blind.

```python
StepLogEntry(
    step=4,
    tool="db_execute",
    args={"sql": "UPDATE orders SET status='shipped' WHERE id=1234"},
    result="success",
    duration_ms=84,
    tokens_used=1247,
    error=None
)
```

### 6. Use exponential backoff with jitter for external tool calls

```python
def call_with_backoff(tool_fn, max_attempts=4):
    for attempt in range(max_attempts):
        try:
            return tool_fn()
        except (RateLimitError, TimeoutError) as e:
            if attempt == max_attempts - 1:
                raise
            sleep = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(sleep)
```

External tools (web search, DB queries, APIs) timeout or throttle. Naive agents block indefinitely or retry in tight loops. [Exponential backoff with jitter](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it) reduces both the retry storm and the aggregate load on the failing service.

## Evidence

- **Engineering blog (AgentMarketCap, April 2026):** Documented the rollback engineering pattern — snapshot → execute → confirm → revert — as the emerging standard for production agents executing destructive operations. Cited growing adoption as agents move from read-only to write-heavy tasks. — [URL](https://agentmarketcap.ai/blog/2026/04/11/agent-checkpoint-rollback-engineering-2026)

- **Hacker News Ask thread (2026):** Practitioners sharing reliability audit frameworks built from 50+ test cases. Top failure modes identified: hallucination under unexpected inputs, edge case collapse (null values, Unicode names, empty fields), prompt injection, and silent success where the agent completes without errors but produces wrong output. — [URL](https://news.ycombinator.com/item?id=47325105)

- **GitHub community resource (vectara/awesome-agent-failures, 2025):** Community-curated taxonomy of seven failure modes with battle-tested mitigations: tool hallucination, response hallucination, auth failures, action loops, state drift, external outages, and rate limit cascades. — [URL](https://github.com/vectara/awesome-agent-failures)

- **Engineering blog (Tian Pan, April 2026):** Documented the Replit database deletion incident — agent with unrestricted SQL execution ran `DROP TABLE` during a live demo, producing the message "I panicked." Four-hour restore from backups. Core argument: agent mistakes are not database bugs; they execute in external state and cannot be fixed by redeploying code. — [URL](https://tianpan.co/blog/2026-04-20-ai-agent-data-rollback-production)

- **Open-source framework (ARF — Agentic Reliability Framework, 2025):** Three-agent architecture: Detective (anomaly detection via FAISS), Diagnostician (causal root cause analysis), Predictive (failure forecasting). Reported 2-minute MTTR versus 45-minute manual recovery, 15–30% revenue impact reduction per incident. — [URL](https://paragguptaclasses.blogspot.com/2025/12/show-hn-agentic-reliability-framework.html)

- **Industry analysis (zeluai.com, citing IDC research):** 88% of AI agent pilots never reach production — 4 of 33 graduate to deployment. Core finding: agents fail silently, completing tasks without error codes while producing wrong outputs. — [URL](https://www.zeluai.com/blog/ai-agent-failures-in-production)

- **Engineering blog (MatrixTrak, January 2026):** Loop detection taxonomy: "Done is not a model concept." Root causes — repeat tool calls (same error class), the model never signaling completion, step count ballooning without progress. Solutions — step limits, token budgets, action-sequence fingerprinting. — [URL](https://matrixtrak.com/blog/agents-loop-forever-how-to-stop)

- **Engineering blog (Agents.NET, June 2026):** AI agents fail probabilistically, emergently, and invisibly. Traditional debugging tools (breakpoints, stack traces, unit tests) are necessary but insufficient. Every step in a multi-tool agent introduces a distinct failure mode that can cascade silently. — [URL](https://agents.net/blog/ai-agent-debugging-error-handling-production)

- **GitHub repo (reivo-guard):** Open-source guardrails library (Python + TypeScript) that auto-kills runaway agents. Features: budget enforcement, loop detection, quality verification. — [URL](https://github.com/tazsat0512/reivo-guard)

## Gotchas

- **Prompts don't enforce budgets.** Telling the model "stop after 10 steps" is guidance, not a constraint. The model will comply right up to the point where it produces a plausible-looking step 11. Use structural limits (step counters, token budgets, circuit breakers) — not prompt instructions.
- **"Success" is the wrong success metric.** A run that returns HTTP 200 with hallucinated output is not a successful run. Track task completion against ground truth, not against whether the agent finished.
- **Error masking is built into agent design.** Agents are optimized to produce a response. When a tool fails, the model often invents a plausible result rather than surfacing the error. You must explicitly surface tool errors as first-class events, not let them flow through the model's output generation.
- **One agent step, many failure surfaces.** A single agent turn involves: input parsing, context retrieval, tool call generation, tool execution, result interpretation, and response formatting. An error at any layer can propagate into a wrong output at the end. Each layer needs its own error boundary.
- **Human-in-the-loop is not optional for destructive operations.** It is the only reliable guard against an agent acting on hallucinated context. Budget for latency — the 30 seconds to get a confirmation is cheaper than the four-hour restore.
