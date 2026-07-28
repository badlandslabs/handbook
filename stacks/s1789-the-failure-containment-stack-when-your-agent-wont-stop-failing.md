# S-1789 · The Failure Containment Stack — When Your Agent Won't Stop Failing

Your agent hit a bad API response at 11 PM. It retried. Got the same error. Retried with different parameters. Got a new error. Tried to work around that. Called two more tools to compensate. None of them were wired to stop. By morning it had burned $437 and produced nothing. No alert fired. No threshold tripped. The agent just kept going because nothing in the architecture asked: *what happens when a task genuinely cannot be completed?* This is the failure containment problem — not how to make agents smarter, but how to make them stoppable.

## Forces

- **Agents fail differently than software.** Traditional code crashes at a specific line. An agent fails through a chain of plausible decisions — each step looks reasonable in isolation, and together they produce confident, partially wrong output that nobody notices until a customer complains or an audit runs.
- **Recoverability is high but containment is low.** 86% of agent failures are recoverable, yet Gartner projects 40%+ of agentic AI projects will be cancelled by 2027 — not because models aren't good enough, but because the systems around them aren't built to handle failure.
- **Cost compounds invisibly.** Agent loops consume ~4x more tokens than standard chat; multi-agent systems can hit 15x. A single retry loop running overnight costs more than the infrastructure that was supposed to replace it.
- **Semantic errors bypass traditional exception handling.** A tool returning an empty result or a model hallucinating valid-looking JSON doesn't throw an exception — it returns HTTP 200 and silently corrupts downstream steps.

## The Move

**Layer five failure-containment mechanisms around every agent loop, starting from the outside:**

1. **Hard iteration caps** — Set `max_iterations` (LangChain defaults to 15) as a non-negotiable ceiling. This is your runaway-loop dead man switch. Never ship an agent loop without one.

2. **Per-tool circuit breakers** — Circuit breakers must be per-tool, not global. An agent with 15-25 tools backed by different services should not halt when one goes down. OpenAI Agents SDK raises `MaxTurnsExceeded`; wrap each tool call in a breaker that trips after N consecutive failures and probes recovery before resuming.

3. **Exponential backoff with jitter** — After each transient failure (429, 503, timeout), double the wait and add random jitter. Formula: `delay = min(base × 2^attempt + random(0, jitter), max_delay)`. Classify the error first — a retry loop hammering a 401 endpoint wastes tokens and time.

4. **Checkpoint-and-resume on multi-step workflows** — Serialize agent state (conversation history, intermediate tool results, current plan position) at each step boundary. When a step fails, resume from the checkpoint, not from scratch. This pairs with durable execution infrastructure (e.g., Temporal raised $300M Series D in Feb 2026 precisely because teams need long-running processes that survive crashes).

5. **Dead-letter queue with three recovery paths** — Tasks that exhaust retries, hit fatal errors, or exceed iteration limits go to a DLQ with captured failure context (error type, retry count, partial results, execution state). Route to: (a) auto-retry with a more capable model, (b) human-in-the-loop review, or (c) log-and-escalate. Classify the failure at capture time so routing is fast, not improvised.

## Evidence

- **Blog post (Neel Mishra, MLOps):** Four-category error taxonomy — Transient (retry with backoff), Semantic (re-prompt with corrective context), Resource (reduce payload or switch model), Fatal (abort and alert). "Classify before you retry." — [Neel Mishra, Agent Error Handling: Retries and Fallbacks](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Blog post (The Agentic Stack, Ashu Kumar):** Per-tool circuit breakers are mandatory because one failing service out of 15-25 tools should not halt the agent. Three states: Closed (normal), Open (fail-fast), Half-Open (probe recovery). — [The Agentic Circuit Breaker](https://theagenticstack.substack.com/p/the-agentic-circuit-breaker)
- **Case study (Tian Pan, May 2026):** A team building a multi-agent research tool discovered, on day eleven, that two agents had been cross-referencing each other's outputs in a loop. Bill: $47,000. No human saw the results. No alarm fired. "Nothing in the architecture asked: what happens when a task genuinely cannot be completed?" — [Dead Letters for Agents](https://tianpan.co/blog/2026-05-05-dead-letter-queues-agent-task-failures)
- **Blog post (Waxell AI, Logan Kelly, May 2026):** Nightly pipeline agent entered a retry loop around 11 PM. By 7 AM, thousands of identical failing tool calls, all billing. Fix: 20 minutes. Run duration: 8 hours. — [AI Agent Circuit Breakers: The Pattern Teams Need](https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern)
- **Engineering blog (Oracle Developers, Casius Lee, Mar 2026):** Agent deployed to scrape a website. Target updated structure. Tool returned empty result. Agent had no hard stopping condition. Retried 400 times in five minutes. Maximum iteration limit of three would have prevented the failure. — [What Is the AI Agent Loop](https://blogs.oracle.com/developers/what-is-the-ai-agent-loop-the-core-architecture-behind-autonomous-ai-systems)
- **Research post (Brandon Lincoln Hendricks, Autonomous AI Agent Architect):** AI DLQ must capture model hallucinations, token violations, and non-deterministic outputs — not just transport errors. Retry count alone cannot capture semantic failure weight. Cloud Pub/Sub + Cloud Tasks foundation for production DLQ systems on Google Cloud. — [Dead Letter Queues and Retry Policies for Production AI Agent Systems](https://brandonlincolnhendricks.com/research/dead-letter-queues-retry-policies-ai-agent-production)
- **Industry analysis (The Operator Collective, Mar 2026):** 86% of agent failures are recoverable. 40%+ of agentic projects will be cancelled by 2027 (Gartner). Only 14% of enterprise agentic implementations are production-ready. — [AI Agent Error Handling: When Your Bot Breaks Production](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)

## Gotchas

- **Naive retry loops amplify outages.** A fixed-interval retry hammering a rate-limited endpoint synchronizes with every other retrying client — the "thundering herd" problem. Always add jitter and cap at a maximum delay.
- **Max iterations is not a circuit breaker.** Iteration caps stop the agent from spinning forever, but they don't prevent a single step from calling a failing tool 400 times before the cap hits. You need both — iteration caps as the dead man switch, circuit breakers as the per-tool guard.
- **DLQ classification must happen at capture time, not at routing time.** Capturing only the raw error and retry count forces routing logic to infer what went wrong. Capturing the error type, partial results, and execution state at failure time makes routing deterministic.
- **Observability is not error handling.** A retry loop can fire for weeks without a single trace proving it fired. Recovery mechanisms and records of recovery are two separate builds — you need both a mechanism that catches failures and a trace that proves it worked.
