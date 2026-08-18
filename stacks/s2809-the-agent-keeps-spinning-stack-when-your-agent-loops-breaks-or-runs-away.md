# S-2809 · The Agent-Keeps-Spinning Stack — When Your Agent Loops, Breaks, or Runs Away

When your agent runs in circles for 35 minutes, silently exceeds your API budget, or crashes partway through a critical task with no way to resume.

## Forces

- Agents fail in qualitatively different ways than single LLM calls — they loop, drift, hang, and burn budget without throwing exceptions
- A crashed database replays its write-ahead log and recovers deterministically. A crashed agent carries LLM interpretation drift across its decision history — restart from the beginning and you rebuild on different judgments
- Recovery is a separate discipline from detection: the cheap fix breaks a repeater but fails on a wanderer, and routing everything to a human is expensive
- Most teams implement guardrails after the first incident — the production debt is already written
- Hard step caps and budget limits are the last line of defense, not the first — relying on them means the agent already failed silently

## The Move

Build a layered failure-handling system across five disciplines:

**1. Hard bounds at the loop level.** Set a maximum step count (e.g., `recursion_limit=12` in LangGraph). If the agent doesn't finish in N steps, stop, checkpoint whatever state exists, emit a structured stop reason, and route to escalation. This is the single most important guardrail — it prevents silent runaway without requiring any model awareness.

**2. Loop detection via progress metrics, not activity proxies.** API call counts and log volume rise during stuck loops too — they can't distinguish stuck from slow-converging. Track a progress metric that only increases on real forward progress (e.g., unique sub-tasks completed, output hash changes). A flat progress metric across N heartbeats means stuck.

**3. Recovery ladder: nudge → replan → reset → handoff.** Once a loop is detected, climb a bounded escalation path. A nudge re-injects the prior result with a replan prompt ("this exact call already returned X — choose a different approach"). If that fails, checkpoint state and restart the planning phase with fresh context. Only escalate to a human when all automated recovery paths are exhausted or the action is irreversible.

**4. Compensation workflows for side effects.** For agents that touch external systems, pre-author compensation workflows registered per step definition. These are not LLM-generated — they are deterministic scripts. When a step partially fails, compensation executes as an independent workflow with its own checkpoint chain. The alternative is accumulating inconsistency between checkpoint state and real-world state that no restart can reconcile.

**5. Defense-in-depth guardrails.** Four types, each assuming the others will fail: permission boundaries (least-privilege tool access per agent), output validators (check tool responses before they propagate), circuit breakers (stop hammering a failing dependency), and human-in-the-loop checkpoints (trip on confidence threshold, budget threshold, or irreversible-action detection). Hard token and dollar spending caps are the final circuit breaker.

## Evidence

- **HN Show HN:** Optio agent orchestration system uses checkpoints for retry and rollback — "I have them set checkpoints so they can revert easily and when they can't make an edit" — [Hacker News discussion on Optio](https://news.ycombinator.com/item?id=47520220)
- **GitHub:** `hailports/self-healing-agent` — a ~200-line dependency-free reference loop wiring retry with exponential backoff, circuit breakers, watchdogs, checkpoint/resume, and budget governor. Maps naive-loop failures to self-healing equivalents — [README](https://github.com/hailports/self-healing-agent)
- **Real incident:** Q3 2025 e-commerce refund agent issued ~$1.2M in unauthorized refunds across 340 transactions before detection — the agent had $500 no-review limit but lacked output validation and confidence-threshold checkpoints — [Agentbrisk incident reconstruction](https://agentbrisk.com/blog/ai-agent-failure-modes-real-incidents/)
- **Enterprise guide:** Four-type guardrail architecture (permission boundaries, output validators, circuit breakers, HITL) implemented at framework level before first production deployment — [Gheware DevOps AI blog](https://devops.gheware.com/blog/posts/ai-agent-guardrails-production-enterprise-2026.html)
- **Pattern catalog:** Stuck-loop recovery via bounded escalation ladder (nudge → replan → escalate → reset → human handoff) distinguished from slow-converging by progress metric, not activity — [agentpatterns.ai](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **Engineering post:** Compensation workflows must be pre-authored and registered per step definition — LLM-generated compensation creates a window where forward action completes but compensation is unavailable — [Tian Pan, March 2026](https://tianpan.co/blog/compensating-transactions-failure-recovery-agentic-systems)

## Gotchas

- **Activity proxies (tool call counts, log volume) flag stuck loops AND active loops** — they measure busyness, not progress. Use output-hash or sub-task-completion as your progress metric.
- **Step caps catch ceiling hits, not loops** — a loop within N steps isn't caught by `recursion_limit`. You need separate loop detection that checks state drift, not just step count.
- **Compensation that isn't registered before the forward action executes creates a gap** — the forward action completes but compensation is unavailable. Register compensation atomically with the forward action.
- **Checkpoint-and-resume requires idempotency key probes on restart** — verify that recorded effects match external system state before replaying. A drifted checkpoint that replays against an already-changed external system compounds the failure.
- **Confidence-threshold HITL fires on every turn if "confidence" reduces to vibes** — requires a measurable signal (classifier score, self-reported uncertainty, divergence between two verifier models) to avoid rebuilding per-iteration human review.
