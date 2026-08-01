# S-1976 · The Tool Catalog Stack — When Your Agent Has 30 Tools and Can't Decide Which One to Use

You gave your agent a web search. Then a code interpreter. Then a browser. Then a SQL executor. Then a file reader, a webhook trigger, an image generator, and a dozen MCP servers. You thought you were being thorough. Your agent now spends 40% of its token budget deciding which tool to call. The tool catalog became a liability.

## Forces

- **More tools ≠ better outcomes.** Anthropic's engineering blog documents that loading all tool definitions upfront causes token overhead that compounds with scale — 16k+ active MCP servers exist but teams that load them all at once hit context exhaustion.
- **Tool description quality dwarfs tool count.** A well-written tool description with a clear input/output schema dramatically outperforms a large catalog of vague ones (LangChain production guides, 2026).
- **The composability trap.** MCP (16k+ servers, 9M+ Python SDK downloads per Xenoss analysis) solves tool integration but creates a new problem: you now have access to everything and nothing is prioritized.
- **Breadth vs. depth tension.** Agents need broad capability coverage for general tasks, but deep specialization for production reliability. A general-purpose agent with 30 tools handles more requests; a focused agent with 4 tools handles each one better.

## The Move

Start with the minimum viable toolset and grow by demonstrated need, not anticipated need.

### 1. Categorize by *cognitive role*, not capability type

Group tools by what cognitive work they do, not what they technically are:

| Cognitive Role | Example Tools |
|---|---|
| **Information retrieval** | Web search, SQL query, RAG retrieval, API call |
| **Computation** | Code interpreter (Python/JS), calculator, data transformation |
| **Web interaction** | Browser automation, screenshot, form fill |
| **File I/O** | Document read/write, file system, export |
| **Action execution** | Webhook, email send, database write, deployment trigger |

Agents that receive tools grouped by cognitive role make fewer misrouted calls than those given a flat alphabetical list.

### 2. Load tools on-demand, not upfront

From Anthropic's engineering blog (November 2025): loading tool definitions at context initialization creates token overhead that scales with tool count. The recommended pattern is **dynamic tool loading** — agents discover and load tools as specific subtasks demand them. MCP's architecture supports this natively via its client-server separation. Teams at Block (Goose agent) and Microsoft (Azure AI Foundry Agent Framework) use this pattern.

Practical rule: if a tool's description never appears in the first 3 tool calls of a task, it shouldn't be in the initial toolset.

### 3. Write tool descriptions as *contracts*, not labels

A tool named `search_web` with description `"Searches the web"` will underperform `web_search` with:

```
Purpose: Retrieve current, publicly-available information from the internet.
Input: A specific question or query (not a URL or topic).
Output: Top search results with titles, URLs, and snippets.
Limitations: Cannot access paywalled content. Returns max 10 results.
Error cases: Returns empty array on network failure; returns "rate_limited" on 429.
```

Clear schemas prevent the agent from guessing at input formats and reduce the "which tool handles this?" confusion that plagues large tool catalogs.

### 4. Cap the active toolset at 7–10, route overflow to specialist sub-agents

Evidence from the HN multi-agent orchestration thread (Ask HN, 2025): teams with reliable production systems use a primary agent with 5–8 tools and delegate overflow to specialized sub-agents. One respondent (pablovarela) described a Node.js architecture where each agent owns a bounded toolset in its own V8 isolate. This prevents the primary agent from becoming a router rather than an executor.

### 5. Audit tool utility monthly with call frequency data

Track which tools are called and how often. Any tool with <5% call frequency over 30 days is either over-specialized or poorly described. Either fix the description or retire the tool. This is the counter-intuitive part: **removing tools makes agents better**, not worse.

### 6. Default to composable toolchains over monolithic tools

Rather than one "do everything" tool, compose chains: `[web_search] → [code_interpreter] → [document_write]`. This gives the agent granular control at each step and makes failures isolated and recoverable. Microsoft's Agent Framework explicitly documents this pattern with tool chains in Azure AI Foundry.

## Evidence

- **HN Ask HN (multi-agent orchestration):** Practitioners building production agent pipelines for ~1 year report that most use 5–8 tools per agent, with specialized sub-agents handling overflow. Custom-built orchestration (Node.js in V8 isolates, MongoDB state stores) outperforms framework defaults. — [HN Ask HN #47660705](https://news.ycombinator.com/item?id=47660705)

- **Anthropic Engineering Blog (Code execution with MCP, Nov 2025):** Documents that upfront tool definition loading causes token overhead at scale. Proposes dynamic tool loading via MCP as the solution. Block's Goose agent uses this pattern — all MCP servers are loaded on-demand, not at initialization. — [Anthropic Engineering](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **Xenoss / MCP enterprise analysis (2026):** 16k+ active MCP servers, 9M+ Python SDK downloads, 1,100+ GitHub repos with `model-context-protocol` topic. Block built all MCP servers in-house for security. Microsoft Azure AI Foundry supports Bing Search, Code Interpreter, Vision, and File Search tools. — [Xenoss MCP Enterprise Guide](https://xenoss.io/blog/mcp-model-context-protocol-enterprise-use-cases-implementation-challenges)

- **OpenAI Agents SDK (March 2025):** Hosted tool categories: WebSearchTool, FileSearchTool, ComputerUseTool (browser automation), code interpreter. Recommends starting with hosted tools before building custom integrations. — [OpenAI New Tools for Building Agents](https://openai.com/index/new-tools-for-building-agents/)

- **LangChain production guides (2026):** Pin every dependency (langchain==0.3.20, langgraph==0.0.24), set max_iterations and max_tokens budgets per query. Tool descriptions should include error cases and limitations — agents without these guidance hints call tools incorrectly and burn budget on retry loops. — [Markaicode LangChain Production Use Cases](https://markaicode.com/usecases/langchain-for-ai-agent/)

## Gotchas

- **The "helpful" tool expansion trap.** Every sprint, someone adds a tool "just in case." After 3 sprints, you have 37 tools and the agent routes incorrectly 30% of the time. The fix is a tool removal ceremony, not more tools.
- **MCP server proliferation.** 16k+ MCP servers exist, but loading more than 10 at once degrades performance (token overhead, context pollution). Pick a curated subset and rotate based on task domain.
- **Tool description hallucination.** Agents sometimes invent parameters or return formats not in the tool schema. Guard with explicit error messaging from tool outputs — the model corrects itself when given specific error feedback (LangChain's ReAct agent docs confirm this).
- **Browser automation token costs.** Computer Use / browser tools return DOM snapshots that can consume 10k+ tokens per page. Cache aggressively and set max_steps limits.
- **Tool availability != tool reliability.** A tool being *available* via MCP doesn't mean it's *reliable* at runtime. One respondent on HN reported their webhook tool worked in testing but silently failed in production under load — requiring a separate health-check tool.
