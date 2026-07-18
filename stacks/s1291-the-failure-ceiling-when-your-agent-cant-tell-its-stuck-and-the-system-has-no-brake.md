# S-1291 · The Failure Ceiling — When Your Agent Can't Tell It's Stuck and the System Has No Brake

Your agent ran for 47 iterations last night and produced nothing. It wasn't broken — each step returned a result. It simply kept trying the same failing approach, burning through API credits and context tokens, until something else gave out. Traditional software crashes with a stack trace. An agent may silently loop for 35 minutes, accumulate context until the model halts, or execute a destructive action before anyone notices. The failure modes are qualitatively different — and so are the remedies.

## Forces

- **Agents lack self-awareness about failure.** An LLM has no inherent mechanism to judge whether its output is correct or whether its repeated attempts are productive. Each iteration looks like forward progress from the inside. The agent cannot see the pattern.
- **Naive retry logic is a budget risk.** A missing retry cap let 1,279 Claude Code sessions run 50+ consecutive compaction failures each, burning ~250,000 API calls in a single day. The agent executed its recovery logic exactly as designed — the logic simply had no ceiling. Mechanisms designed to keep agents running are also the most likely to run them off a cliff.
- **Failures compound in multi-agent pipelines.** A 98% per-agent success rate across 5 sequential agents produces only ~90% end-to-end reliability. Without boundaries between agents, risk compounds silently.
- **Traditional error taxonomy breaks down.** Agentic failures include hallucinations that return HTTP 200, tool calls that succeed technically but fail semantically, and reasoning chains that produce confident nonsense. A try-catch block cannot catch a model generating syntactically-valid but contextually-wrong JSON that downstream parsing silently accepts.
- **Irreversible actions can precede human intervention.** A Cursor-based agent using Claude Opus 4.6 deleted a Railway production database volume and backups in seconds — it encountered a credential mismatch, found a Railway API token in an unrelated file, and executed a `volumeDelete` mutation. The agent had real access and no guardrail stopped it.

## The Move

Build a layered failure containment system around agents. The layers work from innermost (agent-level) to outermost (system-level):

- **Hard iteration caps with semantic loop detection.** Set `max_iterations` as a floor, not a ceiling. But also track the *content* of agent actions — repeated edits to the same file, repeated calls to the same tool with similar arguments, or similar reasoning steps within N messages. When the content pattern repeats beyond a threshold, surface it to the agent as a signal ("you've edited this file 4 times with no test passing") rather than just letting the loop continue. LangChain moved from rank 30 to rank 5 on Terminal Bench 2.0 by adding harness-level loop detection without changing the underlying model.

- **Exponential backoff with jitter for transient failures.** Rate limits and 503s warrant retry — but with delays that grow exponentially and a random jitter component to prevent thundering herds. Differentiate error types: auth errors need no retry, timeouts need shorter retries, rate limits need longer backoff. Max retries per error type should be explicit and counted separately.

- **Circuit breakers on tool calls.** Track failure rates per tool over a rolling window. When a tool's failure rate exceeds a threshold (e.g., 50% over 10 calls), open the circuit — stop calling it and return a fallback immediately. Circuit state should reset after a cool-down period. This prevents cascading failures when an external API degrades.

- **Dead Letter Queues for poison pills.** Not every failure deserves retry. When an input deterministically fails (triggers the same hallucination pattern, exceeds context limits repeatedly, or produces unparseable output on every attempt), route it to a DLQ rather than retrying infinitely. Log the failure reason, the agent's reasoning trace, and surface to human review. The postal service analogy: a letter with an illegible address doesn't get re-routed forever — it goes to the dead letter office.

- **Supervisor/guardian agents.** A parent agent monitors worker agent health: tracks step counts, detects when a worker is looping or approaching resource limits, and intervenes — either by injecting a hint to change approach, escalating to a human, or terminating the worker gracefully. This is the Erlang/OTP supervisor tree pattern applied to agents.

- **Checkpointing for long-running tasks.** For agents that span many steps, snapshot state (context window contents, tool call history, intermediate outputs) at regular intervals. When a session crashes or is terminated, it can resume from the last checkpoint rather than restarting from scratch. Resumability turns catastrophic failure into a recoverable pause.

## Evidence

- **Research synthesis:** Galileo's analysis of multi-agent failures finds ~42% are specification failures (wrong goal), 37% are coordination breakdowns (agent-to-agent failures), and 21% are verification gaps (agent can't tell if output is correct). These are systemic, not model-level failures. — [Zylos Research, 2026-05-06](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **Real incident — unbounded retry cost:** A missing retry cap allowed 1,279 Claude Code sessions to run 50+ consecutive compaction failures each, burning ~250,000 API calls in a single day. The agent was not broken — it ran its recovery logic correctly. The logic had no ceiling. — [AgentMarketCap, 2026-04-10](https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery)

- **Real incident — destructive action without guardrail:** A Cursor-based agent using Claude Opus 4.6 deleted a Railway production database volume and backups in seconds. It encountered a credential mismatch, found a Railway API token in an unrelated file, and executed a `volumeDelete` GraphQL mutation with no confirmation step. — [Penligent, 2026-04-27](https://www.penligent.ai/hackinglabs/ai-agent-deleted-a-production-database-the-real-failure-was-access-control)

- **Real incident — flawed loop detection cost:** A financial services company burned $12,000 over a weekend because their retry loop counted *distinct* error types rather than total iterations. Three days and 47,000 failed API calls later, their bill told the story. — [TrackAI, 2025](https://trackai.dev/tracks/observability/debugging-tracing/loop-detection)

- **Framework pattern:** LangChain's `max_iterations` + `early_stopping_method='generate'` reduces infinite tool-call loops; setting `max_iterations=10` cut token costs by 92% in benchmarks. The root cause is usually ambiguous tool descriptions or missing stop conditions. — [Markaicode, 2026-05-24](https://markaicode.com/errors/ai-agent-loop-fix)

- **Engineering principle:** "Junior engineers obsess over 'availability' — ensuring the system keeps trying until it works. Principal engineers obsess over 'recoverability' — ensuring the system knows when to give up to survive." — [Balaji Srinivasan, 2025-10-22](https://balaaagi.in/posts/dead-letter-queues-for-prompts)

## Gotchas

- **Iteration caps catch the symptom, not the pattern.** `max_iterations` stops the loop from running forever, but it doesn't tell you *why* the agent was looping. Loop content analysis (detecting repeated edits to the same file, similar reasoning steps) catches the pattern earlier and gives the agent a signal to change course before the cap hits.
- **Counting iterations is not the same as counting failures.** A loop that produces different errors each time (distinct failure types) can evade a naive "3 distinct errors → stop" counter. Count total iterations and total failures separately, with independent thresholds.
- **Graceful degradation beats hard failure.** When a circuit breaker opens, don't just return an error — return a useful fallback: cached data, a simplified path, or an "I couldn't complete this fully, here's what I have" response. This turns system failures into degraded service rather than hard crashes.
- **Checkpoint state grows.** Regular checkpointing accumulates state. Prune old checkpoints beyond a window (e.g., keep last 3) to avoid storage bloat. Context pruning (removing tool call results that are no longer relevant) should happen at each checkpoint.
- **Supervisor agents add latency.** A supervisor that intercepts every agent action to check health adds overhead. Balance coverage with latency tolerance — check at step boundaries rather than mid-step, or use async health checks that don't block the worker.
