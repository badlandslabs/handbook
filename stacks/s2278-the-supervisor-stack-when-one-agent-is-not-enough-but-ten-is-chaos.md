# S-2278 · The Supervisor Stack — When One Agent Is Not Enough But Ten Is Chaos

You need a system that does what no single agent can reliably do alone: simultaneously research, draft, review, and route — in the right order, with the right context, without looping forever or tripling your API bill. The moment you spin up a second agent, you inherit an orchestration problem you didn't have with one. The supervisor pattern is how production teams solve it.

## Forces

- **The individual-agent ceiling.** A single agent handling multiple roles conflates context and confuses tools. Give one agent both a browser and a SQL client; it will use the browser to read your database schema. Specialist agents with narrow tool sets dramatically outperform generalists.
- **Orchestration is where engineering actually happens.** 40% of multi-agent pilots fail within six months of production deployment. Anthropic's analysis of 200+ enterprise agent deployments found that 57% of project failures originate in orchestration design — not in the agents themselves.
- **The loop problem.** Without explicit termination conditions and routing logic, agents call each other endlessly. One agent spawning two sub-agents, each spawning two more, compounds latency and cost with no bounding.
- **Context fragmentation.** Every agent needs the right slice of state — not everything, not nothing. Naive "pass everything" strategies hit context windows fast; "pass nothing" strategies lose continuity. Designing the state contract between agents is the real design work.

## The Move

The supervisor pattern: one central agent decomposes a task and delegates to specialist agents, each with a narrow tool set and a clear contract. The supervisor manages control flow, integrates results, and decides when the task is done.

**1. One supervisor, N specialists, each with ≤5 tools.** The supervisor holds the plan. Specialists are deliberately narrow — a "researcher" agent that only calls web search, a "writer" agent that only drafts, a "reviewer" agent that only checks against criteria. Narrow scope is what makes specialists reliable.

**2. Explicit state contracts, not shared context dumps.** Define exactly what each specialist receives as input and must return as output. Use structured schemas (JSON, Pydantic). A 3-line tool definition with two example inputs/outpus outperforms a 1-line one by a wide margin across all major frameworks.

**3. Bounded parallelism at the supervisor level.** The supervisor decides which specialists run in parallel (independent sub-tasks) and which in sequence (dependent outputs). Anthropic's research system uses a lead agent that plans research strategy and spawns parallel subagents — each with a separate context window — then condenses findings before proceeding. Parallelism gives speed; sequencing gives coherence.

**4. MCP for tools, A2A for agents.** MCP (Anthropic's Model Context Protocol, 97M monthly Python+TypeScript SDK downloads as of Feb 2026) is the agent's "hands" — access to external tools. A2A (Google's Agent-to-Agent protocol, backed by 100+ companies including AWS, Microsoft, Salesforce, donated to Linux Foundation June 2025) is the agents' "language" — inter-agent communication. They operate at different layers and are complementary, not competing. A2A v0.3 adds cryptographically signed Agent Cards for enterprise identity verification.

**5. Explicit termination and budget gates.** The supervisor must have a defined stop condition: N iterations max, or "all specialist tasks complete," or a token budget threshold. Without it, loops are not a risk — they are a certainty under production load.

**6. Eval each agent independently before wiring.** Test each specialist's tool-calling accuracy, context handling, and error responses in isolation. Pipeline eval (whole-system end-to-end) catches different bugs than component eval — you need both. The supervisor's routing decisions should be separately evaluated: does it correctly assign tasks to the right specialist?

## Evidence

- **Anthropic engineering post:** Claude's Research feature uses a lead agent that plans research strategy and spawns parallel subagents — each operating with separate context windows, exploring different aspects simultaneously, then condensing findings. Key lesson: "Agents operating individually face fundamental limits that groups of agents do not." The team found that multi-agent systems work mainly because parallelism reduces the cost of exploration — wrong paths get pruned faster, and parallel exploration covers more ground without linear time cost. — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Microsoft ISE (retail partner case study):** A large retail organization evolved from a modular monolith chatbot (router pattern, single-agent-per-query) to a microservices multi-agent architecture with agent reuse across teams. Key challenges: standardized agent onboarding at scale (code-based vs. template/YAML-based), semantic caching for intent detection accuracy (5+ sample utterances per agent meaningfully improves retrieval), and cross-team agent reuse requiring shared capability discovery. — [https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **Requesty production analysis (Gartner data):** 1,445% surge in multi-agent system inquiries Q1 2024 → Q2 2025. Organizations average 12 agents currently, projected +67% growth in two years. 40% of multi-agent pilots fail within six months. 57% of failures traced to orchestration design (Anthropic analysis of 200+ enterprise deployments). The six production patterns identified: Sequential Pipeline, Parallel Aggregation, Supervisor/Hierarchical, Consensus/Routing, Marketplace, and Event-Driven. — [https://www.requesty.ai/blog/multi-agent-orchestration-patterns-that-work-in-production](https://www.requesty.ai/blog/multi-agent-orchestration-patterns-that-work-in-production)

## Gotchas

- **Subagent isolation is a double-edged sword.** Each specialist has its own context window — which enables parallelism but means specialists can't see each other's intermediate results. Design your supervisor to aggregate before re-dispatching, not expect specialists to share state mid-execution.
- **Framework defaults are not production defaults.** LangGraph, CrewAI, and AutoGen all require explicit failure handling for: tool call failures, context window overflow, LLM timeout, rate limiting, and out-of-distribution inputs. None of the frameworks handles this for you by default. Build failure paths alongside happy paths, not after.
- **The supervisor is the single point of failure.** If your supervisor has a bad routing prompt, every specialist gets bad tasks. Invest disproportionately in supervisor prompt quality and routing eval. A single mis-routed task can waste the entire system's capacity.
- **Token costs compound non-linearly.** Multi-agent boost gives +81% performance on parallel tasks but −70% on sequential tasks when wrong pattern is selected. Inference costs reach $5–8 per complex task. Model-tier strategically: use smaller, faster models for routing decisions and specialist execution; reserve the best model for supervisor synthesis.
