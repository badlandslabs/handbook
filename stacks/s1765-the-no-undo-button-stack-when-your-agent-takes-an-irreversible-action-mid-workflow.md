# S-1765 · The No-Undo-Button Stack

When your multi-step agent workflow fails on step 7 of 12, and steps 1–6 already sent emails, charged cards, and updated databases — there is no Ctrl+Z for reality. The agent moved money, notified people, and changed state across external systems. Retry doesn't un-send an email. You need a compensating workflow, not a rollback.

## Forces

- **LLM calls fail 1–15% of the time in production** (transient errors: rate limits, timeouts, server errors). Standard try/catch with a single retry is insufficient for workflows spanning 5+ steps.
- **Agents take irreversible actions.** Unlike traditional software where a failed transaction rolls back atomically, agent workflows span HRMS, payroll, CRM, email, and payment APIs — none of which share a transaction coordinator.
- **"Just retry" breaks idempotency.** Retrying a payment API call without an idempotency key doubles the charge. Retrying a "create record" call without deduplication creates duplicates.
- **Infinite loops cost real money.** One HN case documented $47,000 in 4 weeks from two agents caught in an undetected conversation loop for 11 days. No guard fired.
- **The failure is distributed, not local.** A saga means every forward step declares its compensation up front. When step N fails fatally, the orchestrator fires compensations in reverse (LIFO) order to undo steps N-1 through 1.

## The Move

Build every side-effecting agent workflow as a saga: every forward action gets a paired compensating action, declared before execution begins. Layer three guard systems on top.

### 1. Saga compensation (LIFO undo stack)
- Every tool call that mutates external state also registers its compensating action on a per-workflow stack (Redis list, PostgreSQL, or in-memory during development).
- On `FAILED_FATAL`, the saga manager pops compensations in reverse order and dispatches them as CRITICAL-priority jobs.
- Compensations must be idempotent — running the same compensation twice must produce the same final state.
- **Real-world example:** Insurtech workflow (add dependent → schedule deduction → endorse policy → issue card). If card issuance fails, the saga fires: cancel endorsement → cancel deduction → remove dependent from HRMS.

### 2. Loop detection and circuit breakers
- Track tool-call sequences per session window. Flag when the same tool is called N times with the same parameters within a time window (e.g., 3 identical calls in 60 seconds).
- Implement circuit breakers: after N consecutive failures, open the circuit and stop dispatching. Prevents cascading retries that compound cost.
- Timeout per tool call + overall workflow timeout. An agent silently looping for 35 minutes is not a slow agent — it's a runaway agent.
- Libraries: `agentguard` (Python, MIT) provides circuit breakers, LLM-aware retry, idempotency keys, and loop detection out of the box.

### 3. Escalation gates and human checkpoints
- Define escalation rules as predicates on context: `repeatedFailure(attempts >= 3)` or `novelAction(similarityScore < 0.5)`.
- Before any irreversible action (write to production DB, send email, charge card), insert a human checkpoint if the action is HIGH risk or the agent has failed N times already.
- The best escalation is not "I can't do this" — it's "I need approval to charge $2,400. Reason: [X]. If we don't: [Y]. Here's what the agent would do and two alternatives."
- Never use "proceed anyway" as a fallback for irreversible actions. Document every override in the audit trail.

### 4. Idempotency keys on every side-effecting call
- Attach an `idempotency_key = hash(workflow_id + step_number)` to every external API call.
- If the call fails and you retry, the API returns the original result without re-executing. Eliminates duplicate charges, duplicate records, duplicate emails.
- Store idempotency keys in the saga log alongside compensation actions.

## Evidence

- **arXiv empirical study (Feb 2026):** AgentFail dataset — 307 real-world failure cases from Dify and Coze platforms. Failure distribution: 42% specification failures, 37% coordination breakdowns, 21% verification gaps. Key finding: failures propagate across workflow nodes; isolated retry per node is insufficient. — [arXiv:2509.23735v2](https://arxiv.org/html/2509.23735v2)
- **HN production post (Oct 2025):** Four LangChain agents in A2A coordination for market research. Two agents entered an infinite conversation loop. Cost grew from $127/week to $18,400/week over 4 weeks, reaching $47,000 total before detection. Root cause: no loop detection guard, no per-call timeout, no circuit breaker. — [Hacker News / Towards AI](https://news.ycombinator.com/item?id=45802430)
- **Saga pattern deep-dive (Aug 2025):** Indian insurtech case — agent adds dependent to HRMS, schedules prorated payroll deduction, endorses policy with insurer, then fails at card issuance. Without saga compensation: dependent exists in HRMS, deduction is scheduled, but no card — a partial state failure requiring manual cleanup across three systems. — [balaaagi.in / The Saga Pattern](https://balaaagi.in/posts/the-saga-pattern-undo-buttons-for-agents/)
- **Production fault tolerance library (Apr 2026):** `agentguard` — MIT Python library providing circuit breakers, LLM-aware retry with exponential backoff, idempotency, loop detection, and timeout enforcement for LangChain, AutoGen, CrewAI, or custom pipelines. — [GitHub: maheshmakvana/agentguard-llm](https://github.com/maheshmakvana/agentguard-llm)
- **Compensation architecture (Jun 2026):** Cordum's saga manager: per-workflow Redis stack stores compensation closures. On `FAILED_FATAL`, pops in LIFO order, dispatches as CRITICAL jobs gated by Safety Kernel, with full audit trail. Key insight: rollback is a second workflow, not a database undo button. — [cordum.io / AI Agent Rollback & Compensation](https://cordum.io/blog/ai-agent-rollback-compensation)
- **SAP enterprise checkpoint guidance (2025):** Human-in-the-loop checkpoints must be database-backed (not in-memory MemorySaver) for production approval workflows that must survive application restarts. Never use "proceed" fallback for irreversible actions. SLA-driven timeout escalation required. — [SAP Community](https://community.sap.com/t5/artificial-intelligence-blogs-posts/human-in-the-loop-sap-agents-approval-escalation-and-audit-series-2-part-5/ba-p/14372994)

## Gotchas

- **Don't skip compensating actions for "simple" steps.** The failure that burns you is always the one you thought was safe — a "harmless" notification email that triggered a downstream automation that sent a customer the wrong message.
- **Circuit breakers must distinguish transient from permanent errors.** Never retry on 400 Bad Request (client error — fix the prompt, not the request). Always retry on 429 Rate Limit, 500, 502, 503, 504.
- **Checkpoint state must survive restarts.** In-memory check-pointers (e.g., LangChain's MemorySaver) lose all state on restart. Use PostgreSQL or Redis-backed check-pointers in production.
- **Idempotency keys must be deterministic per workflow+step.** If you generate a new key on every retry, the API treats it as a new request. Store and reuse the key from the saga log.
- **Human escalation is useless without context.** "Agent needs help" is a ticket nobody can act on. Escalate with: the action, the reason, the alternatives, and the consequence of inaction.
