# S-2158 · The Tool Provisioning Stack — When Your Agent Has Too Many Keys and None of Them Fit

You've built an agent with the Model Context Protocol. The ecosystem has thousands of servers. The obvious move: give your agent everything it might ever need. You wire up GitHub, Slack, Jira, a browser, code execution, file system, Postgres, Redis, and three search tools. The agent can technically do anything. The agent does nothing well — it ignores the right tools, calls the wrong ones, and burns tokens deciding what to call next. The problem isn't that your agent lacks tools. It's that you gave it too many.

## Forces

- **Tool definitions consume context before the agent starts reasoning.** A single MCP server like Playwright can consume ~22% of a 200K-token context window just in its tool descriptions (Demiliani, 2025). GitHub Copilot's default VS Code toolset ships ~40 built-in tools; with MCP servers added, it easily exceeds what models can meaningfully reason across.
- **More tools → worse tool selection, not better.** GitHub Copilot's team measured this directly: agents ignore relevant tools, call irrelevant ones, and show the "Optimizing tool selection..." spinner when tool counts exceed model capacity. Cutting from ~40 built-in tools to 13 core ones improved SWE-Lancer and SWE-bench-Verified benchmarks across both GPT-5 and Claude models.
- **The MCP ecosystem creates a supply-side pressure to add tools.** Directories like Glama (21,000+ servers), MCP.so (19,700+), and Smithery (7,000+) have made tool discovery frictionless. Frictionless discovery means tools get added without evaluating whether they help the specific agent.
- **Tool fidelity degrades with quantity.** When a server exposes 40+ tools, the model must parse and distinguish among overlapping capabilities. The GitHub Copilot team found that MCP servers often shipped with far too many tools, unintentionally ruining agent performance.
- **The Anthropic default of "start simple" conflicts with the ecosystem's "more is better" signal.** Anthropic's engineering guide recommends using LLM APIs directly with minimal tooling for most use cases, but MCP directories push the opposite message.

## The Move

The pattern that holds across measured cases: **provision tools surgically, not comprehensively.** This plays out across three dimensions:

- **Right-size the tool count per agent.** GitHub Copilot's data shows cutting from ~40 to 13 tools improved agentic benchmarks. The right number depends on model size and task type, but the ceiling is much lower than the ecosystem implies. For task-specific agents, 3–8 tools is the common sweet spot.
- **Use tool routing before the agent sees the toolset.** Anthropic's MCP guidance (November 2025) recommends having the agent write code that calls tools, rather than passing all tool definitions into context — reducing token overhead by up to 98.7% for complex tools. The agent writes one `python_call_tools([...])` line instead of receiving all 40 tool schemas directly.
- **Cluster tools by workflow phase, not by category.** Instead of exposing all file-system tools at once, expose a `researcher` toolset during research and a `writer` toolset during drafting. The DBOS HN agent uses parent-child workflow layers that switch tool contexts between the orchestrator and step agents.
- **Lazy-load MCP servers rather than loading all at startup.** Anthropic's code-execution-with-MCP guide notes that most MCP clients load all tool definitions up front — this is the source of context-window bloat. Dynamic, per-task server loading avoids paying the definition cost upfront.
- **Validate tool coverage with failure-mode analysis, not feature lists.** Ask: "What does the agent fail to do when this tool is missing?" not "Could the agent possibly use this tool?" Stefano Demiliani's own experience: Playwright's MCP server alone consumed 22% of context — yet he probably needed only 2 of its 40+ tools for the task.

## Evidence

- **GitHub Blog (2025):** GitHub Copilot team measured that cutting the default ~40 built-in tools to 13 core ones improved SWE-Lancer and SWE-bench-Verified benchmarks for both GPT-5 and Claude models. Root cause identified: agents ignore relevant tools and call irrelevant ones when the toolset is oversized. Embedding-guided tool routing and adaptive tool clustering introduced as mitigations.
  — *How we're making GitHub Copilot smarter with fewer tools* — https://github.blog/ai-and-ml/github-copilot/how-were-making-github-copilot-smarter-with-fewer-tools/

- **Anthropic Engineering (November 2025):** Anthropic's MCP code-execution guide documents that having agents write code to call tools (rather than passing all tool schemas into context) reduces token consumption by up to 98.7%. They recommend this as the default pattern for production agents at scale.
  — *Code execution with MCP: Building more efficient AI agents* — https://www.anthropic.com/engineering/code-execution-with-mcp

- **DEV Community / DBOS (July 2025):** A production Hacker News deep-research agent built with DBOS demonstrates surgical tool provisioning: the parent workflow orchestrates with minimal tools, and step agents receive only the tools relevant to their phase. The agent uses a 3-layer parent-child workflow pattern where tool context switches between layers.
  — *Build a Reliable Hacker News Deep Research AI Agent* — https://dev.to/dbos/build-a-reliable-hacker-news-deep-research-ai-agent-365a

- **Stefano Demiliani (September 2025):** Documented empirically that a single MCP server (Playwright) consumed ~22% of a 200K-token context window. Concluded that most MCP servers ship with far too many tools, degrading LLM latency and output quality.
  — *Model Context Protocol and the "Too Many Tools" Problem* — https://demiliani.com/2025/09/04/model-context-protocol-and-the-too-many-tools-problem/

- **Hacker News / Agent MCP Studio (2026):** A browser-based MCP agent studio uses WASM sandboxing (Pyodide, DuckDB-WASM) to execute LLM-generated SQL tools safely. The studio registers tools lazily on first call rather than loading all at startup — demonstrating a practical implementation of lazy tool loading.
  — *Show HN: Agent MCP Studio* — https://news.ycombinator.com/item?id=47899375

- **Anthropic Engineering (December 2024):** Anthropic's canonical "Building Effective AI Agents" guide recommends starting with LLM APIs directly, using composable patterns over frameworks, and using agents (dynamic tool use) only when workflows (predefined paths) are insufficient. The guide advocates for simplicity in tool provision as a first principle.
  — *Building Effective AI Agents* — https://www.anthropic.com/engineering/building-effective-agents

## Gotchas

- **Falling for the "more tools = smarter agent" trap.** MCP directories make tool discovery frictionless, which removes the friction that should force you to evaluate whether each tool earns its context cost.
- **Loading all MCP servers at startup.** This is the default behavior in many frameworks and is the primary cause of the context-window bloat documented by Demiliani. Audit what your framework loads by default and disable the servers you don't need.
- **Giving every agent the same toolset.** An orchestrator agent and a specialist step agent have different tool needs. Use different tool contexts per agent role, not a single superset.
- **Tool descriptions that are too generic.** When tools have overlapping descriptions, models cannot distinguish them reliably. Each tool needs a precise description of what it does *and what it does not do*.
- **Forgetting that the Anthropic/MCP team is the same source recommending "fewer tools" and also building the ecosystem that pushes "more tools."** The recommendation and the ecosystem pressure are in direct conflict — the recommendation wins on measured performance.
