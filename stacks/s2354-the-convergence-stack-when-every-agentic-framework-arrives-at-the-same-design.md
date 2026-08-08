# S-2354 · The Convergence Stack — When Every Agentic Framework Arrives at the Same Design

Claude Code, OpenAI Codex, Gemini CLI, LangGraph, CrewAI, Google ADK, and Amazon Bedrock — built by different companies, in different languages, under different constraints — all converged on the same architecture. Not because they copied each other. Because the constraints are physics: finite context windows, tools that need protocols, safety that can't depend on the model obeying, and tasks too complex for a single invocation. Any team that builds long enough arrives here.

## Forces

- **Frameworks promise flexibility; production demands constraints.** Multi-agent systems are more maintainable and testable when agents are specialized — but adding agents adds orchestration overhead that kills observability and debugging.
- **The simple loop wins; the complex framework loses.** Anthropic's post-launch analysis of dozens of production deployments found consistently that "the most successful implementations use simple, composable patterns rather than complex frameworks" — yet every framework starts with complex abstractions.
- **The 68-point deployment gap is an orchestration gap.** ~79% of enterprises have adopted AI agents, but only ~11% run them in production. The gap isn't adoption — it's making agents reliable enough to ship. That gap lives in orchestration.
- **AutoGen is gone.** Folded into Microsoft Agent Framework in October 2025. LangGraph won production (34.5M monthly PyPI downloads, ~400 production customers including LinkedIn, Klarna, Uber, Elastic). CrewAI won developer mindshare (47K+ GitHub stars, dominates tutorials). Two frameworks and a transition, not three peers.

## The Move

The universal architecture emerging across all frontier systems:

- **Prefer workflows over agents.** Anthropic draws the key line: workflows use predefined code paths (predictable, testable); agents let the model direct its own steps (flexible but harder to bound). Most production systems are workflows with a small, well-fenced agentic core. Reach for dynamic agents only when the task genuinely requires it — open-ended problems, multiple tool calls, model-driven trajectory.

- **Five patterns cover most systems** (DevStudio / Microsoft Azure Architecture Center):
  1. **Sequential chaining** — fixed pipeline, output of one step feeds the next; predictable, low cost, highest debuggability
  2. **Routing** — classify input, dispatch to specialized handler; scales diverse input types
  3. **Parallelization** — fan out identical tasks to multiple workers, aggregate results; max throughput
  4. **Orchestrator-worker** — supervisor decomposes task, dispatches to workers, synthesizes results; the most common multi-agent pattern
  5. **Evaluator-optimizer** — generate → evaluate → refine loop; best for content and code quality improvement

- **Claude Code's architecture as a reference point:** A `while(tool_call)` loop — no DAGs, no classifiers, no RAG. Eight core tools (Bash, Read, Edit, Write, Grep, Glob, Task/sub-agents, TodoWrite). Auto-compacts context at ~75-92% capacity. Sub-agents spawn with their own isolated context (depth=1, only summary returns). The lesson: less scaffolding, more model.

- **OpenAI Codex CLI's architectural answer:** Rust-based agent runtime (67K+ GitHub stars, 10-15 commits/day as of March 2026). Bubblewrap sandbox with namespace isolation (`--unshare-user`, `--unshare-pid`, `--unshare-net`, read-only filesystem, seccomp filters). Rule-based exec policy DSL. Two-phase persistent memory pipeline. JSON-RPC app-server interface as MCP compatibility surface. The sandbox is the architecture.

- **Agent-to-agent data passing:** The HN thread revealed four patterns in production: (1) shared database layer (MongoDB), (2) coordinator endpoint chaining HTTP calls, (3) git worktrees per agent for parallel isolation, (4) structured JSON artifacts passed through a pipeline stage. Sub-agents should return structured data (JSON/XML), not natural language — it lets the orchestrator handle errors programmatically.

- **Observability is the hardest unsolved problem.** Every respondent in the HN multi-agent thread flagged it. Per-step tracing, cost caps, and human-approval gates are the three patterns teams reach for first.

## Evidence

- **Anthropic engineering blog (Dec 2024):** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." — documents after analyzing dozens of production agent deployments. — [URL](https://www.anthropic.com/engineering/building-effective-agents)

- **Ask HN: Multi-Agent Orchestration (4 months ago):** 4 of 7 production respondents built custom orchestration rather than using a framework; the top complaint was observability, not capability. "There's absolute 0 framework out there that's good enough for serious work." — [URL](https://news.ycombinator.com/item?id=47660705)

- **Veso Research — Agentic Patterns (May 2026):** Independent analysis of Claude Code, Codex CLI, Gemini CLI, LangGraph, CrewAI, Google ADK, and Amazon Bedrock all converging on the same 4-layer architecture (tool protocols, instruction schemas, state management, anti-patterns) — [URL](https://veso.ai/research/agentic-patterns/)

- **Zylos Research — Codex CLI Architecture (March 2026):** Deep-dive into the Rust codebase revealing bubblewrap sandbox design, multi-runtime abstraction boundaries, and MCP compatibility layer — [URL](https://zylos.ai/research/2026-03-26-openai-codex-cli-architecture-multi-runtime-patterns)

- **Datarekha ecosystem analysis (2026):** LangGraph: 34.5M monthly PyPI downloads, LinkedIn/Klarna/Uber/Elastic production customers. AutoGen: frozen/folded into Microsoft Agent Framework (October 2025). — [URL](https://datarekha.com/blog/crewai-vs-langgraph-vs-autogen/)

## Gotchas

- **Reaching for an agent first.** Dynamic orchestrator-worker setups are the hardest to evaluate and debug. Start with a fixed workflow; promote to agent only when measurement shows the workflow is the bottleneck.
- **Context window is the hard ceiling.** The moment a tool returns a 40KB payload and the model re-reads history every turn, the context window fills and the agent loops. Architect for compaction before it happens — summarize aggressively, paginate tool results, cap conversation history.
- **Structured data across agent boundaries.** Without it, error handling becomes natural-language negotiation between agents. Define schemas for inter-agent communication before adding the second agent.
- **Framework stability is not guaranteed.** AutoGen went from active development to frozen/folded in under a year. Production systems built on it are now in migration. Prefer frameworks with proven production deployment bases (LangGraph) or commit to custom if you need long-term stability guarantees.
