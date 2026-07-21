# Agent Memory Architecture Research - 2026-07-21

Research into how real-world AI agents handle memory and state persistence across sessions.
Primary sources: HN, Reddit, GitHub READMEs, arXiv papers, engineering/blog posts, 2024-2026.

---

## 1. THE CORE PROBLEM

LLMs are stateless by default. Each API request is processed independently with no knowledge carried forward.

> "Context windows reset with each API request. Memory systems provide long-term recall across sessions, maintaining persistent identity and learned behaviors that context windows cannot preserve."
> - Redis: AI agent memory: Building stateful AI systems (2026-02-03)
>   https://redis.io/blog/ai-agent-memory-stateful-systems/

> "A reasoning loop only survives one request unless its state is stored outside the worker. Without agent memory, the agent cannot resume a paused plan, recover after a crash, or recall a preference from an earlier session."
> - Edge of Context: AI Agent Memory Architecture in 2026
>   https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture

The industry has converged on a **two-tier architecture**: thread-scoped checkpointing for conversation continuity and semantic memory for cross-session knowledge.

> "What your agent remembers is fundamentally determined by what exists in its context window at any given moment. Think of the context window as the agent working memory. Designing an agent memory is essentially context engineering - determining which tokens enter the context window and how they organized."
> - Letta: Agent Memory: How to Build Agents That Learn and Remember (2025-07-07)
>   https://www.letta.com/blog/agent-memory



## 2. MEMORY TAXONOMY

The field uses a layered taxonomy that maps cognitive science onto engineering:

| Type                      | Scope          | Lifetime       | Human Parallel            | Storage Pattern        |
|---------------------------|----------------|---------------|--------------------------|------------------------|
| **Working**               | Single turn    | Milliseconds  | Active thought           | In-memory variables    |
| **Short-term**            | Single session | Minutes-hours | Current conversation     | In-memory / Redis      |
| **Long-term: Episodic**   | Cross-session  | Days-permanent| "I remember that event"  | Vector DB             |
| **Long-term: Semantic**   | Cross-session  | Days-permanent| "I know that fact"        | Key-value / Graph      |
| **Long-term: Procedural** | Cross-session  | Days-permanent| "I know how to do that"   | Code / Config          |

Source: Lets Data Science: AI Agent Memory Architecture (2026-03-03)
https://letsdatascience.com/blog/ai-agent-memory-architecture

### Three-Tier Operational Model (Production View)

| Tier               | Purpose                              | Storage                              | Lifetime       |
|--------------------|--------------------------------------|--------------------------------------|---------------|
| **Hot Memory**      | Current session state for pause/resume | Checkpoint store (PostgreSQL/Redis)   | Minutes-hours |
| **Cold Memory**     | Cross-session facts and preferences   | Vector store or KV store              | Days-permanent|
| **Document Memory** | Project knowledge, conventions        | Files (Markdown/JSON)                 | Days-permanent|

Source: Edge of Context: AI Agent Memory Architecture in 2026
https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture

---

## 3. MEMORY ARCHITECTURES IN PRODUCTION


### 3.1 MemGPT / Letta - OS-Inspired Tiered Memory

**Paper:** arXiv:2310.08560 - Packer et al., UC Berkeley

> "To enable using context beyond limited context windows, we propose virtual context management, a technique drawing inspiration from hierarchical memory systems in traditional operating systems which provide the illusion of an extended virtual memory via paging between physical memory and disk."
> - MemGPT paper abstract

**Core memory functions the agent calls:**

```python
core_memory_replace(block_name="persona", new_content="...")
core_memory_append(block_name="human", content="User prefers Python")
archival_search(query="user preferences")
archival_insert(content="...")
```

**Letta (the platform):** PostgreSQL by default, evolved from MemGPT (2024):
> "Letta is designed to be used with a PostgreSQL database."
> - letta-local GitHub README

> "Letta Code is built around long-lived agents that persist across sessions. Letta Code is the #1 model-agnostic OSS harness on TerminalBench."
> - Letta: Agent Memory

> "Requires a heartbeat mechanism and inner-monologue logic that adds coordination overhead to every turn."
> - agent_memory_techniques README

---

### 3.2 Mem0 - Pluggable Memory Layer

**Paper:** arXiv:2504.19413 (2025) - Chhikara et al., Mem0.ai

> "The three-tier design (vector memory, graph memory, history) with the integer ID mapping trick and the ADD/UPDATE/DELETE/NONE dedup pipeline is really elegant."
> - Community reimplementation in Rust, GitHub Discussion #4743 (2026-04-08)

**Benchmark results (LOCOMO benchmark):**
- 26% relative improvement over OpenAI on LLM-as-a-Judge metric
- 91% lower p95 latency than full-context approaches
- 90%+ token cost savings vs full-context

**Comparison with Letta:**

| Aspect            | Mem0              | Letta (MemGPT)                          |
|-------------------|-------------------|-----------------------------------------|
| GitHub Stars      | ~48K              | ~21K                                    |
| Memory approach   | Passive extraction + semantic search | Agent self-edits tiered memory blocks |
| Integration model | Library - drop into any stack | Platform - agent lives inside Letta |

Source: Vectorize.io: Mem0 vs Letta (2026)

**Mem0 quick-start code:**

```python
from mem0 import Memory
client = Memory()
client.add("User prefers concise responses", user_id="alice")
results = client.search("What does the user like?", user_id="alice")
history = client.get_history(user_id="alice")
```

**Supported vector stores (21):** pgvector, ChromaDB, Pinecone, Qdrant, Weaviate, Milvus, Redis, Neo4j, FAISS, and more.

---

### 3.3 Zep / Graphiti - Temporal Knowledge Graph

**Paper:** arXiv:2501.13956 (2025) - Rasmussen et al., Zep AI

**Key differentiator:** Temporal awareness - the graph tracks when facts became true and when superseded. Prior versions remain queryable.

**Performance results:**

| Benchmark                | Zep Score   | Baseline         | Improvement        |
|-------------------------|-------------|------------------|-------------------|
| DMR (Deep Memory Retrieval) | 94.8%   | MemGPT: 93.4%   | +1.4%             |
| LongMemEval (gpt-4o)   | 71.2%       | Full-context: 60.2% | +18.5%        |
| LongMemEval latency    | 2.58s       | 28.9s            | -91%              |
| Avg context tokens      | 1.6k        | 115k             | -99%              |

> "Zep reduces context from ~115k tokens to ~1.6k tokens while improving accuracy and achieving ~90% latency reduction."
> - Zep paper (arXiv:2501.13956)

**Graphiti** (github.com/getzep/graphiti, 28.9K stars):
> "Graphiti is an open-source framework for building and querying temporal context graphs for AI agents. Unlike static knowledge graphs, Graphiti tracks how facts change over time, maintains provenance to source data."
> - Graphiti GitHub README

**Graphiti code example:**

```python
from graphiti import Graphiti
graphiti = Graphiti("bolt://localhost:7687", "neo4j", "password")
await graphiti.add_episode(source="user", body="I started at Google last month.", episode_time=datetime.now())
results = await graphiti.search(query="What is the user current job?", time_aware=True)
```

---

### 3.4 LangGraph State Persistence

> "A graph without a checkpointer is stateless. Each call to invoke() runs from the beginning with no memory of previous interactions."
> - Crewship: LangGraph.js Memory and Persistence

> "On every super-step, it writes a checkpoint containing: Channel values (state dict), Channel versions, Metadata, Pending writes from interrupted nodes."
> - TeachYou Academy: LangGraph Persistence Backends Compared (2026-06-18)

**Checkpointers by backend:**

| Backend     | Package                        | Use Case                        |
|-------------|--------------------------------|---------------------------------|
| MemorySaver | langgraph.checkpoint.memory    | Development / single instance   |
| SQLite      | langgraph.checkpoint.sqlite   | Single-server production        |
| PostgreSQL  | langgraph-checkpoint-postgres  | Horizontal scaling              |
| Redis       | langgraph-checkpoint-redis     | High-performance / distributed  |

Source: LangGraph.js Persistence Guide (https://langgraphjs.guide/persistence)

**Redis integration:**
> "langgraph-checkpoint-redis brings Redis powerful memory capabilities to LangGraph."
> - Redis: LangGraph & Redis (2025-03-28)

**LangGraph.js PostgreSQL checkpointer:**

```typescript
import { PostgresSaver } from "@langchain/langgraph-checkpoint-postgres";
const checkpointer = new PostgresSaver({ connectionDetails: { type: "postgres", connectionConfig: { database: "langgraph", host: "localhost", port: 5432, user: "user", password: "pass" } } });
const app = createReactAgent({ llm, tools, checkpointer });
const result = await app.invoke({ messages: [] }, { configurable: { thread_id: "user-123-session-456" } });
// Source: langchain-ai/langgraphjs/libs/checkpoint-postgres/README
```

**Key features enabled by checkpointing:** Conversation memory, human-in-the-loop (interrupt()/resume), fault tolerance, time travel.

---

### 3.5 CrewAI Memory

> "CrewAI supports short-term memory (conversation context within a crew execution), long-term memory (persistent across executions), and entity memory (structured facts about recurring entities)."
> - ActiveWizards: CrewAI Memory in Production (2025)

> "CrewAI agents live entirely in RAM. When your process ends, everything dies with it."
> - BotWire: Persistent Memory for CrewAI Agents

> "User corrects agent 3x the same way -> confidence 0.8 (likely real preference). User later does the opposite -> confidence drops, old preference archived. This prevents agents from over-fitting to one-off user actions."
> - crewAIInc/crewAI#6050

**CrewAI Memory API:**

```python
from crewai import Memory, Crew
memory = Memory()
memory.remember("We decided to use PostgreSQL for the user database")
matches = memory.recall("What are our API limits?", limit=5)
facts = memory.extract_memories("Meeting notes: Migrate from MySQL to PostgreSQL next quarter.")
crew = Crew(agents=[...], tasks=[...], memory=True, verbose=True)
# Source: docs.crewai.com/en/concepts/memory
```

---

### 3.6 Neo4j Agent Memory (by Neo4j Labs)

**Repository:** neo4j.com/labs/agent-memory | Python + TypeScript SDKs

> "Production-grade memory for single- and multi-agent systems. Three memory layers - conversations, entities, reasoning - in one graph. Available as a hosted service (zero infra) or run against your own Neo4j."
> - Neo4j Labs: Agent Memory

**Architecture: 1 graph, 3 memory tiers, POLE+O ontology:**

| Layer             | Purpose                                      |
|-------------------|----------------------------------------------|
| **Conversations**  | Full dialogue history                        |
| **Entities**      | Structured facts about people, objects       |
| **Reasoning**     | Derived knowledge, chains of inference        |

**Installation:**
```bash
pip install neo4j-agent-memory
export MEMORY_API_KEY=***  # hosted, or NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD for self-hosted
```

---

## 4. SESSION VS. PERSISTENT MEMORY

**Session memory** = state that persists within a single conversation/session (minutes to hours).
Implemented via checkpointers, in-memory state, or Redis.

**Persistent memory** = state that survives across sessions, days, and system restarts.
Implemented via PostgreSQL, vector stores, graph databases, or file systems.

> "A dict works until it does not. SQLite is better until you need semantic search. Most implementations default to episodic-only, which becomes noisy as the store fills with low-signal exchanges."
> - Kronvex: AI Agent Memory in Python (2026-03-22)

> "Start with the failure you need to fix, then choose the store. Do not put exact facts in a fuzzy retrieval system or treat a checkpoint as an audit log."
> - Edge of Context

---

## 5. PRODUCTION STACKS OBSERVED

### Stack 1: Redis + PostgreSQL + Vector DB
- Hot: Redis (session state, checkpoints)
- Warm: PostgreSQL (LangGraph checkpointer, structured data)
- Cold: Qdrant / pgvector / ChromaDB (semantic memory)

> "Redis Streams + Qdrant with TTL-based expiry" for episodic memory.
> - Inductivee: AI Agent Memory Architecture

### Stack 2: Full PostgreSQL
- All layers: PostgreSQL (pgvector for vectors, AGE for graphs)
- See: BAEM1N.DEV: Full AI Agent Stack on One PostgreSQL

### Stack 3: Neo4j-Centric
- Graph store: Neo4j (via Graphiti or neo4j-agent-memory)
- Session: Redis
- Vectors: Neo4j native (or Pinecone/Qdrant)

### Stack 4: Letta (Monolithic)
- Runtime: Letta server
- Storage: PostgreSQL (default)
- Memory: MemGPT tiered architecture

---

## 6. BENCHMARKS AND EVALUATION

Three benchmarks define the measurement landscape (as of 2026):

**LOCOMO** - 1,540 questions across four categories (single-hop, multi-hop, temporal, general)
**LongMemEval** - Tests retrieval accuracy and latency at scale
**BEAM** - Benchmark for Episodic Agent Memory

| System | Benchmark     | Score    | Key Result                              |
|--------|--------------|----------|---------------------------------------- |
| Mem0   | LOCOMO       | 92.5     | 26% relative improvement over OpenAI   |
| Mem0   | LOCOMO       | -        | 91% lower p95 latency vs full-context  |
| Zep    | DMR          | 94.8%    | +1.4% vs MemGPT (93.4%)               |
| Zep    | LongMemEval  | 71.2%    | +18.5% vs full-context (60.2%)         |
| Zep    | LongMemEval  | 2.58s    | -91% latency vs 28.9s                  |

Sources: Mem0 paper (arXiv:2504.19413), Zep paper (arXiv:2501.13956)

---

## 7. CONSUMER AI PERSISTENT MEMORY (2026)

| Provider  | Feature                                    | Date                  |
|-----------|-------------------------------------------|-----------------------|
| OpenAI    | ChatGPT Memory (persistent fact storage)    | 2024+                 |
| Anthropic | Claude Chat Memory (project-level)          | 2026-03-02            |
| Anthropic | "Dreaming" (async hippocampal consolidation) | 2026-05-06          |
| Google    | Memory Bank                                | I/O 2026 (2026-05-19)|

> "ChatGPT Memory works so well that the platform now surfaces reminders, tailors tone, and references past events. The average ChatGPT Plus user accumulates 40-80 stored memory entries in 30 days."
> - LumiChats testing (2026-04)

> "Anthropic: Claude now remembers your past conversations, so you can seamlessly continue projects, reference previous discussions, and build on your ideas without starting from scratch every time."
> - WinBuzzer (2025-09-12)

---

## 8. OPEN PROBLEMS AND HARD LIMITATIONS

From Mem0: State of AI Agent Memory 2026 and SSGM (arXiv:2603.11768):

1. **Cross-session identity resolution:** The memory model assumes a stable user_id. Anonymous sessions, multi-device users, and mixed auth flows break that assumption.

2. **Memory staleness:** A highly-retrieved memory about a user employer is accurate until they change jobs, at which point it becomes confidently wrong. Decay handles low-relevance memories. Staleness in high-relevance memories is an open problem.

3. **Semantic drift:** Repeated summarization during memory consolidation gradually distorts facts over time. (SSGM paper)

4. **Memory poisoning:** Malicious content internalized as valid knowledge during ingestion. (SSGM paper)

5. **Regulatory compliance:** Who can inspect stored memories? How long retained? How does a user delete them? Application-layer decisions today - regulatory expectations will tighten.

---

## 9. SOURCE INDEX

### Papers
- MemGPT: Packer et al. - arXiv:2310.08560 | https://sky.cs.berkeley.edu/project/memgpt/
- Mem0: Chhikara et al. - arXiv:2504.19413 | https://arxiv.org/html/2504.19413v1
- Zep: Rasmussen et al. - arXiv:2501.13956 | https://arxiv.org/html/2501.13956v1
- SSGM: Lam et al. - arXiv:2603.11768 (memory integrity/safety) | https://arxiv.org/abs/2603.11768

### Frameworks and SDKs
- Letta: https://www.letta.com | https://github.com/letta-ai/letta (formerly MemGPT)
- Mem0: https://mem0.ai | https://github.com/mem0ai/mem0 (~48K stars)
- Graphiti: https://github.com/getzep/graphiti (~28.9K stars)
- Neo4j Agent Memory: https://neo4j.com/labs/agent-memory
- LangGraph: https://github.com/langchain-ai/langgraph
- LangGraph + Redis: https://github.com/redis-developer/langgraph-redis
- LangGraph Checkpointers: https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres
- LangGraph JS Checkpointers: https://github.com/langchain-ai/langgraphjs/tree/main/libs/checkpoint-postgres
- CrewAI Memory: https://docs.crewai.com/en/concepts/memory

### Engineering Blog Posts
1. Redis: AI agent memory - https://redis.io/blog/ai-agent-memory-stateful-systems/ (2026-02-03)
2. Redis: LangGraph & Redis - https://redis.io/blog/langgraph-redis-build-smarter-ai-agents-with-memory-persistence/ (2025-03-28)
3. Edge of Context: AI Agent Memory Architecture in 2026 - https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture (2026-02-14)
4. Inductivee: AI Agent Memory Architecture - https://inductivee.com/blog/ai-agent-memory-persistence-architecture (2025-10-27)
5. Lets Data Science: AI Agent Memory Architecture - https://letsdatascience.com/blog/ai-agent-memory-architecture (2026-03-03)
6. Digital Applied: AI Agent Memory 2026 - https://www.digitalapplied.com/blog/ai-agent-memory-vector-graph-episodic-2026 (2026-05-24)
7. Mem0: State of AI Agent Memory 2026 - https://mem0.ai/blog/state-of-ai-agent-memory-2026
8. Neo4j: Graphiti - https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory (2025-03-24)
9. Kronvex: AI Agent Memory in Python - https://kronvex.io/blog-ai-agent-memory-python (2026-03-22)
10. TeachYou Academy: LangGraph Persistence Backends Compared - https://www.teachyou.ai/blog/langgraph-persistence-backends-compared (2026-06-18)
11. Vectorize.io: Mem0 vs Letta - https://vectorize.io/articles/mem0-vs-letta (2026)
12. AI Magicx: AI Agent Memory Systems - https://www.aimagicx.com/blog/ai-agent-memory-systems-persistent-brain-2026 (2026-03-18)
13. QubitTool: AI Agent Memory Persistence Architecture - https://qubittool.com/blog/ai-agent-memory-persistence-architecture (2026-05-21)
14. Letta: Agent Memory - https://www.letta.com/blog/agent-memory (2025-07-07)
15. Leonie Monigatti: MemGPT paper review - https://www.leoniemonigatti.com/papers/memgpt.html (2025-10-17)

### HN Posts / Show HNs
1. AgentKeeper - cognitive persistence layer - https://news.ycombinator.com/item?id=47217244
2. Mumpix - persistent memory for AI agents - https://news.ycombinator.com/item?id=47266438
3. Mnemory - persistent memory for AI agents - https://news.ycombinator.com/item?id=47995527
4. Drift AI - coding sessions persistent across agents - https://news.ycombinator.com/item?id=47934325

### Community Discussions
1. Reddit r/LocalLLaMA: Agent Memory - https://old.reddit.com/r/LocalLLaMA/comments/1gvhpjj/agent_memory/
2. Reddit r/LangChain: Benchmarked memories - https://www.reddit.com/r/LangChain/comments/1kash7b/i_benchmarked_openai_memory_vs_langmem_vs_letta/
3. GitHub: R-Mem (Rust reimplementation of Mem0) - https://github.com/mem0ai/mem0/discussions/4743 (2026-04-08)
4. GitHub: crewAI#6050 Cross-session memory - https://github.com/crewAIInc/crewAI/issues/6050