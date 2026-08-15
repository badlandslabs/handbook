# S-2687 · The Agent Failure Recovery Stack

When your agent loops eight times into a tool that can never succeed, burns $0.12, and returns `result: null` with no error message.

## Forces

- **Agents fail silently** — the dominant failure mode isn't a crash, it's the agent completing a step that silently did nothing, then proceeding as if it worked
- **Retry logic amplifies outages** — at 500 jobs/minute, three extra attempts per failing job adds 15,000 avoidable calls over 10 minutes; retries are only safe with idempotency keys
- **Traditional error taxonomy doesn't apply** — `try/catch` catches exceptions; it doesn't catch a tool that returns HTTP 200 with semantically wrong output or an agent that loops for 35 minutes without crashing
- **67% of AI system failures stem from improper error handling** — not from bad model outputs or algorithmic issues (Zylos Research, 2026)
- **88% of agent pilots never reach production** (IDC) — not because capability fails, but because the failure-recovery layer is under-built

## The Move

Build a layered resilience stack: classify errors first, then apply the right recovery primitive per class.

**1. Classify before you react.** Errors fall into three categories with different responses:
- **Transient** — network blips, rate limits, temporary unavailability. Retry with backoff.
- **Permanent** — auth rot, bad parameters, fundamentally broken tool. Fail fast, escalate.
- **Semantic** — tool returns 200 but the result is wrong or empty. This is the dangerous one — requires output validation, not HTTP status checking.

**2. Wrap every tool call in a circuit breaker.** Three failures in a 30-second window opens the breaker. The agent stops hammering the degraded dependency and either switches to a fallback or surfaces the failure. Monitor in 10-second windows for inter-agent calls, 60-second windows for LLM calls. — [Brandon Lincoln Hendricks](https://brandonlincolnhendricks.com/research/circuit-breaker-patterns-ai-agent-reliability)

**3. Checkpoint before every tool call.** Capture agent state (current step, accumulated results, pending queue) to durable storage before executing. On crash/restart, resume from the last checkpoint — don't replay the whole task. Without checkpointing, a 2-hour job that dies at step 347 starts from scratch. — [EngineersOfAI](https://engineersofai.com/docs/agentic-ai/long-horizon-planning/checkpointing-and-recovery)

**4. Give every action an idempotency key.** A retry replays the whole step — including the part that worked. Without a way to distinguish "already done" from "do it again," you get duplicate charges, duplicate writes, or infinite loops. Store the idempotency key alongside the checkpoint. — [Supergood](https://supergood.solutions/blog/when-your-agent-fails-silently)

**5. Route failures to a fallback chain, not a dead end.** When the primary tool fails and the breaker is open, the agent needs a defined next action: switch model provider, use a different data source, or degrade to a simpler approach. A chain of fallbacks — rather than a single point of failure — keeps the agent productive. — [Cordum](https://cordum.io/blog/ai-agent-circuit-breaker-pattern)

**6. Set hard escalation gates for irreversible actions.** Actions with monetary, legal, or data-destruction consequences need a human approval step before execution, not after. Observability tells you an agent went off-rails after it happens — escalation design is the enforcement layer that stops the action before it executes. Escalation rate targets: 10–15% normal; >60% means bottleneck; >20% means over-escalating. — [Digital Applied](https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026)

**7. Set max-turn limits with semantic checkpoints.** Nothing in the tool-call protocol forces the loop to terminate — the model decides turn by turn. Enforce a hard cap on iterations (e.g., 20 turns) and save a checkpoint at each meaningful step so a bounded restart is cheap. — [Mervin Praison](https://mer.vin/news/why-your-agent-thinks-a-failed-tool-call-succeeded/)

## Evidence

- **Research paper:** arXiv 2605.01604 identifies 7 production failure modes unique to agentic systems; standard metrics (ROUGE, BERTScore, accuracy) fail to detect 4 of them entirely. Standard benchmark scaffolds assume near-zero infrastructure failure; production reality is 12–18% tool call failure rates. — [arXiv](https://arxiv.org/html/2605.01604)
- **Practitioner post-mortem:** A lead-enrichment agent was "ghosting" — fetching contact data, starting enrichment, then vanishing with no crash logs. Root cause: three concurrent instances hitting a Clearbit API with a 10 req/sec rate limit, causing cascading timeouts that produced zero exceptions. Fixed with circuit breaker + rate-limit-aware queuing. — [Supergood](https://supergood.solutions/blog/when-your-agent-fails-silently)
- **Startup research:** Survey of 30+ European agentic AI founders (MMC Ventures, 2025): 90%+ report at least 70% accuracy as the threshold for deployment decisions; workflow integration (60%) and employee resistance (50%) are top non-technical barriers, not model quality. — [MMC Ventures](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)
- **Experimentation:** Ten identical runs against a deterministically-broken tool. Three of ten ended with `result: null`, no error message, $0.12 burned, nine turns consumed. — [Mervin Praison](https://mer.vin/news/why-your-agent-thinks-a-failed-tool-call-succeeded/)

## Gotchas

- **Status code validation is insufficient.** Tools that return HTTP 200 with empty or wrong results are the most dangerous class of failure. Validate output shape and content, not just the response code.
- **Retry without idempotency keys doubles your damage.** The retry replays the step. If the step wrote data or sent an email, you get duplicates. Design idempotency into the action schema before adding retry logic.
- **Escalation without working state is useless.** Paging a human with just the conversation transcript fails because the human has to reconstruct context. The handoff must include: current agent state, what has succeeded so far, what decision is needed, and what the risk is of doing nothing.
- **Max-turn limits catch loops but don't fix root causes.** A 20-turn limit prevents infinite loops but doesn't tell you *why* the agent needed 20 turns. Log the reasoning trace at each turn for post-mortem debugging.
