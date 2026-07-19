# S-1346 · The Stigmergy Architecture Stack — When Your Multi-Agent System Spends More Time Waiting Than Working

Your multi-agent pipeline runs three agents in sequence: Agent A produces output, Agent B waits for it, processes, then Agent C waits for B. Each handoff adds latency. Each agent-to-agent call multiplies API costs. The orchestration logic gets tangled in callback handlers. You are not parallelizing — you are just serializing with extra steps. This is the direct-communication deadlock, and it hits every team that graduates from a single agent to a multi-agent system. The fix is stigmergy: stop making agents talk to each other and make them write to and read from a shared environment instead.

## Forces

- **Direct messaging creates tight coupling and compounding latency.** Every agent-to-agent round trip is a blocking wait. Three sequential agents with 2-second LLM calls and 500ms API overhead = 7.5 seconds minimum, even on trivially parallelizable work.
- **Token costs explode under direct orchestration.** Every intermediate result passes through a model's context twice (once to write the result, once for the next agent to read it). For multi-step pipelines with branching, this multiplies fast.
- **Orchestration logic becomes the bottleneck.** Hand-rolled callback handlers, message queues, and state machines for inter-agent communication are where production bugs live — not in the agents themselves.
- **The environment is already the shared state.** You already have a database, a filesystem, a vector store, an issue tracker. Using it as the coordination layer instead of building a custom message bus is simpler and more resilient.

## The move

Stigmergy is biological in origin: ants don't coordinate directly — they deposit pheromones in the environment that other ants detect and respond to. Applied to multi-agent systems, the equivalent is: agents write outputs to a shared store (S3, SQLite, a document, a database table) and read from that store when they have work to do, rather than waiting for a synchronous handoff.

- **Define a shared schema for the work artifact, not the protocol.** Instead of "Agent A sends a message to Agent B", define what the shared state looks like at each stage (e.g., `{"stage": "url_collection", "urls": [...], "stage": "analysis", "findings": [...]}`). Any agent can read any stage. Agents are decoupled from each other.
- **Agents read what they need, write what they produce, then exit.** The agent's job ends when it writes its output to the store, not when it delivers it to the next agent. The next agent's job starts when it reads that output.
- **Use a polling or event trigger for downstream agents.** The simplest version: a scheduler or orchestrator polls for completed stages and spawns the next agent. The most resilient: a workflow engine (Temporal, Prefect, Dagster) triggers on artifact completion events.
- **Store structured artifacts, not raw text.** Pass JSON or Markdown with typed fields (`urls`, `findings`, `code_review`). This lets downstream agents parse reliably without re-parsing natural language output.
- **Add a critic/evaluator as a separate agent that reads the final artifact.** Anthropic's GAN-inspired harness pattern applies here: separate the worker from the judge. The evaluator doesn't need to wait for anyone — it reads the completed artifact when it appears and judges quality independently.
- **Instrument token usage per stage.** Stigmergy naturally enables this: each agent's input tokens = its read of the artifact, output tokens = its write. Track these and you can see which stage is expensive and whether the artifact is carrying too much context.

## Evidence

- **r/LocalLLaMA discussion (5 months ago):** A practitioner implemented stigmergy for multi-agent orchestration and documented 80% token reduction versus direct agent-to-agent communication. The approach eliminates blocking waits — agents write to the shared environment and exit, rather than holding connections open. Agents check the environment on their own schedule, enabling true parallelism. — [Reddit r/LocalLLaMA — Stigmergy pattern for multi-agent LLM orchestration](https://www.reddit.com/r/LocalLLaMA/comments/1qv3o3o/p_stigmergy_pattern_for_multiagent_llm/)

- **Anthropic Engineering — Harness design for long-running application development (2025):** Anthropic's internal work on autonomous full-stack application building introduced a GAN-inspired architecture: separate the generator agent (does the work) from the evaluator agent (judges it). Key finding: "Tuning a standalone evaluator to be skeptical is far more tractable than making a generator critical of its own work." The evaluator reads completed artifacts independently — a form of stigmergy where the evaluator is decoupled from the generator. — [Anthropic Engineering — Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)

- **HN Show HN — OpenSwarm (4 months ago):** An open-source multi-agent Claude CLI orchestrator implements a Worker → Reviewer → Test → Documenter pipeline with a shared Long-term Memory layer (LanceDB + embeddings) as the coordination substrate. Agents read from the shared memory rather than from each other directly, enabling the orchestrator to dispatch agents asynchronously and reuse context across sessions. — [HN Show HN — OpenSwarm: Multi-Agent Claude CLI Orchestrator](https://news.ycombinator.com/item?id=47160980)

- **LangChain 2025 Production Survey (cited by Agentika):** 73% of production systems use simple chains; only 12% use full agents with loops. For the 12% running agentic systems, token costs and latency are the primary pain points — both addressed by decoupling agent communication from the inference path. — [Agentika — LLM Orchestration Patterns That Actually Work](https://agentika.uk/blog/llm-orchestration-patterns)

## Gotchas

- **Stigmergy adds infrastructure complexity.** You now have a shared store, a polling or event mechanism, and an artifact schema to maintain. For teams that don't have this infrastructure already, the overhead may exceed the benefit. Start with a lightweight store (SQLite, S3, or even structured files) before adding a workflow engine.
- **The artifact schema is a contract that will break.** As agents evolve, the schema must evolve with them. Version the artifact format and handle schema migration explicitly — an agent reading a stale artifact format will produce garbage silently.
- **No atomicity without a real workflow engine.** If you use a simple shared store without transactional semantics, a crashed agent mid-write can leave the store in an inconsistent state. Use a workflow engine (Temporal, etc.) for state management and retry logic if reliability is non-negotiable.
- **Agents still need context to act.** Stigmergy reduces token costs by eliminating redundant passes, but the downstream agent still needs to understand what the upstream agent produced. Poorly structured artifacts create as many problems as direct messaging — invest in artifact design.
- **The evaluator pattern requires a skeptical judge, not a friendly one.** Anthropic found that agents confidently praise their own work. The evaluator must be tuned or prompted specifically to be critical — a generic model will rubber-stamp mediocre outputs.
