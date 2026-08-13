# S-2601 · The Agent Failure-Handling Stack — When Recovery Logic Runs Your Bill Up

Your agent's retry logic is running perfectly. It just doesn't know when to stop. You gave it backoff, fallbacks, and a self-healing loop — but no ceiling. It spent 11 days calling itself a $47,000 no-op. The problem is not that your agent failed. The problem is that your failure handling is unchecked.

## Forces

- **Recovery logic has no natural stopping point.** Unlike a developer writing a try-catch block, you are writing logic that decides whether to keep going. Without a hard ceiling, "keep trying" is the default outcome of every failure.
- **Agent success is not HTTP-visible.** A tool can return 200 and still be semantically broken — the wrong answer, the wrong resource, the wrong direction. Traditional error detection misses the failures that cost the most.
- **Partial progress is the normal state.** A multi-step agent fails at step 4 of 8 and you need steps 1–3 back. A restart wipes them. This is not how traditional software fails, and it is not how traditional software recovers.
- **The ceiling problem compounds.** A missing retry cap on a recovery path is invisible until it isn't. One misconfigured agent burned 250,000 API calls in a day executing the exact recovery logic it was given.
- **Permission boundaries don't match autonomy levels.** An agent with human-equivalent permissions and machine speed will take irreversible actions before a human can intervene. The approval gate designed for one doesn't work for the other.

## The Move

Build a failure-handling stack with three layers: **detection, recovery, and containment**. Each layer has a distinct job, and each has a hard stop.

### Detection Layer

- **Hard iteration cap** — set `max_iterations` as an enforced limit, not a soft suggestion. This is the single most effective guard against runaway loops. The 250,000-call incident had no retry ceiling.
- **Syntactic loop detection** — if the last N actions match a repeating subsequence (e.g., last 6 actions repeat a 3-action pattern), halt. This catches obvious tactical loops.
- **Semantic loop detection** — actions are diverse but no progress is being made. Track a progress metric alongside action sequences: if token cost grows at more than 10x the rate of output quality improvement over a sliding window, trigger a halt regardless of action variety.
- **Cost-output ratio monitoring** — every agent run should track cumulative token cost vs. verified output units. Alert when cost-per-output-unit exceeds a threshold, even if the run is technically still active.

### Recovery Layer

- **Exponential backoff with jitter** for transient errors — `delay = min(base × 2^attempt + random(0, jitter), max_delay)`. Prevents thundering-herd retry storms across distributed agents.
- **Fallback chain** — when primary model/tool fails, try alternatives in order (e.g., GPT-4o → Claude Sonnet → local model → graceful degradation). Each fallback should be logged with cost and latency.
- **Checkpoint-and-resume** — persist workflow state at defined boundaries (between agentic steps, after each tool call). On failure, resume from the last successful checkpoint instead of restarting. 82% of agent failures are recoverable; checkpointing makes recovery automatic.
- **Circuit breaker trip conditions** — trip not just on HTTP errors but on semantic indicators: consecutive failures, declining confidence scores, token cost growth without output progress, or repeated identical action sequences.

### Containment Layer

- **Permission ceiling** — agent actions that are irreversible (delete, deploy, send, write) require an explicit human-approval gate at a threshold. An agent with operator-level permissions at machine speed caused a 13-hour production outage by autonomously deciding to rebuild an environment.
- **Escalation queue** — when recovery attempts are exhausted, route to a human with the full diagnostic bundle: original query, error type, retry count, fallback history, timestamps, session ID, and checkpoint state.
- **Resumable workflow contract** — design the workflow so that after human intervention resolves the underlying issue, the agent can resume from where it left off. State must be externalized from the agent process.

## Evidence

- **Case study (Vectara/awesome-agent-failures, March 2026):** Four LangChain agents via A2A protocol ran an 11-day infinite loop producing zero output and $47,000 in API costs. Root causes: no iteration cap, no circuit breaker, no output monitoring, no semantic loop detection. Discovery came from a billing dashboard alert, not internal agent safeguards. — [URL](https://github.com/vectara/awesome-agent-failures/blob/main/docs/case-studies/langchain-a2a-47k-infinite-loop.md)
- **Case study (AgentMarketCap, April 2026):** 1,279 concurrent Claude Code sessions each ran 50+ consecutive compaction failures, burning ~250,000 API calls in one day. The retry logic had no cap — it was executing exactly as designed. — [URL](https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery)
- **Industry data (Easton, May 2026):** 87% of enterprise AI agent projects see >25% task failures within 3 months of production deployment. 82% of agent failures are recoverable. Proper retry implementations boost API success rates from ~85% to 99.5%. — [URL](https://eastondev.com/blog/en/posts/ai/20260527-ai-agent-monitoring-recovery)
- **Production pattern (AI Agents Blog, March 2026):** Five-pattern failure stack validated in production with Anthropic SDK: exponential backoff with jitter, circuit breakers, checkpoint-and-resume, fallback chains, and escalation queues. Each pattern addresses a distinct failure mode. — [URL](https://aiagentsblog.com/blog/agent-error-recovery-patterns/)
- **Incident (Zylos Research, May 2026):** An agent with operator-level permissions autonomously deleted and rebuilt a cloud environment, causing a 13-hour outage. Root cause: permission boundaries designed for human self-check rhythms, not machine-speed autonomous execution. — [URL](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

## Gotchas

- **`max_iterations` is not a circuit breaker.** It stops the loop but tells you nothing about why it stopped or whether progress was made. It is a floor, not a ceiling on quality.
- **HTTP 200 is not success.** Agentic failures often return successful status codes. You must check semantic output quality, not just HTTP status.
- **Checkpointing state that isn't externally persisted is useless.** Checkpoints saved to in-memory state disappear on restart. State must survive process death.
- **Fallback chains have costs.** Each fallback tier (model, tool, strategy) should be evaluated for cost and latency trade-off. A fallback to a more expensive model on every transient error defeats the purpose.
- **The escalation queue must include enough context to be actionable.** "The agent failed" is not a valid escalation. The bundle must include: original query, error classification, recovery history, checkpoint state, and session identifiers.
