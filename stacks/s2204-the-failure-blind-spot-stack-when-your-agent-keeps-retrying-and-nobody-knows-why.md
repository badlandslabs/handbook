# S-2204 · The Failure Blind Spot Stack — When Your Agent Keeps Retrying and Nobody Knows Why

When your agent fails, it catches the error, retries with backoff, fails again, and either loops until it burns through tokens or returns a silently wrong answer — and you find out three hours later when a user complains.

## Forces

- **Retry logic is not a recovery strategy.** 67% of AI system failures stem from improper error handling, not algorithmic issues — yet teams implement retry loops and call it done. Basic retry covers only ~20% of actual failure modes (transient: timeouts, rate limits). The other 80% — semantic errors, structural failures, deadlocks — just fail more expensively with each retry.
- **Agents fail without crashing.** Unlike conventional software, agents can produce wrong answers, skip tool calls, or stall mid-task with no exception raised. Silent failures are the production norm, not the exception.
- **Loops are the #1 production failure mode.** MAST analysis of 1,642 real agent traces across 7 frameworks found failure rates of 41–87%. Agent looping alone accounts for the majority of production incidents — and naive retry makes it worse.
- **Tracing complexity hides the real failure surface.** Agent trace spans average 50KB each; a single session can generate 10GB of trace data. 67.6% of tokens in an agent trace are tool responses — but teams obsess over the 3.4% spent on system prompts.

## The Move

Classify failure before choosing a response. Agents need a triage layer that distinguishes error types and routes each to the right intervention — not a flat retry loop.

### 1. Build a four-category failure taxonomy

| Category | Examples | Right response |
|---|---|---|
| **Transient** | API timeout, HTTP 429, 503, DNS blip | Exponential backoff retry with jitter |
| **Semantic** | Valid HTTP response, but content is wrong/hallucinated/wrong schema | Abort and escalate — retry won't help |
| **Structural** | Wrong tool chosen, impossible operation, plan failure | Re-plan from last checkpoint |
| **Cascading** | Loop detected, resource exhaustion, context overflow | Hard halt with state snapshot |

Only category 1 belongs in a retry loop. Everything else needs a different exit path.

### 2. Instrument loop detection before retries

The most common cause of agent loops isn't repeated transient errors — it's ambiguous tool responses. When a search returns `[]`, an agent sees "not done yet" instead of "definitive empty result." A single pattern change fixes ~40% of production loops:

```json
// Make every tool response self-describing
{
  "status": "complete",
  "result": [],
  "message": "Search returned no results. This is definitive — do not retry."
}
```

Pair with structured loop guards: max iterations with hash-based repetition detection (catch when the agent reaches the same reasoning conclusion in 3+ consecutive turns).

### 3. Layer circuit breakers per tool

Not all tools are equal. A payment API failure should trip immediately (failure_threshold=1); a search API failure can absorb several retries. Implement per-tool circuit breakers with different thresholds and recovery timeouts:

```python
tool_breakers = {
    "payment_api": CircuitBreaker(failure_threshold=1, recovery_timeout=120),
    "search_api": CircuitBreaker(failure_threshold=5, recovery_timeout=30),
    "code_exec": CircuitBreaker(failure_threshold=3, recovery_timeout=60),
}
```

### 4. Checkpoint state at decision boundaries

Agents need resumable state, not just retry-from-start. Save a lightweight checkpoint at each major decision point (tool call, plan change, task handoff). On failure, the recovery path replays from the last checkpoint rather than re-executing from scratch. Three tiers of reversibility:

- **Filesystem level:** Git/checkpoint files — cheap, coarse
- **Database level:** Compensating transactions for multi-step operations — saga pattern applied to agentic pipelines
- **External action level:** Irreversible operations (emails sent, money moved) — approval gates *before* execution, not recovery after

### 5. Route uncorrectable failures to a dead letter queue

For semantic and structural failures that can't be retried to resolution, write to a DLQ with full context: input, trace, failure classification, checkpoint snapshot. This prevents silent loss and enables human review, replay, or downstream compensation. The DLQ is the fallback for the 80% of failures that retry can't touch.

### 6. Add human-in-the-loop for irreversible actions

For any operation with irreversible consequences, the control gate runs *before* the action — not after. Dry-run modes, approval queues, and idempotency keys are the last line. MAST data shows specification failures (agent ignores task constraints) account for 11.8% of failures; pre-execution validation catches most of these.

## Evidence

- **MAST Taxonomy (NeurIPS 2025):** 1,642 agent execution traces across AutoGPT, BabyAGI, CrewAI, LangGraph, MetaGPT, CAMEL, and ChatDev. Failure rates 41–87%. 14 failure modes in three categories: Specification (41.77%), Execution, and Communication. — [GitHub/mast-taxonomy.md](https://github.com/HimClix/agentic-ai-system-design-primer/blob/main/resources/failure-modes/mast-taxonomy.md)
- **Microsoft AI Red Team Taxonomy v2.0 (April 2026):** 7 safety failure modes, 13 security failure modes, 12 mitigation families. New surfaces: MCP/plugin abuse, CUA visual attacks, supply-chain compromise via natural-language tool descriptions. — [Microsoft PDF](https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/bade/documents/products-and-services/en-us/security/Taxonomy-of-Failure-Modes-in-Agentic-AI-Systems-v2-0.pdf)
- **Tian Pan / Self-Healing Agents (Sept 2025):** Three silent failure categories. Pattern 1: repeated identical tool calls (agent thinks it failed when it succeeded). Pattern 2: repeated reasoning conclusions (agent loops on the same plan). Pattern 3: cascading failure from resource contention. — [tianpan.co](https://tianpan.co/blog/2025-09-22-self-healing-agents-in-production)
- **GetATeam post-mortem (Nov 2025):** Single unhandled API timeout cascaded into complete system failure. Solution: exponential backoff, circuit breakers, dead letter queues, graceful degradation. — [blog.geta.team](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/)
- **Zylos Research (Feb 2026):** Self-healing implementations achieve 60% reduction in system downtime. Five-stage cycle: detection → diagnosis → repair → validation → adaptation. Agentic SRE pattern distributes failure response across specialized agents. — [zylos.ai](https://zylos.ai/research/2026-02-17-ai-agent-self-healing-auto-recovery/)
- **Zenflow Show HN (2025):** Built specifically to handle "you're right" loops in coding agents — cross-model verification where one model reviews another's output, breaking the mutual-confirmation deadlock. — [Hacker News](https://news.ycombinator.com/item?id=46290617)
- **Digital Applied / Agent Rollback Patterns (July 2026):** Three tiers of undo, saga pattern for agent compensation, GuardFall defeated command filters in 10/11 open-source agents — isolation is mitigation, not guarantee. — [digitalapplied.com](https://www.digitalapplied.com/blog/agent-rollback-checkpoint-patterns-2026-engineering-reference)
- **HN multi-agent debugging thread (2026):** Practitioners confirm coordination failures, state management, and cross-agent contract enforcement are the hard unsolved problems. — [Hacker News](https://news.ycombinator.com/item?id=47358618)

## Gotchas

- **Naive retry is optimistic.** It assumes the same operation will succeed if given another chance. For semantic errors (wrong output, wrong schema) and structural errors (wrong plan, wrong tool), retrying the same thing produces the same failure. Classify first.
- **Max iteration limits prevent loops but don't fix the underlying cause.** A loop guard without a recovery path just means "fail fast and give up." Pair every limit with a checkpoint + DLQ so the failure is actionable.
- **System prompts are not where the failures live.** Braintrust data shows 67.6% of agent trace tokens are tool responses. Teams spend hours on prompt engineering when the real debugging surface is tool interaction — the response schemas, status codes, and error messages agents receive from their own tools.
- **Self-healing needs a defined scope.** A five-stage detect-diagnose-repair-validate-adapt cycle is the aspiration. In practice, "adapt" (storing failure patterns for future use) is the hardest part and the most commonly skipped. Without it, you get recurrence — the same failure pattern repeating across sessions.
