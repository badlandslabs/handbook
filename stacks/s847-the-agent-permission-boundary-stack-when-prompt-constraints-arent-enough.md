# S-847 · The Agent Permission Boundary Stack — When Prompt Constraints Aren't Enough

Your agent is authorized to process refunds. A well-crafted system prompt says "never approve over $500." On a long conversation, under load, with a creative user — it approves $2,000. The API returns 200. No exception fires. The money is gone. Prompts are not permissions.

## Forces

- **LLMs reason about intent, not policy** — a constraint embedded in a prompt is a suggestion to the reasoning layer, not a wall at the execution layer; the model can drift when context is long, adversarial, or simply unusual
- **Fail-open is the default in most frameworks** — when an external validator is unreachable or a guard check times out, many agent frameworks proceed with execution anyway, because "the action was already decided"
- **Compounding autonomy compounds risk** — a 5-step agent with partial failure can leave the world in a half-committed state that retries cannot fix and rollback cannot cleanly undo
- **The legal and financial accountability question** — if an agent over-refunds or over-approves, the buck stops with whoever built or deployed it; the distinction between "prompt failure" and "architectural failure" matters to auditors and regulators

## The move

Build a deterministic permission layer between the LLM's output and every side-effecting action — **LLMs propose, the boundary enforces.**

**1. Separate intent from permission.** The LLM generates a structured proposal (action type, target, parameters, amount). The permission layer evaluates it against registered policy rules. The LLM never has direct write access to anything that matters.

**2. Implement fail-closed at the boundary.** If the permission layer is unreachable, the action is blocked by default. FailWatch (HN Show HN, Ludwig1827) codifies this: "Math > Prompts — deterministic Python logic (Pydantic/Regex) for hard constraints." If the guard server is down, the action is blocked, not bypassed. [news.ycombinator.com/item?id=46529092](https://news.ycombinator.com/item?id=46529092)

**3. Classify actions by risk and gate accordingly.** Not all actions need the same scrutiny. Low-risk reads get a fast path; writes, deletions, and financial operations require the full permission check. The HN discussion on controlling agents with real actions (thesvp/limits.dev) surfaces three tiers: structured data validators (regex, Pydantic schemas), unstructured output classifiers (LLM-as-judge), and hard guardrails (deterministic rule engine). [news.ycombinator.com/item?id=47134506](https://news.ycombinator.com/item?id=47134506)

**4. Design for saga-style rollback on multi-step workflows.** When a multi-step agent partially succeeds — booking a flight but failing on payment — retries won't help. The Runtime Rollback Pattern (Agent Native, 2026) applies compensating transactions: each step in a saga has an inverse ("release the seat if payment fails") that the orchestrator executes on failure. LangGraph's `error_handler` pattern supports this: after retries are exhausted, the handler transitions to a `compensate` node that undoes only the steps that actually completed, keeping state persistently so compensation is precise. [www.langchain.com/blog/fault-tolerance-in-langgraph](https://www.langchain.com/blog/fault-tolerance-in-langgraph)

**5. Make every action idempotent.** Safe retries require idempotency keys on all write operations. If an agent retries a refund call after a timeout, the second attempt should not double-refund. The Supergood Solutions analysis (March 2026) frames this as a prerequisite: idempotency + retry + circuit breaker are the three legs of safe agent execution. [supergood.solutions/blog/systems-sunday-agent-failure-recovery-2026](https://supergood.solutions/blog/systems-sunday-agent-failure-recovery-2026)

**6. Gate financial and data-loss actions with human approval.** The dominant practitioner consensus from the HN thread: for high-stakes actions, the pattern is `LLM proposes → validator checks → human approves → real-world execution`. The validator is deterministic; the human is the last circuit breaker. This separates accountability from autonomy.

## Evidence

- **Show HN — FailWatch:** Built specifically for financial AI agents with production wallets. Enforces fail-closed safety: deterministic Pydantic/Regex constraints between agent and tool execution; if the guard server is unreachable, the action is blocked. "The scariest part wasn't the hallucination itself, but the failure mode: if my external validation service crashed or timed out, the default behavior in many frameworks was to fail-open and execute the tool anyway." — Sheeplover, 3 months ago. [news.ycombinator.com/item?id=46529092](https://news.ycombinator.com/item?id=46529092)

- **Ask HN — Controlling agents with real actions:** 20 practitioners discuss control architectures for agents that take real actions (refunds, DB writes, API calls). Consensus pattern: "LLMs are good at understanding intent, unreliable at following instructions — that's exactly why enforcement lives outside the LLM." vincentvandeth's approach uses a deterministic governance layer between model output and execution. [news.ycombinator.com/item?id=47134506](https://news.ycombinator.com/item?id=47134506)

- **LangChain Blog — Fault Tolerance in LangGraph (June 2026):** Documents the `error_handler` primitive for saga-style compensation in LangGraph workflows. "Agents are taking on more autonomy, and with that comes more power to act. They're booking flights, filing tickets, executing payments." The `compensate` node pattern provides atomic rollback of completed steps when retries are exhausted. [www.langchain.com/blog/fault-tolerance-in-langgraph](https://www.langchain.com/blog/fault-tolerance-in-langgraph)

## Gotchas

- **Trusting the LLM to enforce its own constraints** — the most common mistake; a prompt saying "never do X" has no enforcement mechanism; it is advisory, not architectural
- **Building fail-open by accident** — catching an exception and proceeding anyway, or treating a validator timeout as a pass; always treat "validator unreachable" as a deny
- **Skipping idempotency on high-frequency agents** — a retrying agent without idempotency keys will cause duplicate charges, duplicate emails, duplicate database entries; this is the silent killer at scale
- **Compensation without checkpointing** — you cannot rollback what you cannot see; LangGraph's `checkpointer` or Temporal's durable execution is a prerequisite for saga compensation to work correctly
