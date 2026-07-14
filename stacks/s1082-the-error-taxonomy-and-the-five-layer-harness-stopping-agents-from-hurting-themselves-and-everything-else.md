# S-1082 · The Error Taxonomy and the Five-Layer Harness — Stopping Agents From Hurting Themselves and Everything Else

Your agent makes great decisions. Until it calls the wrong tool, hits a rate limit, hallucinates a JSON argument, loops on a logic error, and then makes that same mistake three more times while the context window drains. This isn't a model problem you can fix with a better prompt. It's an execution layer problem that requires a harness.

## Forces

- **Agents fail non-deterministically.** Unlike code with a known stack trace, an agent's "errors" include HTTP-200 hallucinations, semantically wrong tool calls, and confident nonsense chains. Traditional try-catch doesn't cover it.
- **Bad outputs snowball.** A garbled JSON response from node A propagates into worse failures in node B. Agents amplify downstream damage far faster than traditional software.
- **Loops are not edge cases — they are guaranteed at scale.** With enough turns, any agent will eventually hit a condition that causes looping. What was a 2% probability per run becomes a 100% probability per month of continuous operation.
- **Rollback has no standard abstraction.** Agents mutate external state (files, databases, APIs) without a transaction boundary. When it goes wrong, the blast radius isn't in your codebase — it's in production data.

## The Move

Build a five-layer harness before the agent does anything irreversible. Each layer addresses a distinct failure class.

### Layer 1 — Error Taxonomy and Routing

Classify every failure into one of four buckets and route each to its correct handler:

| Error Class | Who Fixes It | Handler |
|---|---|---|
| **Transient** (429, timeout, DNS) | The system, automatically | Retry with backoff |
| **LLM-Recoverable** (bad JSON, wrong tool) | The LLM itself | Inject corrective context and re-prompt |
| **User-Fixable** (ambiguous input, missing field) | A human | `interrupt()` and await resolution |
| **Unexpected/Unrecoverable** | Nobody in-loop | Dead letter queue, escalate |

Source: Focused Labs (LangGraph error handling) and Neel Mishra's MLOps agent taxonomy independently converge on this four-class model. The key insight from both: the fix is not "add a try/except" — it's routing each error class to who can actually fix it.

### Layer 2 — Hard Execution Bounds

Without explicit limits, running long enough guarantees catastrophic failure.

- **Step ceiling:** Cap turns at 20–50 (Cloudzy benchmarks: 25 is common for document pipelines, up to 50 for multi-tool research). Track step count in agent state, not in the model's head.
- **No-progress detection:** If the agent's last N tool calls produced no meaningful state change (same tool called 3× in a row, identical output), break the loop and trigger recovery. This catches logic loops that step-counting alone misses.
- **Per-tool timeouts:** Set timeouts at the tool level, not just the request level. A web search can hang; a file write can take forever; an API call can stream indefinitely. Timeout per tool, defaulting to 30–120s.

Source: Cloudzy's "6 harness fixes" post, r/AI_Agents practitioner thread, and Adaline Labs independently all name step limits as the first line of defense.

### Layer 3 — Retry with Exponential Backoff and Selective Retry Logic

Not all errors warrant retry. Configure it by error class:

- **Retry transient errors** (HTTP 429, 503, timeout, DNS failure) with exponential backoff: 1s → 2s → 4s → 8s → 16s. Add jitter (±20%) to prevent thundering herd.
- **Do NOT retry** auth failures (401), invalid input (400), or malformed requests — these won't resolve on their own.
- **Retry count:** 3–5 attempts for most operations. Critical operations (payments, writes) may warrant more, but each retry wastes time and may cascade. OpenHelm reports proper retry handling increased agent reliability from 87% to 99.2% — a 14× reduction in failures.

Source: OpenHelm blog (quantified result), Neel Mishra's retry taxonomy, LangGraph's `RetryPolicy` guide.

### Layer 4 — Circuit Breakers

When a downstream service is genuinely degraded, retries don't help — they amplify load.

- Trip the circuit after N consecutive failures (N=3–5 is common).
- Open the circuit for a fixed cooldown period (30s–5min).
- During open state: fail fast, use cached responses, or route to a fallback model/tool.
- Auto-reset after the cooldown window.

This prevents retry storms — where 1,000 agents simultaneously retry a 503 and generate 50,000 requests against a struggling service.

Source: Preporato (NCP-AAI curriculum), OpenHelm, Fast.io independently document circuit breakers as mandatory for multi-agent production.

### Layer 5 — Checkpoint and Rollback

When all else fails, you need to return to a known-good state rather than continue from a corrupted one.

- **Checkpoint before every write operation:** Snapshots of agent state (tool history, conversation context, intermediate results) are stored before any mutation to external systems. Commit only after validation.
- **Three-layer rollback architecture:**
  - Layer 1: Filesystem — `cp -r` state snapshots before destructive file operations
  - Layer 2: Database — transaction-based state; use rollback if the DB supports it (CockroachDB serializable isolation recommended)
  - Layer 3: API/Web — ephemeral state; use idempotency keys so repeated calls produce identical results
- **Idempotency keys:** Attach a unique key to every write operation. If the agent retries or replays, the downstream system recognizes the key and returns the original result without re-executing. Critical for APIs that are not naturally idempotent (email sends, payment charges, record creation).

Source: AgentMarketCap's April 2026 rollback engineering post (three-layer architecture), CockroachDB's production agent loop patterns (database state), Adaline Labs (idempotency keys).

## Evidence

- **LangChain/LangGraph error handling guide:** Documents the four-class error taxonomy with code-level routing to `RetryPolicy`, `interrupt()`, and dead letter queues. Emphasizes that error handling built at the graph edge (rather than inside nodes) scales better. — [machinelearningplus.com](https://machinelearningplus.com/gen-ai/langgraph-error-handling-retries-fallback-strategies)
- **OpenHelm quantified result:** Teams implementing retry logic + circuit breakers + fallbacks saw agent reliability jump from 87% to 99.2% in production. Specific failure mode breakdown: API timeouts (2–5% of requests during peak), rate limits (HTTP 429), and invalid JSON from LLM output were the top three recoverable failure modes. — [openhelm.ai](https://www.openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)
- **CockroachDB production patterns:** Persistent workflow state in a durable database (with serializable isolation) is what separates agents that recover cleanly from agents that continue in a corrupted state. The blog explicitly recommends against relying on in-memory or ephemeral state for agent loops that run longer than a single request. — [cockroachlabs.com](https://www.cockroachlabs.com/blog/agent-loops-production-database-patterns)
- **r/AI_Agents practitioner thread:** Practitioner describes the loop-within-context problem: "the more context I give it to 'reason,' the more it overthinks and breaks the loop." Community consensus: hard step limits, explicit state management, and approval gates before irreversible operations. — [reddit.com/r/AI_Agents](https://www.reddit.com/r/AI_Agents/comments/1r54kau/anyone_else_struggling_with_agent_loops_getting/)
- **NassimRahimi/agent-failure-recovery (GitHub):** Open-source demo implementing the full pipeline: failure detection → attribution to specific tool call and run_id → quarantine bad state → rollback to known-good snapshot → recovery validation. Uses mock LLM for deterministic testing. — [github.com/NassimRahimi/agent-failure-recovery](https://github.com/NassimRahimi/agent-failure-recovery)

## Gotchas

- **Step count limits don't catch semantic loops.** An agent can call different tools but produce the same wrong decision repeatedly. Pair step limits with no-progress detection (same output in last N turns → interrupt).
- **Retry without jitter creates thundering herds.** If your agent orchestration runs 500 instances and all hit a 503 simultaneously, naive retry (same delay across all instances) generates a retry storm. Always add jitter.
- **Context window exhaustion is a silent failure.** When the agent approaches token limits, output quality degrades gradually rather than crashing. Monitor token usage per turn and trigger a summarize-or-truncate step at 70–80% of context capacity.
- **Approval gates are useless if placed after the model decides.** If you ask the LLM "should I run this DELETE?" it will almost always say yes. Approval gates must be in the orchestrator layer, enforced before the tool executes — not as part of the agent's reasoning.
- **Dead letter queues need human review, not automatic retry.** Tasks that fail after exhausting all recovery paths should go to a human queue with full context (run_id, tool history, error classification). Auto-retrying them wastes cycles on failures that require judgment to resolve.
