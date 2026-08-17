# S-2767 · The Fan-Out Stack — When Your Agent Waits for Five Things One at a Time

Your agent needs to check a database, query a vector store, call a currency API, hit a weather service, and look up a user record. You wrote it to do them one after another. Each call takes 1–3 seconds. Your agent takes 12 seconds to answer a question that could be answered in 2. The bottleneck is not model inference speed — it is sequential tool execution. This is the fan-out problem: agents that could run independent operations concurrently but don't, burning latency and cost unnecessarily.

## Forces

- **Sequential is the default because it's easy to write.** Most agent frameworks execute tool calls one at a time. Adding parallel execution requires either explicit async scaffolding or a framework that supports it natively.
- **Not all tool calls are independent.** Some depend on the output of others. You can't parallelize a DAG without understanding dependencies — doing it blindly produces wrong answers.
- **Latency matters in production UX.** A 12-second response vs. a 2-second response determines whether users trust the system or abandon it. In high-volume pipelines, the compounding cost is significant.
- **Naive parallelization introduces new failure modes.** What happens when one of five parallel calls fails? Sequential execution gives you atomic rollback; parallel execution requires explicit error handling per branch.

## The move

Structure agent tool execution as a directed acyclic graph (DAG) of independent branches, fan out all at once, and aggregate results on return.

- **Treat the agent's tool-call plan as a compilation target.** LLMCompiler (ICML 2024) formalized this: the LLM generates a plan where nodes are tool calls and edges are data dependencies. Independent nodes execute concurrently; dependent nodes wait.
- **Fan out for independent reads.** Any tool call whose output isn't consumed by another tool call can run in parallel with its siblings. Multiple data source queries, external API calls, vector searches — all prime candidates.
- **Fan in with an aggregator.** A dedicated result collector receives outputs from all parallel branches and synthesizes them into a single response for the next agent step or final output.
- **Use a function-calling planner that emits a DAG.** The LLM generates the execution graph (LLMCompiler), or a runtime planner analyzes dependencies and reorders tool calls (PASTE, March 2026).
- **Implement per-branch error handling.** Each parallel branch should timeout and fail independently. The aggregator needs a policy: return partial results, retry the failed branch, or escalate.
- **Enable async invocation at the framework level.** LangGraph, Google ADK, and OpenClaw all support this pattern natively. Microsoft Agent Framework ships a `ParallelAgent` with built-in fan-out/gather.

## Evidence

- **Research survey (Zylos Research, 2026-04-26):** Benchmarks across frameworks show consistent **1.8x–3.7x wall-clock speedups** and **up to 6x cost reductions** when agents schedule independent work concurrently via fan-out/fan-in. Five 2-second tool calls drop from 10 seconds sequential to ~2 seconds parallel. — [Zylos Research](https://zylos.ai/en/research/2026-04-26-parallel-concurrency-agent-execution/)
- **Independent corroboration (Particula Tech, 2026):** DAG approaches (LLMCompiler + PASTE speculative tool execution) confirm **36–50% wall-clock reduction** for production content and research workflows. — [Particula Tech](https://particula.tech/blog/dag-agent-orchestration-fan-out-fan-in-latency-parallel-execution)
- **Parallel tool optimization survey (Zylos Research, 2026-04-23):** Since the LLMCompiler paper (ICML 2024), every major model provider — OpenAI, Anthropic, Google — has shipped native parallel function calling. Production systems report **3–5x latency reductions and 40–70% cost savings**. — [Zylos Research](https://zylos.ai/en/research/2026-04-23-parallel-tool-calling-optimization-ai-agents)
- **Enterprise implementation (Microsoft ISE, 2026-06-12):** A large retail organization migrating from a modular monolith to multi-agent microservices found that **running concurrent specialized agents** — fan-out/fan-in — was the primary mechanism for reducing response latency and enabling agent reuse across teams. — [Microsoft ISE Developer Blog](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems/)
- **Framework support (Microsoft Agent Framework, 2026):** Ships a `ParallelAgent` pattern with explicit fan-out/gather for production use. — [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/concurrent)

## Gotchas

- **You must identify true independence before parallelizing.** If tool B's input depends on tool A's output, running them in parallel produces garbage. Model your dependencies first, then parallelize only the DAG leaves.
- **Timeout and error isolation is non-negotiable.** In sequential execution, one bad API call fails the whole run. In parallel, a slow call holds up the aggregator. Set per-branch timeouts and define what "good enough" partial results mean for your use case.
- **Watch for token overhead in aggregation.** Fan-out produces multiple independent outputs that must be re-injected into the agent context for synthesis. With many branches, this can re-create the context-window pressure the parallelism was supposed to reduce. Summarize or compress branch outputs before aggregation.
- **Not all models support parallel function calling well.** The LLM needs to generate a coherent DAG from a single prompt. Older models or models not fine-tuned for multi-tool planning may produce worse results with parallel tool calls than with sequential ones.
