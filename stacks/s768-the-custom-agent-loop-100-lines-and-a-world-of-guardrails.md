# S768 · The Custom Agent Loop: 100 Lines and a World of Guardrails

The moment you need an AI agent to run reliably in production — not as a demo, not as a prototype, but as a process that ships value continuously — you reach for a framework and it fights you. LangChain has 47 ways to do the same thing. CrewAI has opinions that don't match yours. AutoGen has 9 dependencies you can't upgrade. The move: write the loop yourself.

## Forces

- **Prototype speed vs. production weight** — frameworks get you from zero to spinning agent in an hour; by hour three you're fighting their abstractions instead of your problem
- **Dependency debt** — every framework pins versions of things you need to upgrade for your own reasons; the framework pins them for its own reasons; eventually you have two stacks in one process
- **Observability is the hard part** — a tracing framework doesn't know what your agent is *trying* to do; you need domain-specific instrumentation that no framework can provide
- **The loop itself is trivial** — the real complexity is tool calling, memory management, cost control, and error recovery; none of which a framework solves generically

## The Move

Build the core agent loop from scratch. It's approximately 100 lines of code combining four elements:

1. **LLM call** — pick your model, call it with structured output (Pydantic/Zod), get back a tool call or response
2. **Tool executor** — take the tool call, run it against your actual systems, return the result
3. **State accumulator** — maintain the conversation history and intermediate results; this is your memory
4. **Loop controller** — decide when to stop (max iterations, termination condition, confidence threshold)

Everything else — logging, rate limiting, budget circuit breakers, sandboxed execution, semantic memory retrieval, guardrails — lives *outside* the loop as orthogonal concerns.

The Digits ML team, running agents in production for accounting applications for 2+ years, recommends this explicitly: open-source frameworks are great for prototyping but bring too many dependencies for production. Their own agent core is custom.

## Evidence

- **MLOps World 2025 / Digits ML Team:** "Open source frameworks like LangChain and CrewAI are great for prototyping but bring too many dependencies for production. The recommendation? Implement your own core agent loop." — [digits.com/blog/ai-in-production-2025-slides](https://digits.com/blog/ai-in-production-2025-slides/)
- **AI in Production 2025 / Hannes Hapke:** "The term 'agent' might be doing more harm than good." — argues for "Process Daemon" framing; demonstrates core agent as ~100 lines combining LLM call, tool execution, state, and loop control — [digits.com/blog/mlops-world-2025-slides](https://digits.com/blog/mlops-world-2025-slides/)
- **HN / Mike Hearn:** "I recently built my own coding agent, due to dissatisfaction with the ones that are out there." — uses custom Docker container, shell-script-over-wire execution pattern, automatic checkpoints — [news.ycombinator.com/item?id=45429639](https://news.ycombinator.com/item?id=45429639)
- **HN / Philipp Dubach:** "The agent stack is splitting into specialized layers" — context/orchestration/sandbox/execution/context/infra each have different defensibility profiles; monolithic frameworks conflate layers with different rates of change — [philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)

## Gotchas

- **The loop is the easy part** — teams underestimate how much infrastructure they need around the loop before it's production-ready: structured logging on every tool call, budget circuit breakers, rate limit handling, and execution sandboxing
- **Writing your own loop means owning every failure mode** — runaway loops that call the LLM indefinitely are real; Zylos Research documented incidents costing $15 in 10 minutes to $47,000 over 11 days; hard budget limits and iteration caps are non-negotiable
- **Don't confuse "custom loop" with "no framework"** — you still use Pydantic for schema validation, LangSmith or Phoenix for tracing, and a vector store for memory; you're replacing the orchestration framework, not the tooling ecosystem
- **The prototype trap** — the moment a custom loop gets "good enough," resist the temptation to add features into it; keep it small and push complexity to the tool layer
