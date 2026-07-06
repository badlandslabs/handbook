# S-677 · Choose LangGraph: The Orchestration Decision That Compounds

[Teams spend weeks debating LLM choice but make the orchestration framework decision in an afternoon. The opposite is correct. Your orchestration layer determines every architectural property downstream — observability, testability, failure recovery, cost profile. Pick it like you pick your database: once, deliberately, with the hard cases in mind.]

## Forces

- **Fast prototyping vs. painful rewrites.** CrewAI gets agents running in hours. By month three, teams hit the wall: implicit state, opaque routing, no way to replay a failure. LangGraph starts slower but scales without architectural surgery.
- **The "conversation as code" illusion.** AutoGen's conversation-first model maps cleanly to demos. Production workflows are not conversations — they are state machines with side effects, retries, and human-in-the-loop gates. Converting a conversation model to handle that is rewrite-level work.
- **Tool count is a trap.** Shopify's Sidekick team identified a cliff at 20–50 tools: "boundaries become unclear, unexpected combinations emerge." At 50+, a flat tool list stops working regardless of framework. The right orchestration model lets you group, namespace, and route tools structurally — not by better prompts.
- **Learning curve vs. rewrite cost.** The prevailing expert recommendation: "Default to LangGraph unless you have strong reasons not to — the steeper learning curve prevents painful rewrites 6–12 months in." The learning curve is a one-time cost; a rewrite is compounded.

## The move

LangGraph's core bet: model your agent as a **directed graph of explicit states**. Each node is a step (a function or LLM call). Each edge is a transition (a condition). State flows through the graph as data, not as implicit conversation context. This has four concrete consequences:

- **Replay and debug.** Any step in the graph can be re-entered with the same state. Production failures become reproducible.
- **Test each node in isolation.** Unit-test your LLM call nodes with mocked state. Integration-test the graph topology. CrewAI and AutoGen resist this — their agent logic is too entangled with the runtime.
- **Conditional branching is data, not prompting.** "If the document is >10 pages, route to summarizer; otherwise use the full text" is an `if` statement on the state dict, not a prompt engineering problem.
- **Human-in-the-loop is a first-class concept.** Add a node that suspends execution, returns control to a human, and resumes on approval — without restructuring the graph.

Core philosophy comparison across the three dominant frameworks:
- **LangGraph** → state machines
- **CrewAI** → roles
- **AutoGen** → conversations

## Evidence

- **Engineering blog (Shopify, ICML 2025):** Sidekick evolved from simple tool-calling to a structured agentic loop. Tool count created a complexity cliff at 20–50 tools where boundaries became unclear and unexpected combinations emerged. They migrated toward graph-structured state management to handle tool routing and failure recovery. — https://shopify.engineering/building-production-ready-agentic-systems
- **Production comparison (Gheware DevOps, 2026):** LangGraph recommended as default for production systems. Key finding: CrewAI's fastest-path advantage disappears within 6–12 months as teams hit scalability limits. AutoGen (merging with Semantic Kernel) is positioned as the enterprise Azure choice, not a general-purpose pick. — https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html
- **Primary research / practitioner analysis:** The three frameworks have distinct core metaphors that determine their ceiling. State machines (LangGraph) are testable and debuggable. Role-based agents (CrewAI) are intuitive and fast to prototype. Conversation models (AutoGen) work for multi-turn chat but struggle with structured workflows and side effects. — https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison

## Gotchas

- **LangGraph has real complexity at the edges.** Conditional branching with multiple exit paths, parallel node execution, and subgraph composition take time to internalize. Budget a learning ramp before committing to it for production.
- **LangGraph does not abstract your LLM.** You still own the prompt engineering, tool schema definitions, and output parsing. The framework gives you structure; you still do the work.
- **CrewAI's simplicity is a real tradeoff, not a bug.** If your workflow genuinely fits the "role-based team" model (specialist agents with clear handoffs, no complex state), CrewAI's lower ceremony is a genuine advantage. The failure mode is assuming your use case fits that model when it doesn't.
- **AutoGen is shifting.** Microsoft is merging AutoGen with Semantic Kernel into a unified Agent Framework with GA planned Q1 2026. Evaluate this as a moving target, not a stable product.
