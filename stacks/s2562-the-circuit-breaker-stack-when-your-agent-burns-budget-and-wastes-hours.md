# S-2562 · The Circuit Breaker Stack: When Your Agent Burns Budget and Wastes Hours

Your agent is stuck. It might be looping, waiting on a hung tool, or burning through tokens repeating the same failed action. You won't know until you check — or until the bill arrives. This is the failure you should have caught before shipping.

## Forces

- **Agents fail silently.** Unlike a web service that crashes and logs, an agent may loop for 35 minutes without any exception being raised. It just keeps calling the LLM, thinking it's making progress.
- **The failure modes are novel.** Specification failures (42% of multi-agent failures per Galileo 2025), coordination breakdowns (37%), and verification gaps (21%) don't map to traditional error handling.
- **Bounded autonomy is the hard part.** Teams know how to give agents capabilities. They forget to give them limits.
- **The cost surface is new.** A runaway agent doesn't just fail — it costs money on every retry.

## The Move

Build a three-layer defense: **prevent**, **detect**, **recover**.

### Prevention — Guard the Boundaries Before the Agent Runs

- **Max-turn budget:** Set a hard cap on LLM calls per session. AgentCircuit (GitHub: simranmultani197/AgentCircuit) implements this as a decorator with configurable limits — trips at $200+ of runaway spend without it.
- **Execution timeouts:** Kill any single tool call after N seconds. The agent moves on; you don't wait indefinitely.
- **Idempotency guards:** Wrap every stateful write with deduplication keys. If a retry replays an action, the second write is a no-op, not a double-charge.
- **Prompt-defined limits:** Embed the turn cap and escalation rules directly in the system prompt so the agent knows when to stop and ask.

### Detection — Catch the Loop Before It Escalates

- **Step deduplication:** Track a hash of the last N tool-call sequences. If the agent repeats the same action with the same context twice in a row, flag it.
- **Cost-per-task counters:** Per-task budgets that alert at 50% and hard-stop at 100%. The $47k case (Towards AI, Oct 2025) ran two agents in an infinite conversation loop for 11 days with no alerts.
- **Conversation-length monitoring:** Agents accumulating context toward context-window limits are a predictable failure precursor — watch the sequence length, not just the cost.
- **Trace analysis tooling:** agent-triage (GitHub: converra/agent-triage) replays production traces step-by-step, extracts behavioral rules from system prompts, and aggregates root causes across runs (e.g., "24 of 51 failures are missing escalations").

### Recovery — Stop, Escalate, or Degrade Gracefully

- **Circuit breaker on tools:** If a tool fails N times consecutively, stop calling it. Route to a fallback — cached result, cached model, or human review. AgentCircuit implements this as a decorator wrapping LangGraph, LangChain, CrewAI, and AutoGen.
- **Graceful degradation hierarchy:**
  1. Retry with exponential backoff (transient failures)
  2. Fall back to a cached or simpler result
  3. Degrade to a simpler model (e.g., switch from o3 to gpt-4o-mini)
  4. Escalate to human review
- **Human-in-the-loop checkpoints:** For high-stakes actions, insert an explicit interrupt. SAP's production pattern uses `LangGraph interrupt()` at defined checkpoints — the agent pauses and waits for explicit human approval before proceeding. (SAP Community, Apr 2026)
- **Self-termination:** In one real case (HN: "We put a coding agent in a while loop"), an agent actually used `pkill` to terminate itself after recognizing it was stuck. While emergent, this points to the value of giving agents explicit self-termination as a sanctioned tool.

## Evidence

- **$47k runaway bill:** A team ran 4 LangChain agents via A2A for market research. Two agents entered an 11-day infinite conversation loop. Cost escalated from $127/week to $18,400 in week four. — [Towards AI, Oct 2025](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)
- **Agent pkill itself:** When a coding agent was put in an autonomous while-loop for code porting (~1100 commits, ~$800 spent), one instance recognized its own stuck state and called `pkill` to terminate. — [Hacker News, "We put a coding agent in a while loop"](https://news.ycombinator.com/item?id=45005434)
- **88% never reach production:** The dominant reason is governance failure, not capability. Teams invest in evals and prompting but skip the handoff/escalation layer entirely. — [Digital Applied, Jun 2026](https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026)
- **Open-source circuit breaker:** AgentCircuit wraps LangGraph/LangChain/CrewAI/AutoGen with loop detection, auto-repair, output validation, and budget control via a single decorator. — [GitHub: simranmultani197/AgentCircuit](https://github.com/simranmultani197/AgentCircuit)

## Gotchas

- **Alerts are not prevention.** Watching a dashboard is not a circuit breaker. You need automated, enforced limits — not human operators watching for anomalies.
- **Bounded retries ≠ bounded loops.** Retrying a failing tool N times is different from detecting that the agent is looping on the same plan. Loop detection needs state across turns, not per-call.
- **Context accumulation is a silent killer.** Agents that don't fail loudly fail expensively — they keep context-growing until they hit the window limit or your bill.
- **Prompts that define capability but not limits.** The $47k team's prompt was 1,500 words of what the agent *should* do. It had no clause for what it *should not*. The agent that knows its boundaries is cheaper than the agent you have to rescue.
- **Recovery ≠ restart.** Don't just re-run the agent after a failure. Diagnose first — agent-triage-style replay to identify which step broke and whether the failure is systemic or a one-off.
