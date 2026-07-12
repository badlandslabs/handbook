# S-999 · The Orchestration and Memory Stack — When Your Agent Needs to Know What It Already Knew

You split one agent into three. Now none of them can remember why the first one made the decision it did. Context fragments across sessions. The agent works fine on day one; by day ten it's rediscovering the same facts it established last week. The orchestration graph is clean on paper. The memory layer is the problem.

This is two failure modes wearing one face: how you chain agents determines what state they need; how you store that state determines what chains are even possible. Most teams solve orchestration and treat memory as an afterthought — then spend months retrofitting persistence into an architecture that was never designed for it.

## Forces

- **Token budget exhaustion kills late steps.** Every LLM call in a chain consumes context tokens. Without deliberate memory management, later steps in a pipeline get degraded input — not clean outputs from previous steps, but a bloated context window full of intermediate noise. This is the most common reason orchestration graphs look right but perform wrong.
- **Defining task graphs yourself beats letting agents self-coordinate.** One HN practitioner's hard-won finding: agents picking their own subtasks leads to chaos. Define the task graph explicitly; let agents only handle leaf nodes. The orchestration supervisor decides routing; workers execute. Direct agent-to-agent negotiation adds a coordination cost that rarely pays off.
- **Memory is not one thing.** Context window (working memory), conversation history (episodic), structured facts (semantic), and learned procedures (procedural) are four distinct systems. Most teams build one and wonder why the others fail.
- **Scratchpad vs. vector store is a false dichotomy.** The right answer depends on retrieval latency tolerance, context window headroom, and whether the agent needs to navigate or just recall.

## The Move

### For Orchestration: Three Patterns, Not a Framework

Start with the Anthropic decision ladder: single LLM call → retrieval + in-context examples → prompt chaining → parallelization → routing → orchestrator-worker → evaluator-optimizer. Only add a rung when the current one demonstrably fails. Most production needs live at routing or orchestrator-worker. You rarely need the full evaluator-optimizer stack.

**Pick a coordination pattern by scale:**

| Pattern | When to use it | Failure mode |
|---|---|---|
| **Supervisor** | 2–5 agents, clear task boundaries, governance required | Single point of failure; supervisor becomes the bottleneck |
| **Orchestrator-Worker** | Complex multi-step tasks, dynamic sub-task decomposition | Task graph complexity grows fast; needs explicit definition |
| **Parallelization** | Homogeneous independent tasks (scraping N URLs, summarizing N docs) | Only works when tasks are actually independent; fanned results need a merge step |

**Key practical constraint from production practitioners (HN, 2025):** Build agent-to-agent data passing around structured JSON outputs in SQLite, not direct messaging. One team found that letting agents talk to each other directly was "a mess" and switched to a central coordinator that reads per-task JSON outputs and routes. The coordinator handles orchestration; agents handle execution only.

**Framework caveat from Anthropic:** "We suggest that developers start by using LLM APIs directly. Many patterns can be implemented in a few lines of code. If you use a framework, ensure you understand the underlying code. Incorrect assumptions about what's under the hood are a common source of customer error." The frameworks that survive scrutiny are LangGraph (state-machine DAGs), CrewAI (fast prototyping with role-based agents), and AGNO (lightweight, opinionated). Custom orchestration in production consistently beats framework defaults for non-trivial workloads.

### For Memory: Three Architecture Generations, Choose by Use Case

Emotion Machine documented three iterations of memory architecture, each a response to the predecessor's limits. The progression maps directly to the memory tier problem:

**V1: pgvector + importance scoring.** Store semantic embeddings in PostgreSQL with pgvector. Score facts by importance at write time. Retrieve by cosine similarity. This works for large memory stores where selective retrieval is the goal — but naive vector search returns temporally stale results first (recent memories rank low on similarity even when they're most relevant). It also requires managing an embedding pipeline.

**V2: LLM-managed scratchpad.** At session end, the LLM decides what matters and writes a structured summary into a persistent context file. On session start, inject the scratchpad. This is ChatGPT's memory approach. It wins on simplicity and retrieval latency (it's just text injection), and the LLM deciding what to remember scales better than having engineers impose structure upfront. The tradeoff: the model can miss things, and there's no audit trail of what was discarded.

**V3: Filesystem + hot_context.** The agent gets a working directory it can write to and read from via bash. Files become the memory. A separate `hot_context` mechanism surfaces relevant files into the active context window. This is the right model for agentic workflows requiring sandboxed execution — the agent can navigate and reason about its own memory like a developer navigating a codebase. The tradeoff: you need active context management to avoid filling the context window with irrelevant file reads.

**The tier model from AgentMarketCap (2026):** Working memory (context window) for active reasoning, episodic memory (conversation logs, task logs) for what happened before, and semantic memory (facts, preferences, entity knowledge) for what the agent knows about the world and the user. Cross-session identity — knowing that "the user moved from New York to San Francisco" means something and isn't just two unrelated city facts — remains an open problem across all three architectures.

**Practical production rule (Mem0, 2026):** 21 agent frameworks and 20 vector stores are now integrated into the memory ecosystem. The biggest gains in 2025–2026 came from temporal reasoning (+29.6 points on BEAM benchmark) and multi-hop retrieval (+23.1 points). Cross-session identity and temporal abstraction at scale are still genuinely unsolved. If your use case requires either, budget for custom work.

## Evidence

- **HN Ask: Multi-Agent AI Workflow Orchestration (2025):** Practitioners sharing production stacks — "LangGraph, built my own orchestrator on top. Agents run as parallel workers in their own git worktree. Agent-to-agent data flows through SQLite-structured JSON output per task, central coordinator reads and routes." Another: "There's absolute 0 framework out there that's good enough for serious work." — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **Anthropic Engineering Blog — "Building Effective AI Agents" (Dec 2024):** Canonical five-pattern framework (prompt chaining, parallelization, routing, orchestrator-worker, evaluator-optimizer). Key finding: "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Emotion Machine — "Three Memory Architectures for AI Companions" (2025):** First-person account of evolving from pgvector → scratchpad → filesystem. Key finding: "The memory problem in AI companions is the single hardest product problem in this space." Each architecture solves different problems; none replaces the others entirely. — [https://www.emotionmachine.com/blog/how-memory-works](https://www.emotionmachine.com/blog/how-memory-works)
- **AgentMarketCap — "Agent Memory in Production 2026" (Apr 2026):** Tier model (working/episodic/semantic), cross-session identity as open problem, Letta/Mem0/Zep/Hindsight benchmarked. Key finding: "Memory-layer architecture enables agents that run autonomously for weeks, accumulate user context, and displace headcount." — [https://agentmarketcap.ai/blog/2026/04/11/agent-memory-architecture-production-2026](https://agentmarketcap.ai/blog/2026/04/11/agent-memory-architecture-production-2026)
- **VDF AI Industry Intelligence — "State of AI Agent Orchestration 2025" (Jun 2026):** $5.4B market in 2024, 78% enterprise adoption, 45.8% CAGR through 2030. "Observability is the #1 barrier to production adoption." — [https://vdf.ai/ai-agent-orchestration-2025](https://vdf.ai/ai-agent-orchestration-2025)

## Gotchas

- **Don't build the task graph dynamically from the start.** Let the supervisor define task routing; let workers only handle leaf execution. When you let agents self-coordinate subtasks, coordination cost dominates execution cost and nothing ships on time.
- **Scratchpad summarization has a silent discard problem.** The LLM decides what to keep. Low-importance facts that later turn out to be critical get dropped silently. Mitigation: log the raw session alongside the summary so you can replay or re-extract.
- **Vector store memory requires temporal re-ranking.** Naive cosine similarity puts recent facts last when they're most relevant. Add a recency boost to retrieval scores, or use a hybrid BM25 + vector approach.
- **Orchestration complexity and memory complexity compound.** The more agents you have, the more you need structured inter-agent state. The more structured state you have, the more you need a schema. Design both layers together, not sequentially.
- **Framework abstraction hides failure modes.** LangChain, CrewAI, and AutoGen each make trade-offs that are invisible until you hit a production incident. If you're using a framework, read the source for the parts that matter: retry logic, token accounting, and context management.
