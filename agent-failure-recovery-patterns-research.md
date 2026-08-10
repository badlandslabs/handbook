# Agent Failure Handling & Recovery: Primary Source Research

**Compiled:** August 2026 | **Scope:** Production AI agents, primary sources
**Source types:** Company engineering posts (Anthropic, OpenAI), framework source/docs (OpenAI Agents SDK, LangGraph, Pydantic AI, Anthropic SDK Go), agent pattern catalogs, practitioner reports.

---

## SECTION 1: ERROR TAXONOMY

Before choosing a recovery strategy, classify the failure type. Every framework and practitioner independently arrives at the same four-category taxonomy.

| Error Type | Examples | Correct Response |
|---|---|---|
| **Transient** | HTTP 429, 503, timeout, DNS failure | Retry with backoff — will self-resolve |
| **Client/Validation** | HTTP 400, 401, 404, schema violation | Fix root cause, then retry; never retry blindly |
| **Semantic** | Hallucinations, confident wrong answers, malformed tool output | Validation layer, re-prompt with correction, or escalate |
| **Business-rule** | Action blocked by policy, denied permission | Fail fast; escalate to human |

**Key insight (LangGraph docs):** "A timeout from a remote API is different from invalid state, which is different from a rejected human approval, which is different from a tool permission violation. Retrying all of them the same way wastes money and can make incidents worse."

**OpenAI Agents SDK exception hierarchy:**
- `AgentsError` — base class
- `MaxTurnsExceededError` — extends `AgentsError`; carries `RunState` snapshot; thrown when `maxTurns` limit is reached
- Tool errors — normalized and routed through `RetryConfig`

---

## SECTION 2: RETRY WITH BACKOFF

### OpenAI Agents SDK Retry Module (`src/agents/retry.py`)

The SDK has two retry layers:

**Layer 1: Model-level backoff settings** (`ModelRetryBackoffSettings`):
- `initial_delay`: seconds before first retry
- `max_delay`: cap on delay between retries
- `multiplier`: exponential multiplier per attempt
- `jitter`: random jitter to prevent thundering herd

**Layer 2: Runner-level `RetryConfig`**:
- `max_attempts`, `initial_delay_ms`, `max_delay_ms`, `multiplier`
- `retry_on`: list of `ExceptionType` — which exceptions trigger retry
- Respects HTTP `Retry-After` header via `wait_retry_after` strategy

**MaxTurnsExceededError behavior:**
- Runner throws this when `maxTurns` is reached
- Exception carries full `RunState` — caller can inspect what agent was doing at the limit
- Agent loop terminates; no automatic retry — this is a guard rail, not a transient failure
- **Community reported issue (Jan 2026):** `MaxTurnsExceeded` during tool execution leaves caller unable to retrieve partial results. Mitigation: catch the exception and resume from the last tool result.

### Pydantic AI Retry Infrastructure

Built on **Tenacity**. Two independent retry configs for task vs evaluator execution:

```python
retry_task={'stop': stop_after_attempt(3), 'wait': wait_exponential(multiplier=2, min=1, max=30)}
retry_evaluators={'stop': stop_after_attempt(2)}
```

`AsyncTenacityTransport` wraps HTTP requests with `RetryConfig` respecting `Retry-After` headers.

Key Tenacity wait strategies:
- `wait_exponential`: `min * 2^(attempt-1)` up to `max`
- `wait_random`: adds jitter
- `wait_retry_after`: reads `Retry-After` header

### Anthropic SDK Tool Error Handling

Tool execution errors are converted to `is_error: true` tool result blocks and sent back to Claude as a regular tool result. Claude then self-corrects and retries or tries a different approach. Recovery is **model-driven**, not infrastructure-driven.

**Anthropic Python SDK default:** 3 retries with jittered exponential backoff on API errors. No circuit breaker by default.

### Practitioners Recommended Backoff Schedule

- Attempt 1: immediate
- Attempt 2: ~1s
- Attempt 3: ~2s
- Attempt 4: ~4s
- Attempt 5: ~8-16s
- Then fail or escalate

Add **jitter** (random +/- 20-50%) at every step to prevent synchronized retry storms.

---

## SECTION 3: CIRCUIT BREAKERS

### Three States

| State | Behavior | Trigger |
|---|---|---|
| **CLOSED** (normal) | Requests pass through; failures counted | — |
| **OPEN** | Requests fail immediately without calling downstream | N consecutive failures (typically 3-5) |
| **HALF-OPEN** | Limited requests allowed through to test recovery | After `reset_timeout` expires |

### Key Decision

Circuit should open on **transient errors only** (429, 503, timeout). Never open on validation errors (400, 401) — those indicate a bug, not an overloaded service.

From OpenHelm: "After N consecutive failures, stop calling the downstream service. This prevents cascading failures."

---

## SECTION 4: FALLBACK CHAINS

### Multi-Provider Fallback Pattern

Core principle: **cross-provider fallbacks protect against correlated outages**. If primary and fallback are both OpenAI, one API outage takes down the entire chain.

```python
chain = FallbackChain([
    call_gpt4o,           # Primary: best quality
    call_gpt4o_mini,     # Fallback 1: cheaper
    call_claude_haiku,    # Fallback 2: cross-provider
    return_cached,       # Fallback 3: stale but useful
])
```

### OpenAI Agents SDK Handoffs

Handoffs are structured fallback: a tool call that transfers control to another agent. Used for specialized subagents rather than provider failover.

### Degradation Chain

Full response -> Cached response -> Summarized context -> Static fallback -> Error message

---

## SECTION 5: CHECKPOINTING & STATE RECOVERY

### Anthropic Multi-Agent Research System — Git-Based Recovery

Anthropic recommends for long-running research agents:
- **Commit frequently** so progress is preserved at recoverable points
- Use **git worktrees** for parallel exploration — each worktree is an isolated checkpoint
- After each significant step: `git add . && git commit -m "step: completed analysis"`
- On failure: `git stash` or branch switch recovers state

Why git: already trusted, versioned, auditable, provides diffs for free, agents already interact with it.

**Anthropic GitHub #6568:** Claude Code misinterpreted "commit everything" as "commit only current files" — partial commit and data loss. This is a **semantic error** (model misunderstood intent), not a technical failure.

### Anthropic GitHub #16057 — OnCompactFailed Hook

Claude Code context compaction can fail on large conversations. Proposed hook pattern:

```javascript
{
  "hooks": {
    "onCompactFailed": {
      "script": "./recovery-script.js",
      "actions": ["save-conversation-to-file", "notify-user", "checkpoint-before-exit"]
    }
  }
```

### LangGraph Checkpointing

```python
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
app = workflow.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "session-123"}}
app.invoke(None, config)  # Picks up from last checkpoint
```

**Pending writes (critical):** When a node fails mid-superstep, LangGraph stores pending writes from other nodes that completed successfully in that superstep. On resume, completed nodes are **NOT** re-executed — only the failed node is retried.

### Temporal + LangGraph Crash Recovery

Uses Temporal heartbeat mechanism to checkpoint LangGraph state during long agent runs. Simulates K8s OOMKill: checkpointer persists state after each node. Next invocation resumes from last saved checkpoint without re-running completed nodes.

---

## SECTION 6: CONTAINMENT & BLAST RADIUS (ANTHROPIC)

### Anthropic Engineering: How We Contain Claude Across Products (May 2026)

Anthropic frames agent failure as a **blast radius problem**. Two containment approaches:

**Approach 1: Human-in-the-Loop (Supervision)**
- Ask user for permission at each action (Claude Code original approach)
- **Discovery:** ~93% of permission prompts were auto-approved — security theater that degraded UX without improving safety
- Not sufficient alone

**Approach 2: Autonomous Operation with Structural Limits**
- Reduce need for human oversight by making the environment safer
- Three containment layers (defense in depth):
  1. **Environmental** — sandboxing, restricted file access, network segmentation
  2. **Tool-layer** — read-only DB access, allow-listed tools, rate-limited APIs
  3. **Model-layer** — system prompts encoding behavioral constraints

Key insight: "Defenses should overlap and complement each other. When environmental defenses are not available, the model layer has to pick up the slack."

### Tool Error Containment

When a tool throws an error, it is converted to a tool result with `is_error: true` and fed back to the model. The model can then: (1) retry with corrected parameters, (2) try an alternate tool, (3) acknowledge failure, (4) request help. Self-healing at the model level — the error does not propagate up as an exception unless the model exhausts recovery attempts.

---

## SECTION 7: PROGRESSIVE FAILURE HIERARCHY

Self-Correct -> Fallback -> Degrade Gracefully -> Escalate

| Level | Strategy | When Used |
|---|---|---|
| **Self-Correct** | Detect error, retry or adjust | Most tool errors (failed file read -> path correction) |
| **Fallback** | Switch strategy or model | Primary fails repeatedly; threshold made explicit by circuit breaker |
| **Degrade Gracefully** | Deliver partial results | Ideal response impossible; return what IS available |
| **Escalate** | Surface to human with context | Last resort; provides full state + error history |

---

## SECTION 8: OUTPUT VALIDATION GUARDS

### Layered Validation Pipeline

```
Raw LLM output
    -> Schema validation (Pydantic/Zod) — catches malformed JSON, wrong types
    -> Semantic validation — checks output matches task intent
    -> Groundedness check — confirms output aligns with retrieved context
    -> Format enforcement — applies output template
```

If validation fails at any layer:
- **Schema:** Return parse error -> model re-generates with correct structure
- **Semantic:** Return specific error -> model self-corrects
- **Groundedness:** Flag hallucination -> escalate or use fallback source

---

## SECTION 9: TOOL CALL PIPELINE ERROR LAYERS

From Claude Code Agent Development Guide:

```
LLM wants to call a tool
         |
    Layer 1: canUseTool (context check)     -> PermissionDenied
         |
    Layer 2: Schema Validation (input check) -> ValidationError
         |
    Layer 3: Execution (runtime check)      -> RuntimeError
         |
         V
    Success or tool_error result
```

---

## PATTERN SUMMARY TABLE

| Pattern | Primary Source | Used For |
|---|---|---|
| Retry with exponential backoff + jitter | OpenAI Agents SDK, Pydantic AI, OpenHelm | Transient failures (429, 503, timeout) |
| MaxTurnsExceededError with RunState snapshot | OpenAI Agents SDK | Turn-limit guard rail |
| Tool error -> is_error result -> model self-corrects | Anthropic Go SDK, Anthropic Python SDK | Tool failures |
| Circuit breaker (CLOSED/OPEN/HALF-OPEN) | OpenHelm, NiteAgent, Cowork/Ink | Preventing cascading failures |
| Multi-provider fallback chain | Neel Mishra, NiteAgent | Provider outages |
| Graceful degradation chain | Cowork/Ink, agentpatterns.ai | Delivering partial results |
| Git-based checkpointing | Anthropic multi-agent engineering blog | Long-running coding agents |
| LangGraph pending writes + checkpoint resume | LangGraph docs, tutorialslogic.com | Crash recovery |
| Temporal heartbeat + LangGraph | steveandroulakis/temporal-langgraph-checkpoint-recovery | K8s OOMKill recovery |
| Progressive failure hierarchy | agentpatterns.ai (Anthropic-based) | Self-correct -> Fallback -> Degrade -> Escalate |
| Output validation layers | Cowork/Ink, LangGraph, Pydantic AI | Catching hallucinations, bad schema |
| Blast radius containment (env + tool + model) | Anthropic How We Contain Claude | Limiting damage from failures |
| OnCompactFailed hook | Anthropic GitHub #16057 | Context compaction failure |
| Three-layer tool call validation | Claude Code agent dev guide | Tool permission, schema, runtime errors |

---

## SOURCES

- Anthropic Engineering: How We Contain Claude Across Products (May 2026)
- Anthropic Engineering: How We Built Our Multi-Agent Research System (Jun 2025)
- OpenAI Agents SDK: Retry Module (openai.github.io/openai-agents-python/ref/retry/)
- OpenAI Agents SDK: MaxTurnsExceededError (openai.github.io/openai-agents-js/)
- OpenAI Agents SDK: Running Agents guide
- Anthropic SDK Go: Tools and Error Handling (github.com/anthropics/anthropic-sdk-go)
- Anthropic Docs: Handle Tool Calls (docs.anthropic.com)
- LangGraph: Error Handling and Retry Policies (deepwiki.com/langchain-ai/langgraph)
- LangGraph: Checkpoint Recovery (github.com/nadja-mansurov/langgraph-checkpoints)
- LangGraph + Temporal: Crash Recovery (github.com/steveandroulakis/temporal-langgraph-checkpoint-recovery)
- LangGraph: Errors and Retries Failure Taxonomy (tutorialslogic.com)
- Pydantic AI: Retries Module (pydantic.dev/docs/ai/api/pydantic-ai/retries)
- Pydantic AI: Retry Strategies in Evals (pydantic.dev/docs/ai/evals/how-to/retry-strategies)
- agentpatterns.ai: Exception Handling and Recovery Patterns
- OpenHelm: Error Handling and Reliability Patterns for Production AI Agents (Jul 2024)
- NiteAgent: Building Reliable Agent Error Handling (Jul 2026)
- Neel Mishra: Agent Error Handling Retries and Fallbacks
- Cowork/Ink: AI Agent Error Handling (Apr 2026)
- Preporato: Error Handling in AI Agents
- Claude Code Agent Development Guide: Error Handling and Resilience
- Anthropic GitHub #16057: OnCompactFailed hook feature request
- Anthropic GitHub #6568: Critical Git Commit Failure
