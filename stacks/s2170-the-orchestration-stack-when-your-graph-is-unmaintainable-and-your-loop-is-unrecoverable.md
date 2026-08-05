# S-2170 · The Orchestration Stack — When Your Graph Is Unmaintainable and Your Loop Is Unrecoverable

Your orchestration has two failure modes and they are opposite. Option A: you build a graph with fifteen nodes and six conditional edges, and debugging means reading through forty lines of LangGraph to trace which state you're in. Option B: you write a while loop, it fails at step seven, and the only recovery option is re-running from the beginning at full cost. The teams that get this right don't pick one or the other. They treat orchestration as a first-class state machine with explicit transitions and recovery points at every state boundary.

## Forces

- **Graph sprawl is real.** LangGraph's graph API looks clean until your workflow has five steps, two decision points, and one parallel branch — then you're drawing node-edge diagrams just to understand your own code. The framework that helps you express complexity also makes complexity the path of least resistance.
- **Loops can't recover.** A while loop with `max_retries` is the most common "orchestration" pattern, and it works until a pod restarts at iteration twelve, or a human needs to approve a decision mid-loop. At that point, you have no state to resume from — only a log file and a fresh invoice.
- **Anthropic says "just use the API."** The strongest counterpoint to every orchestration framework is Anthropic's December 2024 guidance: "We suggest that developers start by using LLM APIs directly. Many patterns can be implemented in a few lines of code." This is correct for simple cases and dangerously wrong for complex ones — the trick is knowing which case you're in.
- **Multi-agent is oversold.** The community migrated hard from "one agent does everything" to "multi-agent teams" — but >80% of production use cases don't need multiple agents. The supervisor + specialists pattern is the exception, not the rule.
- **State is where production breaks.** The persistence layer decision — Redis vs. Postgres vs. MemorySaver — is the single most-missed architectural choice. Teams ship on MemorySaver in staging, lose state on every pod restart in production, then scramble to retrofit a checkpointer while the event loop blocks.

## The move

**Start with direct API calls. Graduate to LangGraph when you need branching, resumability, or human-in-the-loop. Never skip the checkpointer.**

### The pragmatic graduation ladder

1. **Single LLM call + tools dict.** If your workflow is "call the model once, maybe twice" — do not reach for LangGraph. A `while` loop with a tool registry dict, 60 lines of Python, and no framework dependencies is the right answer. This covers the majority of agentic tasks.
2. **LangGraph when complexity demands it.** Graduate when you have two or more of: branching on conditional output, parallel execution branches, need for crash-safe resume, need for human-in-the-loop approval mid-run, or >10 tool calls per session.
3. **Typed state from day one.** Define a `TypedDict` state schema with explicit reducers, not a list of messages. This makes the graph debuggable and the checkpoint meaningful.
4. **Checkpoint before production, not after.** MemorySaver for local dev — fine. Production: Redis for latency-sensitive workflows, PostgreSQL for durability and replay. The checkpointer is not optional scaffolding; it is the recovery mechanism for every failure mode your loop can't handle.
5. **Keep multi-agent minimal.** One supervisor that routes to specialists covers most coordination needs. If you find yourself drawing arrows between agents, you're probably over-architecting. The supervisor pattern (LangGraph, Mastra, CrewAI hierarchical) is the one that ships; the agent-mesh is the one that loops.
6. **Treat the graph as a state machine, not a chat transcript.** Nodes are functions or LLM calls. Edges are conditional transitions. If your edge logic depends on reading the last message in a message list, you're writing a chat-bot inside a state machine — and it will behave like both at their worst.

## Evidence

- **Anthropic Engineering Blog:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." — recommends starting with direct API, using agents only for "long-running processes where the model must repeatedly decide between multiple tool calls in unpredictable sequences." — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **r/LocalLLaMA, Feb 2026:** "Switched our 4-agent research crew from CrewAI to LangGraph after the checkpoint + parallel branch features landed — 2x throughput, easier to debug." — benchmark cited: LangGraph's state-primitive checkpointing avoided 18% of redundant LLM calls. — [https://www.holysheep.ai/articles/en-langgraph-vs-crewai-2026-shengchanhuanjing-benchma-2026-07-05-0043.html](https://www.holysheep.ai/articles/en-langgraph-vs-crewai-2026-shengchanhuanjing-benchma-2026-07-05-0043.html)
- **MMC Ventures, Nov 2025:** Surveying 30+ agentic AI startup founders and 40+ enterprise practitioners — "60%+ of teams build homegrown orchestration stacks" due to framework limitations. LangChain and AutoGPT cited as "brittle, looping, unable to handle messy data." Key shift: "customers want services, not tools." — [https://mmc.vc/research/state-of-agentic-ai-founders-edition/](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)
- **LangChain survey, 4,200 teams, 2026:** LangGraph ranked #1 for production readiness (4.6/5), CrewAI ranked #1 for onboarding speed (4.3/5). Migration pattern: CrewAI → LangGraph driven by checkpointing needs, not performance benchmarks. — [https://www.langchain.com/resources/ai-agent-frameworks](https://www.langchain.com/resources/ai-agent-frameworks)
- **Hacker News, 44301809:** "We suggest that developers start by using LLM APIs directly. Many patterns can be implemented in a few lines of code." — Anthropic's position gets 543 HN points. Top comment: "It's insane that people use whole frameworks to send what is essentially an array of strings to a webservice." — [https://news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **Mastra (Show HN, Feb 2025):** Built on XState with OpenTelemetry tracing, `.step()/.then()/.after()` API for explicit branching and parallel merge. 154 HN comments on the JS-first alternative to LangGraph. — [https://news.ycombinator.com/item?id=43103073](https://news.ycombinator.com/item?id=43103073)

## Gotchas

- **Using MemorySaver in production.** It is the default checkpointer. It works in dev. It loses every in-flight thread on any service restart. Choose Redis or Postgres before you write your first production test.
- **Building a multi-agent system when a single agent with better tools suffices.** The supervisor + specialists pattern is the production pattern — not a peer-to-peer agent mesh. If you can't describe the routing logic in two sentences, you've over-scoped the agent count.
- **Storing everything in state.** Large artifacts (retrieved documents, tool outputs, intermediate results) should live in an external store — S3, Postgres blob, Redis — not in the state dictionary. Putting 500KB of RAG results into graph state adds serialization overhead on every transition and blocks the event loop on checkpoint writes.
- **Reaching for LangGraph before validating the simpler path.** The direct API + while loop approach is genuinely correct for 60-70% of agentic tasks. The framework tax — learning the graph API, setting up checkpointing, managing state serialization — is only worth it when the workflow complexity justifies it. If you can't list the states and transitions on a single index card, use the loop.
- **Silent state loss on long-running workflows.** Without checkpointing, a 2-hour workflow that fails at step 47 has no recovery point. With a checkpointer, you resume from the last successful step. This is not an optimization — it is the difference between a resilient system and a budget-burning retry loop.
