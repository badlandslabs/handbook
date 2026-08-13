# S-2556 · The Three-Tier Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent aced the demo. In production, it has no idea who the user is, what they discussed last week, or why they rejected the previous proposal. Every session starts with a cold context — the LLM is brilliant but amnesiac. Users resent repeating themselves. The agent makes the same mistakes it made three conversations ago. Meanwhile, you are feeding it entire conversation histories as context, burning through tokens at $15 per 1M-token call before you even hit the model's limit.

This is the memory architecture problem — and the three-tier episodic/semantic/procedural model has become the production standard for solving it.

## Forces

- **Context windows are attention, not memory.** Every token in context competes for processing bandwidth. Models begin deprioritizing critical information at roughly 60% context capacity, long before any hard token limit is reached. Production agents hit practical overflow within 15–20 conversation turns.
- **Stateless inference is expensive when you make it stateful.** Feeding full conversation histories into the context window to simulate memory is financially untenable at scale — one million-token call costs ~$15.
- **Episodes, facts, and skills are fundamentally different data types.** A conversation transcript, a user's name, and a learned tool-calling procedure require completely different storage, retrieval, and eviction strategies. Treating them all as "text in context" destroys efficiency on all three.
- **Forgetting is not failure.** An agent that remembers everything will accumulate irrelevant context and degrade. Memory architectures need eviction, decay, and summarization — not just storage.

## The Move

Implement a **three-tier memory architecture** modeled on cognitive science, separating storage into layers with distinct retrieval and eviction policies.

**Tier 1 — Episodic memory (what happened):** Stores specific events, conversations, and interactions tagged with time, participants, and outcome. Implemented as a searchable event log. Retrieval is by recency + semantic similarity. Eviction uses summarization — old episodes get compressed rather than deleted.

**Tier 2 — Semantic memory (what is true):** Stores extracted facts, preferences, and knowledge — the "what" that survives individual interactions. Implemented as a knowledge graph (entities + relationships) or vector store. Retrieval is by query. The LLM itself decides what to promote from episodic to semantic during reflection.

**Tier 3 — Procedural memory (how to act):** Stores learned behaviors, tool-calling sequences, and refined prompts — the "how" the agent has internalized. Often implemented as curated prompt templates or learned tool chains. Eviction is manual or triggered by sustained failure rates.

**The key discipline:** The architecture knows the difference between what to keep in working context, what to store long-term, and what to encode as reusable behavior. An LLM-managed interface decides what to promote between tiers. No tier stores everything by default.

## Evidence

- **arXiv (Software Engineering, Feb 2026):** "From Prompt–Response to Goal-Directed Systems: The Evolution of Agentic AI Software Architecture" proposes a reference architecture separating cognitive reasoning from execution, with explicit memory layers as a structural requirement — not a feature. Critically notes that "agency arises from clean separation of cognition from execution, state management, and policy enforcement." — [arXiv:2602.10479v1](https://arxiv.org/html/2602.10479v1)

- **Red Hat Emerging Technologies Blog (Jun 2026):** "From Context to Dreams: Architecting Memory for AI Agents" introduces the capability formula: **Agent capability = model + harness + memory + environment + evolution**. Demonstrates that an average model with better harness and memory outperforms a larger model without them. Identifies the "goldfish problem" — LLMs forget everything across sessions without explicit memory architecture. — [next.redhat.com/2026/06/01/from-context-to-dreams-architecting-memory-for-ai-agents](https://next.redhat.com/2026/06/01/from-context-to-dreams-architecting-memory-for-ai-agents)

- **GitHub: Zijian-Ni/agent-memory (open source, MIT):** Implements the three-tier model in production-ready Python with SQLite + FTS5 storage, Ebbinghaus forgetting curve simulation for episodic decay, graph relationships between memories (caused_by, supports, contradicts), and hybrid retrieval scoring (relevance × recency × importance). Framework-agnostic — works with OpenAI, LangChain, or raw Python. — [github.com/Zijian-Ni/agent-memory](https://github.com/Zijian-Ni/agent-memory)

## Gotchas

- **Do not conflate context window with memory.** Context is working attention — finite and expensive. Memory is persistent storage with retrieval. Feeding conversation logs into the prompt to simulate memory is the antipattern this stack corrects.
- **Episodic overflow is silent.** Without explicit summarization or eviction, episodic memory grows unbounded. After 100 conversations, retrieval latency and relevance both degrade. Schedule periodic consolidation, not just on-demand retrieval.
- **The LLM is both the consumer and the curator of its own memory.** This creates a bootstrapping problem — the same model that retrieves memories also decides what to store and what to forget. Validate that the curation logic is sound independently from the retrieval logic.
