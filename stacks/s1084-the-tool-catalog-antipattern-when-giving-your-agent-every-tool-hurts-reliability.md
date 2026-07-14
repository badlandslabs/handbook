# S-1084 · The Tool Catalog Antipattern

When your agent freezes mid-task, loops endlessly, or calls the wrong API — the reflex is to blame the model. Usually it's not the model. It's the tool interface: too many tools, too little description, and no routing between what the agent needs and what it sees.

## Forces

- **Naive context inclusion degrades performance.** Passing all tool schemas to a model tanks accuracy. Semantic tool routing achieves 86.4% tool selection accuracy versus below 50% for naive all-tools-in-context at scale.
- **Every tool is an attack surface.** A code execution tool accessible from a document Q&A agent is unnecessary blast radius.
- **Tool descriptions set the model's world.** Models pay disproportionate attention to context boundaries — system instructions and task-relevant tools at the edges, filler in the middle.
- **Read vs. write tools have different retry semantics.** Retrying a write tool can create duplicates. Retrying a read tool is usually safe. A flat `try/except` over all tools ignores this distinction.
- **What you exclude matters as much as what you include.** Verbose tool schemas and irrelevant tools degrade the model's ability to focus on the actual task.

## The Move

**Tier your tool exposure and route dynamically, not statically.**

- **Layer 1 — Tool selection before tool call.** Use embedding-based semantic routing over tool descriptions to pre-filter the candidate set before the model sees schemas. This is the pattern that gets 86.4% accuracy on large tool catalogs.
- **Layer 2 — Per-call retry contracts, not global retry policy.** Read tools: retry up to 3× with exponential backoff. Write tools: idempotency key on first call, reject retry without confirmation of prior outcome. Connector tools (no confirmation returned): store call ID, check state before retry.
- **Layer 3 — Five-layer context assembly at inference time.** Statically ordered as: (1) system instructions, (2) retrieved knowledge (RAG, filtered), (3) persistent memory, (4) conversation history (compressed), (5) tool definitions. Keep the most relevant tools at the context boundaries — the model weights these highest.
- **Layer 4 — Semantic routing for large tool catalogs.** Beyond ~15 tools, embedding similarity search over tool metadata outperforms full-context approaches. For predictable tool chains, a graph-based approach that captures tool transition probabilities can predict the next tool without a full LLM call, cutting inference costs up to 30%.
- **Layer 5 — Tool failure taxonomy drives recovery, not error type.** The recovery path depends on consequence class: unknown side effect → halt and surface to human; partial success → query state before continuing; stale reconciliation → refresh and re-evaluate; duplicate risk → idempotency gate before retry.

## Evidence

- **Engineering Blog (Anthropic):** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Single LLM calls with retrieval and in-context examples outperform over-tooled agents for well-defined tasks. — [Anthropic Engineering: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Research Paper (AAAI 2026):** "AutoTool: Efficient Tool Selection for Large Language Model Agents" shows semantic routing achieves 86.4% accuracy on large tool catalogs; graph-based tool usage inertia captures predictable sequential patterns, reducing inference costs by up to 30% while maintaining task completion rates. — [arXiv:2511.04618](https://arxiv.org/abs/2511.04618)
- **Engineering Blog (Amazon):** HITL (human-in-the-loop) is critical for multi-agent evaluation specifically because increased complexity creates emergent behaviors that automated metrics miss. Operational constraints — latency, cost per task, token efficiency, tool reliability — are first-class evaluation targets, not afterthoughts. — [AWS ML Blog: Evaluating AI Agents](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Engineering Blog (Tian Pan, 2025):** Of 7,949 AI agents shipped by one company, only 15% worked. The rest failed silently, looped, or contradicted themselves. Root cause was architecture, not model capability. Context engineering (what info the model has at each step) replaced prompt engineering as the dominant discipline. — [tianpan.co: AI Agent Architecture](https://tianpan.co/blog/2025-10-23-ai-agent-architecture-production)
- **Survey (Tsinghua, December 2025):** Agent memory taxonomy by function: episodic (events), semantic (facts), procedural (how-to). Production systems need all three layers plus short-term and working memory. — [arXiv:2512.13564](https://arxiv.org/abs/2512.13564)

## Gotchas

- **Placing verbose tool schemas in the middle of context degrades focus.** Models attend more to beginning and end positions. Put tool schemas after the task context, not before it.
- **Retry without idempotency on write tools creates duplicate actions.** The standard `try/except` retry loop is only safe for read operations. Write tools need explicit outcome confirmation before retry.
- **Confusing "agents" with "workflows."** Agents dynamically direct their own processes. Workflows use predefined code paths. Most tasks are workflows — wrapping a simple retrieval-augmented call in agent orchestration adds complexity without benefit. Start with the simplest pattern, escalate to agents only when task paths are genuinely unpredictable.
- **Embedding routing degrades on ambiguous tools.** When two tools have semantically similar descriptions, routing accuracy drops. Tool descriptions must be discriminative, not generic — write them as "does X, not Y" pairs.
