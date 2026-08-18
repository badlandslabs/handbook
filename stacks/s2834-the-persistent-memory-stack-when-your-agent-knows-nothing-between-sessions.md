# S-2834 · The Persistent Memory Stack — When Your Agent Knows Nothing Between Sessions

Your agent works perfectly for 20 minutes — analyzing data, making decisions, executing tasks. Then it crashes, redeploys, or the user returns after the weekend. It starts from zero. No memory of what it was doing. No knowledge of preferences established in the last session. No continuity. This is the persistent memory problem: LLMs are stateless between calls, and everything that looks like memory is something you engineered on top of it.

## Forces

- **Context window vs. persistent storage:** The context window is attention, not storage — it resets between calls and has hard limits. You can't stuff your entire history in it.
- **Cost vs. recall fidelity:** Summarization is cheap but loses nuance. Full recall is accurate but expensive at scale. Most teams pick a midpoint and accept the loss.
- **Write complexity vs. read reliability:** Building a memory write pipeline (what to store, when, how to structure it) is harder than the read pipeline, but a sloppy write makes reads worthless.
- **Agent autonomy vs. memory corruption:** Letting the agent write its own memory summaries is powerful but risks the agent encoding its own mistakes as facts.
- **Multi-agent memory:** When multiple agents share a task, memory must be consistent across agents without becoming a coordination bottleneck.

## The move

Build a layered memory architecture that separates concerns by temporal scope and retrieval cost:

- **Layer 1 — Working memory (context window):** The active conversation. Fast, expressive, zero persistence. This is what the model sees during a single call.
- **Layer 2 — Episodic memory:** What happened and when. Store conversation summaries, key decisions, task milestones. Human-readable. Queryable by timestamp and topic.
- **Layer 3 — Semantic memory:** What's true. User preferences, facts, learned patterns. Structured key-value records, not raw text.
- **Layer 4 — Procedural memory:** How to do things. Agent instructions, system prompts, tool definitions. Version-controlled.

### Memory write strategy

- **Write-through on key events:** Don't wait for a session end. Store a memory entry on explicit user signals ("remind me to..."), confirmed decisions ("subscribed to plan X"), and task milestones. This is more reliable than end-of-session summarization.
- **LLM-assisted extraction:** Use a lightweight model or a structured prompt to extract facts from each message turn and write them to semantic memory. The MemGPT/Letta approach gives the agent explicit memory write tools it calls itself.
- **Conflict resolution on read, not write:** When retrieving conflicting facts (e.g., "meeting Friday" vs "meeting moved to Thursday"), reconcile by timestamp — the most recent entry wins — before the retrieved context reaches the generating model.
- **Periodic summarization:** For long conversations, compress episodic memory into dense summaries at configurable token thresholds (e.g., every 8,000 tokens). Store both the summary and the original for auditability.
- **Git-based versioning for code agents:** Letta's Context Repositories (2026) stores agent memory as a local filesystem backed by git. Each memory edit is a commit with an informative message. Multiple subagents can work on the same memory via git worktrees. The history is queryable with standard git diffs — the agent can see what it knew two sessions ago.
- **Local-first for privacy-sensitive use cases:** OpenMemory (CaviraOSS, Apache 2.0, ~4.4k GitHub stars as of 2025) stores memory in a local SQLite file. No cloud dependency, no data leaves the machine. Uses a Hierarchical Memory Decomposition architecture with multi-sector embeddings and single-waypoint graph linking.

### Memory read strategy

- **Inject at session start:** Load relevant semantic memory into the system prompt before the first turn. This is the most reliable pattern — the agent starts with context rather than building it.
- **RAG over semantic memory:** Embed episodic summaries and semantic records. Retrieve top-k relevant entries based on the current query. This scales better than flooding the context with everything.
- **Progressive disclosure:** Don't inject everything upfront. Let the agent request relevant memories as needed, similar to how a human refers to notes. OpenMemory supports this via its HSG (Hierarchical Search Graph) engine.

## Evidence

- **Research paper:** *Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers* (arXiv:2603.07670v1, March 2026) formalizes agent memory as a **write–manage–read loop** and introduces a three-dimensional taxonomy spanning temporal scope, representational substrate, and control policy. The paper identifies four core mechanisms: context-resident memory and compression, retrieval-augmented memory, self-reflective memory (agent-initiated writes), and learned memory policies.
- **Company engineering post:** Kaizen Software Systems (2026) describes the four-layer taxonomy and frames the core problem: "The model itself — the LLM at the core of any agent — remembers nothing between calls. Everything that feels like 'memory' in a production agent is something you engineered on top of it." They document failure modes including summarization drift (the summary diverges from the original), overwrite races (concurrent writes lose data), and the "confident amnesia" pattern (the agent doesn't know it forgot something).
- **Open-source framework:** Letta (formerly MemGPT, UC Berkeley origins) released **Context Repositories** in February 2026 — a rebuild of memory for coding agents using git-based versioning. Agents clone their context repository locally, edit memory files with standard terminal commands, and every change is auto-committed with an LLM-generated commit message. Enables multi-agent memory via git worktrees. Source: [letta.com/blog/context-repositories](https://www.letta.com/blog/context-repositories)
- **Open-source project:** OpenMemory (CaviraOSS, Apache 2.0) implements **Hierarchical Memory Decomposition (HMD) v2** with a multi-sector embedding pipeline, decay/reinforcement mechanics for memory importance, and local-first SQLite storage. HN discussion (48 points, December 2025) noted the local-first pitch split commenters — fans praised offline operation and privacy; skeptics asked for comparisons against Redis and existing solutions. Source: [github.com/CaviraOSS/OpenMemory](https://github.com/CaviraOSS/OpenMemory)
- **Framework:** Mem0 (mem0.ai, 62k+ GitHub stars) published engineering guidance (May 2026) framing context window and persistent memory as complementary layers: "A large context window handles within-session coherence. Persistent memory handles everything else: continuity across sessions, cost control at scale, and reliable retrieval of the facts that actually matter." Source: [mem0.ai/blog](https://mem0.ai/blog/context-window-vs-persistent-memory-why-1m-tokens-isn-t-enough)

## Gotchas

- **Context window management is not memory management.** Context compression (summarizing the conversation to fit a window) solves the immediate problem but doesn't produce durable memory. After compression, the original history is gone and can't be retrieved.
- **The agent doesn't know what it forgot.** This is the most dangerous failure mode. The agent confidently proceeds with a degraded context, unaware that key facts were lost. Solution: give the agent a memory "sanity check" tool that explicitly queries the memory store and reports what it found.
- **Naive RAG on memory returns stale facts.** A fact retrieved from semantic memory may be outdated. Always resolve retrieved facts by timestamp before using them. The model will often just use the first retrieved chunk.
- **Concurrent writes cause silent data loss.** If multiple agents or concurrent threads write to the same memory store without a locking strategy, writes get lost. Use optimistic locking, event sourcing, or git-style merge conflict detection.
- **Memory grows unbounded without a decay mechanism.** Every session adds records. Without importance-based decay or archival, the retrieval pipeline degrades as the memory store fills with low-value entries. Mem0 and OpenMemory both implement reinforcement/decay cycles but require tuning.
