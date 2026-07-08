# S-803 · The Agent Failure Recovery Stack: Getting Agents to Resume, Not Restart

An agent that crashes mid-task and loses all progress is not production-ready — it's a demo. The failure recovery stack is the unsexy plumbing that separates agents that quietly burn $200 in API calls from agents that actually recover. This cycle covers the 2025-2026 convergence on durable execution, per-call retry contracts, and grounded self-correction.

## Forces

- **Bolted-on try/except is the losing play** — wrapping the whole agent in a retry block doesn't help when the crash is at step 7 of 12; you've now retried all 7 steps and hit the same error at step 7
- **Agents fail silently** — the worst failure mode is not an exception; it's a task that completes with the wrong answer and nobody notices until the invoice arrives
- **Self-correction is only as good as its grounding** — ungrounded Reflexion-style self-critique (model judging itself) is fragile; grounded correction (anchored in execution results, validators, or process reward models) is where real gains live
- **The framework boundary is dissolving** — Temporal, LangGraph, and Pydantic AI are all converging on durable execution as a first-class feature, and teams are composing them together

## The Move

**Build failure recovery into the execution substrate, not the agent logic.**

1. **Taxonomize errors before you handle them.** Agent errors fall into four categories, each demanding a different strategy: (a) transient errors (rate limits, timeouts, 503s — retry with backoff), (b) tool call failures (API unavailable, malformed response — fallback to alternative or surface to human), (c) model output failures (malformed JSON, invalid tool call — self-correct with structured validation), (d) logic failures (wrong plan, wrong assumption — grounded self-correction or escalation).

2. **Write per-call retry contracts, not blanket exception handlers.** Specify exception classes, max attempts, and backoff per call site. A retried step without an idempotency key duplicates the side effect it was trying to fix.

3. **Use durable execution as the default substrate.** Journal-based replay (record each step, replay on crash) or database checkpointing (persist state after each node) — both solve the same problem: resume at step N, not step 1. LangGraph's built-in persistence, Temporal's 9.1T lifetime executions, and Pydantic AI's durable primitives are all first-class now.

4. **Ground self-correction in external signals.** The Reflexion approach (verbal self-critique stored in memory, 91% pass@1 on HumanEval) revealed that LLMs cannot reliably correct reasoning errors without external signals. Pair self-correction with validators that return specific error messages, execution traces, or process reward model scores.

5. **Instrument for silence, not just crashes.** Silent failures — wrong answers that look complete — are the highest-risk mode. Use step-level checkpoint logging, confidence thresholds, and output validators to catch degradation before it reaches the user.

6. **Add human-in-the-loop gates at autonomy boundaries.** Before any action with irreversible consequences (writes, deletes, sends, payments), persist state and wait for confirmation. This is not a philosophical preference — it's the difference between a $300M cascade failure and a $50 interrupt.

## Evidence

- **Engineering post (Zylos Research):** Temporal raised $300M at $5B valuation (Feb 17, 2026), with 9.1 trillion lifetime action executions on Temporal Cloud — 1.86 trillion from AI-native companies alone. LangGraph, Pydantic AI, and OpenAI Agents SDK all adopted durable execution as a first-class feature by mid-2025. — [zylos.ai/research/2026-02-17-durable-execution-ai-agents](https://zylos.ai/research/2026-02-17-durable-execution-ai-agents/)

- **Engineering post (Zylos Research):** Reflexion (NeurIPS 2023) achieved 91% pass@1 on HumanEval using verbal self-critique stored in memory. Follow-on research found intrinsic self-correction (model judging itself) unreliable for reasoning errors without external signals. Grounded self-correction (anchored in execution results, structured critics, or PRMs) is the production standard by 2025. — [zylos.ai/en/research/2026-05-12-agent-self-correction-reflexion-to-prm](https://zylos.ai/en/research/2026-05-12-agent-self-correction-reflexion-to-prm/)

- **HN Ask post (yuer2025):** Four recurring production failure modes: (1) non-replayable decisions — implicit context lost across restarts, (2) brittle edge zone — self-correction loops fail because the validator lacks reliable ground truth, (3) cascade amplification — multi-agent errors compound without containment, (4) silent wrong answers that pass validation. — [news.ycombinator.com/item?id=46450307](https://news.ycombinator.com/item?id=46450307)

- **Engineering post (Markaicode):** Production LangGraph pattern: typed state management with `Annotated` + `operator.add` for list accumulation, `MemorySaver` checkpointing for in-memory recovery, `SqliteSaver` for durability across restarts. Also documents the silent 20-minute loop failure mode — agents that consume $200 in API calls before anyone notices. — [markaicode.com/langgraph-production-agent](https://markaicode.com/langgraph-production-agent)

- **Analysis (BestAIWeb):** BestAIWeb's agent reliability editorial (May 2026) documents the framework convergence: Temporal wrapping LangGraph, Temporal wrapping OpenAI Agents SDK, Pydantic AI plugging into both. "The boundary between agent framework and workflow engine is dissolving." — [bestaiweb.ai/langgraph-temporal-and-pydantic-ai-how-2026-frameworks-are-solving-agent-resilience](https://www.bestaiweb.ai/langgraph-temporal-and-pydantic-ai-how-2026-frameworks-are-solving-agent-resilience/)

- **Production guide (Maxim.ai):** The standard reliability triad for LLM apps: retries (exponential backoff for rate limits/timeouts), fallbacks (provider switching on persistent failure), circuit breakers (block requests to unresponsive services before cascade). — [getmaxim.ai/articles/retries-fallbacks-and-circuit-breakers-in-llm-apps-a-production-guide](https://www.getmaxim.ai/articles/retries-fallbacks-and-circuit-breakers-in-llm-apps-a-production-guide)

## Gotchas

- **Retrying without idempotency keys duplicates side effects.** A retried `send_email` step that doesn't check for prior sends will send duplicates. Every step that writes state needs an idempotency contract.
- **Self-correction loops can loop forever.** If the validator and the model are both wrong about the ground truth, you get infinite correction. Set max correction iterations and escalate to human review instead.
- **Durable execution ≠ durable correctness.** Checkpointing your agent state means you can resume from the right step — but only if the step that failed was idempotent. A failed database write that left the DB in a partial state will resume into that corruption.
- **Validation is a different component from the agent.** Do not ask the agent to validate its own output for correctness — use a separate validator function with deterministic checks, or a process reward model trained for the task.
