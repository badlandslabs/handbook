# S-1518 · The Expert Swarm Stack — When One Generalist Agent Can't Do Anything Well

You gave your agent one broad role: "Handle customer support." It wrote a refund email, then tried to fix the database schema, then called the shipping API incorrectly, then apologised for hallucinating a tracking number. The fix is not a better system prompt — it's a team.

## Forces

- **One agent, one context window, many jobs.** A generalist agent burns tokens on instructions for tasks it isn't currently doing, and degrades on each task because the others are always in the way. A 70B model asked to do research, code review, AND email writing simultaneously performs worse on all three than three 7B models each doing one.
- **Testing is impossible without boundaries.** You cannot regression-test "does the agent do the right thing?" across 15 possible actions. You CAN test "does the code-review agent correctly flag SQL injection?" when the boundary is clean. Unbounded agents are untestable agents.
- **Failure cascades in monoliths.** One bad output propagates to the next step. In a team of specialists, a bad output from the research agent fails loudly at the handoff — it never reaches the synthesis agent — because each agent's output has a schema.
- **Latency compounds in sequential chains.** Passing everything through one large model on every step is expensive. Small models handle deterministic steps (routing, formatting, validation) at a fraction of the cost and latency. The big model is for decisions, not format conversions.

## The move

Break the monolith into a pipeline of focused, single-responsibility agents. Give each a tight role, a constrained toolset, and a structured output schema. Route work between them with explicit handoff protocols.

- **Decompose by task type, not capability level.** Separate agents for: ingestion → validation → analysis → synthesis → delivery. Each agent's role fits in a single sentence.
- **Size each agent to its task.** Use a 7B–13B model for deterministic steps (routing, reformatting, rule enforcement). Reserve 70B+ for steps requiring genuine reasoning or creativity. The cost and latency difference is 10–50x.
- **Constrain each agent's toolset to its domain.** The email agent gets a compose tool and a template library. It does not get `exec_sql`. The code-review agent gets `grep`, `diff`, and a linter. It does not get a web browser.
- **Enforce structured handoffs.** Every agent output must conform to a schema before the next agent accepts it. A JSON schema validator in the handoff layer catches degradation before it propagates. This is the wire protocol, not just a prompt convention.
- **Add a router or orchestrator at the entry point.** A lightweight classifier (even a fine-tuned 1B model or a keyword heuristic) routes the input to the correct specialist. This keeps the specialist prompts lean — they never see inputs outside their domain.
- **Isolate failures to the responsible agent.** If the analysis agent crashes, the ingestion agent's output is preserved. The pipeline retries or escalates the analysis step, not the whole run. Checkpoint after each stage.
- **Use the big model as a reviewer, not a worker.** At critical handoff points (or for final synthesis), route to a frontier model for quality gating. This is the most expensive call in the pipeline — keep it to one or two per run.

## Evidence

- **Engineering post — Harsh Rastogi (Modelia.ai, March 2026):** Documented two production failures from monolithic agents — a candidate evaluation agent hallucinating tool parameters and approving flawed outputs, and an image-generation agent optimizing for completion over quality. Solution: "A pipeline of focused agents outperforms one monolithic agent. Each agent is simpler to test, debug, and improve." — [URL](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **COMPEL Framework — Operational Resilience for Agentic AI (April 2026):** Failure taxonomy includes "planning failures" where an agent omits steps — the fix is to decompose tasks into agents with explicit, isolated responsibilities so missing steps become visible. Also recommends chaos engineering: inject tool timeouts and resource unavailability, observe how each specialist agent recovers independently. — [URL](https://www.compelframework.org/articles/operational-resilience-for-agentic-ai-failure-modes-and-recovery)
- **GitHub — Mlakshay01/Empirical-Evaluation-of-Multi-Agent-Orchestration-Frameworks (July 2025):** Benchmarked LangChain, CrewAI, and AutoGen with local LLaMA 3.2 across multi-document summarisation, report generation, web research, and code generation. Found that framework overhead (serialisation, handoff overhead) was significant with smaller models — suggesting that pipeline design choices (how agents hand off, how much context each receives) matter as much as model size. — [URL](https://github.com/Mlakshay01/Empirical-Evaluation-of-Multi-Agent-Orchestration-Frameworks-for-Complex-Task-Automation)
- **n8n Blog — Production AI Playbook (June 2026):** "The challenge isn't that multi-agent systems are inherently fragile — it's that teams build them the same way they built their first prototype, adding pieces incrementally without an architecture to hold them together." Recommends: clear boundaries between components, explicit interfaces, isolated failure domains, ability to test each piece independently. — [URL](https://blog.n8n.io/production-ai-playbook-complex-agent-patterns)
- **Show HN — Agent MCP Studio (85 days ago):** Built a browser-based MCP tool builder with a "strategies" framework for multi-agent collaboration. Their 10 collaboration strategies map to different handoff patterns — some agents vote, some delegate, some debate. The system exports as a Python MCP server. — [URL](https://news.ycombinator.com/item?id=47899375)

## Gotchas

- **The orchestrator becomes a bottleneck.** A poorly designed router sends everything to the "big" agent anyway, recreating the monolith. Test with adversarial inputs — does the router correctly reject out-of-domain requests, or does it pass everything through?
- **Handoff schemas drift.** If the email agent changes its output format, the next agent breaks silently until you test the integration. Treat handoff schemas as versioned contracts, not informal agreements.
- **Tool access creep.** Specialists accumulate tools over time. A code-review agent that started with 3 tools ends up with 12, and starts doing things it shouldn't. Audit each agent's toolset quarterly.
- **Latency compounds in synchronous pipelines.** Each agent step adds 200–2000ms. A 5-step pipeline with 3 frontier model calls is too slow for user-facing interactions. Use async pipelines for batch workloads; reserve synchronous chains for low-latency requirements.
