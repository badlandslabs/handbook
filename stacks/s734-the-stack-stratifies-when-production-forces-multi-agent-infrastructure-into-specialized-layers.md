# S-734 · The Stack Stratifies: How Production Forces Multi-Agent Infrastructure Into Specialized Layers

The moment you need more than one agent — or more than one tool, or persistent memory, or sandboxed code execution — the "LLM with tools" mental model breaks. The production stack fragments into layers with distinct failure modes, defensibility profiles, and competitive dynamics. Treating them as one system is the root cause of most agent rewrites.

## Forces

- **The agent stack has different defensibility profiles per layer.** Sandboxing (secure execution), orchestration (workflow/state), tools (MCP), and memory (vector stores) are architecturally independent — yet most teams build or adopt them as a bundle. Bundling optimizes for demo speed; separating optimizes for long-term maintainability.
- **Inference cost structure changes dramatically as agents chain.** A single-agent task = 1–2 LLM calls. A multi-agent task with planning, tool calls, verification, and error recovery = 10–20 calls. A naive cost model built on single-call pricing will be wrong by 10x in production.
- **MCP went from experimental to enterprise-default in 18 months.** As of July 2026, 78% of enterprise AI teams have MCP-backed agents in production, 28% of Fortune 500 companies run MCP servers, and monthly SDK downloads reach ~97 million. The tool-interoperability problem is solved — teams that don't use it are building bespoke adapters that will become liabilities.
- **"More agents" is a cost amplifier, not a quality guarantee.** Multi-agent costs 2–5x more in tokens for the same work. Production multi-agent systems exist because work has genuine boundaries — different access controls, different tool sets, different models — not because two LLMs are smarter than one.

## The move

Design the agent system as five independent layers, and own the integration contracts between them:

**1. Execution layer (sandboxing).** Isolate agent code execution from production infrastructure. Options: E2B, Modal, Firecracker microVMs, Shuru. Don't embed execution in the orchestrator — this layer has a completely different security and scaling profile.

**2. Orchestration layer (workflow + state).** Choose based on the paradigm that matches your problem shape:
- LangGraph (state machines) — most control, best for complex/production-grade workflows with detailed state management
- CrewAI (role-based) — fastest path to working prototype; roles map cleanly to organizational structures
- OpenAI Agents SDK — if you're already in the OpenAI ecosystem and want minimal additional dependencies
- AutoGen / Microsoft Agent Framework — enterprise/Azure shops; GA planned Q1 2026 after the AutoGen + Semantic Kernel merger

**3. Tool layer (via MCP).** Build one MCP server per resource (Slack, Postgres, GitHub, internal API, filesystem) and consume it across all agents. Stop writing custom tool integrations. As of mid-2026, MCP SDKs support Anthropic, OpenAI, Google, Microsoft, Salesforce, and Snowflake.

**4. Memory layer (vector store + semantic cache).** Production RAG requires more than top-k vector retrieval:
- Use hybrid search (dense + sparse with Reciprocal Rank Fusion) to avoid vocabulary mismatch failures (dense embeddings miss exact tokens like `ISSUE-1234`)
- Q&A-augmented chunking outperforms naive sentence splitting — pre-generate question-answer pairs from content to anchor retrieval
- Rerankers can hurt quality in narrow domains — test before committing
- Store durable facts outside the context window; inject only on relevance

**5. Observability layer.** Instrument from day one. LangSmith, Phoenix, or custom structured logging — but something must trace every tool call, LLM invocation, and state transition. Agent failures compound multiplicatively across steps (five steps at 95% accuracy = 77% end-to-end reliability).

## Evidence

- **HN discussion (2025):** The agent stack is splitting into specialized layers; sandboxing is becoming its own distinct concern. Companies building monolithic agentic systems are taking on compound risk — the layers have very different defensibility profiles and should be evaluated independently. — [HN thread on agent stack stratification](https://news.ycombinator.com/item?id=47114201)
- **MCP adoption data (July 2026):** 78% of enterprise AI teams have MCP-backed agents in production; 28% of Fortune 500 companies run MCP servers; ~97 million monthly SDK downloads. MCP went from experimental to enterprise-default in ~18 months. — [andrew.ooo: MCP Enterprise Adoption July 2026](https://andrew.ooo/answers/mcp-model-context-protocol-enterprise-adoption-july-2026)
- **Multi-agent cost analysis (2026):** Multi-agent costs 2–5x more in tokens than single-agent for equivalent tasks. Production multi-agent systems exist because work has genuine boundaries — different access controls, tools, models — not because more agents improve quality automatically. — [Gravity: Multi-Agent Coordination Patterns](https://gravity.fast/blog/ai-agent-multi-agent-coordination)
- **Production RAG patterns (2026):** Naive RAG pipelines fail ~40% of the time at retrieval in production. Hybrid search with RRF, Q&A-augmented chunking, and selective reranking are the three patterns that separate shipping systems from demos. — [onseok: Building a Production RAG System](https://onseok.github.io/posts/building-production-rag-system)
- **Orchestration framework comparison (2026):** LangGraph (state machines) leads for production complexity; CrewAI (roles) leads for prototype speed; Microsoft Agent Framework leads for Azure/enterprise. AutoGen is effectively deprecated in favor of the Semantic Kernel merger. — [Gheware: LangGraph vs CrewAI vs AutoGen 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Agent cost structure (2026):** Simple agent ~$800/month run cost; RAG-workflow agent ~$2,700/month; multi-agent system ~$6,250/month. Model tokens are only 8–27% of total run cost — senior human oversight dominates above simple workloads. — [Digital Applied: AI Agent Build & Run Cost Index 2026](https://www.digitalapplied.com/blog/ai-agent-build-run-cost-index-2026)

## Gotchas

- **Don't bundle sandboxing into the orchestrator.** When you need to isolate code execution (developer agents, autonomous scripts), you'll face a painful extraction. Design for isolation from the start.
- **Don't use multi-agent architecture without a clear boundary justification.** If the only reason is "it'll be smarter," you're paying 2–5x the cost for uncertain quality gains. The exception is genuinely separate domains (different access, different tools, different models).
- **Don't skip MCP because "we only use one model."** The tool interoperability problem MCP solves isn't about model variety — it's about avoiding N×M custom integrations. One MCP server per resource consumed across all agents is the right default.
- **Don't build RAG without hybrid search.** Pure dense retrieval fails on exact-match tokens (IDs, codes, technical terms) that sparse retrieval handles naturally. RRF fusion costs ~1ms and fixes the most common production complaint.
