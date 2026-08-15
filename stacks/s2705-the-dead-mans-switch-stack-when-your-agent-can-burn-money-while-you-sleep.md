# S-2705 · The Dead Man's Switch Stack — when your agent can burn money while you sleep

When your agent runs autonomously, failures don't look like errors. They look like normal execution — more tokens, more API calls, more cost. The agent keeps working. The bills keep arriving.

## Forces

- **Agents fail creatively, not predictably.** Traditional software throws exceptions; agents produce wrong outputs that look correct. The failure mode is invisible until the invoice arrives.
- **Retry logic compounds the problem.** When a tool call fails, the agent retries. If the retry also fails, it retries again — cascading into a death spiral that burns budget without producing value.
- **Silent failures are the worst failures.** The most dangerous incidents involve agents that keep running, keep producing outputs, and those outputs are based on tool calls that silently returned auth errors or stale data.
- **What stops the agent is never built-in.** Frameworks ship iteration limits as crude bounds but no behavioral loop detection. The safeguard is always your job to add.
- **Context window compression degrades reliability over time.** The longer a chain runs, the more the agent loses track of what it already did, re-implements solutions, or contradicts earlier decisions.

## The move

Build a three-layer failure containment system around any autonomous agent. No single layer is sufficient; together they make runaway agents nearly impossible.

### Layer 1 — Hard cost circuit breaker

Set a maximum spend per session *before* the agent starts. This is not a budget warning — it is a kill switch. When the cap is hit, the agent stops regardless of what it is doing.

- Set `recursion_limit` in LangGraph (~$5 loop kills per the cost-cap literature) or equivalent in your framework
- Set `max_iterations` on agent executors with `early_stopping_method='generate'` (reduces token waste by 92% per one benchmark)
- Add a proxy wrapper via `tenacity` with `stop_after_attempt(3)` for tool call retries — never let the agent decide its own retry count
- Use deterministic policy enforcement (FailWatch pattern): hard blocks on numeric limits, regex patterns, and business rules — no LLM involved

### Layer 2 — Behavioral loop detection

Cost caps stop the agent from running too long. Loop detection stops it from running in circles.

- Track message/response hashes across conversation turns; if the same semantic state repeats N times (N=3 is a common threshold), halt
- Detect tool-call oscillation: agent alternating between two tools without progress
- For LangChain agents: set `max_iterations=10` and `early_stopping_method='force'` once output quality degrades
- For CrewAI: the agent loop detection middleware (open GitHub issue #4682) addresses behavioral repetition in extended runs — or implement a custom middleware that compares recent tool call sequences
- For A2A/multi-agent systems: track inter-agent message IDs. Two agents exchanging messages in a closed loop with no external resolution is a $47,000 pattern

### Layer 3 — Human-in-the-loop escalation

Not every failure needs to stop the agent. But some decisions should never be made autonomously.

- Tier actions by risk: read-only → low-risk write → high-risk write → irreversible. Apply escalating approval gates per tier
- Build a handoff context package: when escalating, transmit the full state snapshot (tool results, conversation history, confidence scores) — not just a vague "something went wrong"
- For async teams: the approval queue should be async and auditable. A human should be able to approve, reject, or redirect with full context
- Calibration: auto-escalate when confidence drops below a threshold, when a tool returns an unexpected schema, or when the agent requests a permission it shouldn't need
- Test the escalation path. Teams that build approval gates but never verify they fire under real conditions discover the gap in production.

## Evidence

- **HN Ask HN thread on agentic AI limitations:** Practitioners report agents "lose track of what they already did, re-implement things, or contradict decisions from 20 minutes ago" — root cause is context compaction degrading reliability over long chains. Solution: external state that survives context compression.
  — *Ask HN: What are the biggest limitations of agentic AI in real-world workflows?* — https://news.ycombinator.com/item?id=47039354

- **Engineering post / viral Medium story — $47K infinite loop:** A team deployed four LangChain agents with A2A communication for market research. Two agents entered a recursive loop: Agent A asked Agent B a question, Agent B's response triggered Agent A to ask a follow-up. For 11 days, no errors fired, no alerts triggered. Costs escalated: $127 (week 1) → $891 → $6,240 → $18,400 → $47,000 total. No max iterations cap existed. The loop only ended when someone manually shut it down.
  — *We Spent $47K Running AI Agents in Production* — https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33

- **GitHub / OWASP taxonomy — five failure classes:** Agent failures fall into five categories: prompt injection, tool call failures, reasoning errors, state corruption, and cascading external dependencies. Tool failures specifically manifest as schema mismatches (agent retries → loops), permission denials (agent tries workarounds → token waste), timeouts (agent waits indefinitely → stuck), and network errors (agent retries → rate limit cascade).
  — *AI Agent Failure Modes: A Cited Taxonomy (2026)* — https://buildingeffectiveagents.com/failure-modes/

## Gotchas

- **Iteration limits ≠ loop detection.** `max_iterations` caps total turns, not behavioral repetition. An agent can call the same wrong tool 10 times and stop because it hit the limit — not because it noticed it was looping. You need both.
- **Transients are not failures.** Network timeouts and 429 rate-limit errors are the most common tool failures and both are retryable — but letting the model handle every retry adds latency and token cost for no benefit. Build retry logic at the infrastructure layer, not the agent layer.
- **Silent auth failures are the most dangerous.** When a tool call returns an auth error but the agent silently falls back to degraded behavior, the output looks fine. The agent keeps running. The user sees no signal that the system is compromised. Instrument every tool call with explicit result validation before passing output to the next step.
- **The approval gate must be tested under load.** Teams build human-in-the-loop escalation but never verify it fires in the actual failure scenario. The escalation path is the one code path you cannot afford to leave untested.
