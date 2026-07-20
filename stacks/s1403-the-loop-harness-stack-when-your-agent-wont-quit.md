# S-1403 · The Loop Harness Stack — When Your Agent Won't Quit

Your agent has been "working" on the same task for 47 minutes. It's not crashing. It's not erroring. It's just looping — calling the same tool with slightly different arguments, each response sounding plausible, none of them right. Your monitoring shows 100% uptime. Your logs are full. The budget is bleeding. This is the loop failure: the agent that won't quit, and the infrastructure you need to stop it.

## Forces

- **LLMs hallucinate tool calls and miss exit conditions** — unlike code, the LLM doesn't "know" it's looping; each iteration feels reasonable in isolation
- **Silent failures return HTTP 200** — the agent finishes the task but the output is semantically wrong; traditional monitoring never flags it
- **The stuck/converging boundary is fuzzy** — agents genuinely need multiple iterations; hard-coding step limits kills legitimate long-horizon tasks
- **Error handling migrated from try-catch to agentic self-correction** — the LLM is now part of the recovery path, but only if it can see the error
- **Human oversight vs. autonomous recovery** — the more power you give the agent to self-correct, the less you can predict what it will do next

## The Move

The loop harness is layered infrastructure that (1) classifies failures by who should fix them, (2) feeds errors back into agent state so the LLM can self-correct, (3) enforces hard termination bounds from the outside, and (4) escalates to human review at defined thresholds.

**1. Classify errors into four buckets — who fixes this?**

| Class | Fixer | LangGraph Primitive | Examples |
|-------|-------|---------------------|----------|
| Transient | System | `RetryPolicy` (automatic) | 429 rate limit, DNS blip, network timeout |
| LLM-Recoverable | The LLM | Error stored in state + loop back | Tool returned bad JSON, wrong tool chosen |
| User-Fixable | Human | `interrupt()` | Missing required field, ambiguous input |
| Unexpected | Developer | Let it bubble up | `TypeError`, schema mismatch, logic bug |

**2. Errors are state, not exceptions.** Instead of swallowing errors in try-catch, inject them into the agent's state so the LLM sees the failure on the next turn and can adjust strategy:

```python
class AgentState(TypedDict):
    messages: list
    error: str | None        # last error
    retry_count: int         # which retry we're on
    step_count: int          # total steps this run
    fallback_used: bool      # did we switch models?
```

**3. The recovery ladder.** On failure, climb: retry with exponential backoff → inspect error → self-correct (LLM) → fallback model → human interrupt → fail-safe terminal state (`needs_approval`, `queued_for_later`, `failed_safely`).

**4. Hard termination bounds from the outside.** The LLM cannot be trusted to self-limit. Set them externally: `max_steps_per_run`, `max_retries_per_tool`, `max_runtime_per_run`, `same_error_twice = escalate`. Also design explicit terminal states — agents need a place to land.

**5. Convergence detection, not just step counting.** Distinguish slow-but-converging from genuinely stuck: track action diversity (is the agent repeating the same tool call?), output entropy, and progress signals (is the output improving across iterations?). Step counting alone kills legitimate long-horizon tasks.

**6. Monitor what actually matters for loop health.** Track: retry count, success rate after retry, latency impact of recovery, semantic quality of fallback outputs. Standard infrastructure monitoring (uptime, HTTP status) misses loop failures entirely.

## Evidence

- **HN Ask thread (harperlabs):** Practitioner built reliability audit framework covering 7 consistent failure modes; found teams commonly test #1 (hallucination) and #3 (tool errors) but almost no one systematically tests #4–#7 (routing loops, semantic failures, silent success, prompt injection) — [HN Ask: How are you testing AI agents before shipping to production?](https://news.ycombinator.com/item?id=47325105)

- **TensorPool Agent (YC W24, Show HN):** Autonomous GPU training job recovery agent. Solves the "zombie job" problem — jobs that appear running but are silently stalled (NCCL rank failures, Xid GPU errors, corrupted S3 checkpoints). Commenters specifically flagged trust concern: an agent silently nursing a zombie job without progress checks is worse than no agent at all — requires deterministic health signals, not LLM self-assessment. — [Show HN: TensorPool Agent](https://news.ycombinator.com/item?id=46812909)

- **LangGraph documentation (LangChain):** `RetryPolicy` for node-level retries with configurable backoff, `interrupt()` for human-in-the-loop approval gates, and checkpoint-based stateful rollbacks that preserve partial execution on failure — [LangGraph: Error Handling and Retry Policies](https://deepwiki.com/langchain-ai/langgraph/3.8-error-handling-and-retry-policies)

- **AgentPatterns.ai:** Loop engineering concept — designing agent loops that converge by treating termination and cost as first-class design concerns, not afterthoughts. Proposes convergence detection (action diversity, output entropy, progress signals) as distinct from step counting — [Loop Engineering: Designing Agent Loops That Converge](https://www.agentpatterns.ai/loop-engineering)

## Gotchas

- **HTTP 200 means nothing.** A `200 OK` response with semantically wrong output is the most dangerous failure mode — it passes all conventional monitoring. You need semantic validation layered on top of HTTP status checks.
- **Step limits kill legitimate agents.** A hard `max_steps=20` defeats tasks that genuinely need 30 steps. Use convergence detection (is the output improving?) instead of step counting alone.
- **Errors swallowed in try-catch prevent self-correction.** If you catch the error and log it silently, the LLM never sees it and can't adjust strategy. The error must enter the state.
- **Fallback models reduce quality, not cost.** When the primary model fails (500, timeout), switching to a smaller fallback degrades output quality. Budget for this in your quality expectations and monitoring — don't silently ship degraded outputs.
- **"Silent" progress looks like success.** A looping agent that generates plausible-sounding logs is indistinguishable from a working agent in standard log aggregation. You need action-level tracing: which tool was called, with what args, and what changed in the output.
