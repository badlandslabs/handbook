# S-1066 · The Invisible Failure Stack — When Your Agent Succeeds and Burns $47K Instead

Agents fail differently from traditional software. They don't crash — they loop. They don't error — they drift. They don't timeout — they silently spend. The failure modes unique to LLM agents are invisible to every monitoring tool built for deterministic systems, and the cost of missing them is measured in tokens, not errors. This is the Invisible Failure problem: your agent is failing and nothing in your stack is telling you.

S-1064 covers trajectory evaluation. This entry covers the failure modes evaluation doesn't catch — the silent, financially destructive patterns that emerge from agents' non-deterministic nature.

## Forces

- **Agents have no completion signal.** Unlike a function that returns or a script that exits, an LLM agent's "done" is a prediction it makes about itself. It can be wrong, and it is frequently wrong, especially under time pressure or when a task is partially complete.
- **The loop is the failure, not the exception.** Infinite loops are not edge cases in agentic systems — they are the default failure mode when task completion is ambiguous and retry is free. Every agent framework defaults to retry on failure, and retry loops compound into runaway token spend with no crash to trigger an alert.
- **Soft failures outnumber hard failures 10:1.** The L4 study (FSE 2025, 428 real LLM training failures) found 89.9% of failures require manual log analysis, 34.7 hours average diagnosis time, 16.92 GB of logs per incident. Production agents fail silently on wrong format, wrong tool choice, wrong assumption — and return HTTP 200 doing it.
- **Cost accumulation is decoupled from error rate.** A failed API call costs tokens. An agent looping for 11 days on two agents talking to each other also costs tokens — but no alert fires because no error was logged.

## The Move

The pattern is **layered failure containment** — treating agent failure not as a catch clause but as a multi-level system that detects, contains, limits, and recovers from the three invisible failure modes: runaway loops, dead-end states, and silent cost accumulation.

### Loop detection and hard caps

- Set `max_iterations` as a hard budget guard, not a soft suggestion. CrewAI's default of 25 iterations is dangerous in multi-turn tasks; safe production ceiling is 5–8 for single-task agents, with escalation paths for complex tasks. Budget monitoring tools like AgentBudget log cumulative token spend per session and alert on threshold breaches — treating cost as a first-class signal.
- Track action fingerprints: if the agent's last N tool calls are identical to its previous N, it is looping. Hash the tool name + argument structure and detect repetition. This catches loops that tool-level `max_iter` misses — especially when the agent varies arguments slightly while achieving nothing.
- Log every loop detection event with the full action history. Loops are diagnostic — a looping agent tells you the task was underspecified, the available tools were inadequate, or the success condition was undecidable.

### Dead-end state trapping

- Design explicit recovery states for every agent terminal state. The "unstable bug wall" pattern in coding agents — where fixing one bug regresses another in an infinite cycle — is caused by agents modifying state without understanding how it arrived there. Apply "Chesterton's Fence for agents": document the current state before modifying it, and verify the path to the desired state exists.
- Add outbound transitions from every safety/hold state. State machine agents that introduce `NEEDS_HUMAN_REVIEW` or `UPDATE_NEEDED` frequently fail to add outbound paths from those states — trapping the agent permanently.
- Use per-object reasoning traces that track state history before each modification, preventing the agent from undoing its own progress without awareness.

### Degradation ladder (recover gracefully)

- Level 0 — Circuit breaker: detect the failure type, halt further tool calls, log the state.
- Level 1 — Fallback model: swap to a cheaper/faster model for retry (LiteLLM's automatic provider failover supports this across OpenAI, Anthropic, Azure, and self-hosted endpoints).
- Level 2 — Simplified toolset: reduce available tools to the minimal set for the detected task type, reducing the agent's action space and the chance of mis-selection.
- Level 3 — Human-in-the-loop escalation: surface the agent's reasoning trace and current state to a human with a forced decision point.
- Each level degrades capability slightly and costs slightly more human time — but stops token burn. The agent "keeps moving, just with less convenience at each level."

## Evidence

- **Engineering post:** A 4-agent LangChain A2A system for market data research burned $47,000 over 11 days when two agents entered an unmonitored conversation loop. No error was logged. No alert fired. The loop ended when the API budget was manually reviewed — Towards AI documented the incident and the recovery in detail. — [Towards AI — We Spent $47,000 Running AI Agents in Production (Oct 2025)](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)

- **GitHub repo:** The AgentBudget library formalizes budget-aware agent design — logging cumulative token spend per session, alerting on threshold breaches, and integrating with CrewAI and LangChain as a first-class monitoring primitive. This reflects the community standardizing around token cost as a failure signal equivalent to error rate. — [AgentBudget GitHub (2026)](https://github.com/AgentBudget/agentbudget)

- **Engineering post:** Multi-agent coding systems frequently trap agents in dead-end states by adding safety states (UPDATE_NEEDED, NEEDS_HUMAN_REVIEW) without outbound transitions — the agent correctly detects a problem, enters the safety state, and cannot exit it. VS Code's multi-agent development blog cites the MASFT failure taxonomy (Berkeley, 2025) as the canonical reference for this failure class. — [VS Code Blog — Your Home for Multi-Agent Development (Feb 5, 2026)](https://code.visualstudio.com/blogs/2026/02/05/multi-agent-development)

- **Technical guide:** LiteLLM's production proxy implements automatic provider failover — when one LLM provider errors or rate-limits, the request routes to the next configured provider without agent awareness. This is the standard production pattern for the "Level 1" degradation step. — [LiteLLM Docs — Fallbacks (Provider Failover)](https://docs.litellm.ai/docs/proxy/reliability)

## Gotchas

- **Soft budget limits don't work.** Setting a $100/month budget on an agent that loops at $0.02/token means the loop runs for 5,000 iterations before stopping. Budget limits must be iteration-based first and token-based second — iteration caps halt the loop immediately; token budgets only matter if you check them.
- **Recovery is not the same as retry.** Most frameworks retry on failure by default — but retry without state inspection just reproduces the same failure with different random seeds. Effective recovery means: diagnose what went wrong, correct the input, then retry. Retry without diagnosis is just a more expensive failure.
- **The agent's confidence is not a reliability signal.** Agents report high confidence while producing wrong outputs, looping silently, or drifting from the task goal. Confidence scores are useful for human-facing UX, not for automated reliability decisions. Treat every agent output as untrusted until validated.
- **Dead-end detection requires state observability you probably don't have.** If you can't observe the agent's full reasoning trace and tool call history at the moment of failure, you can't diagnose whether it hit a dead-end or simply completed. Invest in structured agent logging before deploying agents into production workflows with real consequences.
