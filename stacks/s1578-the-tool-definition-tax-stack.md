# S-1578 · The Tool Definition Tax

Every tool you give an agent has a cost that isn't obvious until you run it in production: the tool definition itself. The schema, the description, the parameter docs — that bundle of tokens gets loaded into context on every single request. With 10 tools, this is noise. With 50, it's a budget problem. With hundreds, it changes what the agent actually does.

## Forces

- Every tool definition costs 50–200 tokens before the agent has done any real work — at GPT-4o pricing, 50 tools × 150 tokens × 10k requests/day = ~$19/day just on tool metadata.
- Loading all tools upfront causes decision paralysis — agents waste tokens reasoning about irrelevant options instead of acting.
- Tool proliferation is the default trajectory — every new capability gets a new tool, and the list grows faster than anyone audits it.
- The "obvious" fix (add more tools) is the trap: more tools mean worse performance, not better.
- Tool descriptions are the primary semantic signal for dynamic selection, but writing good descriptions is underappreciated and rarely systematic.

## The move

Control the tool definition tax at three layers:

**Layer 1 — Write tool definitions like APIs, not documentation.**
- Name tools for the action, not the data: `create_jira_ticket` not `jira_ticket_tool`. Include the noun+verb pattern.
- Descriptions should answer: what does calling this do, when should you call it, when should you NOT call it. The "when not to use" clause is the most underused part.
- Keep parameter schemas tight — only expose what the agent actually needs to make a decision, not the full internal schema.
- Add one concrete example in the description of a successful call with real parameter values.

**Layer 2 — Select tools dynamically, not all-at-once.**
- Index tool descriptions in a vector store. At request time, retrieve the top-k semantically relevant tools rather than loading the full list.
- Route by task type: classification queries → search tools, data aggregation → database tools, content generation → no tools.
- Apply a capability scoring layer: semantic similarity × estimated reliability × latency weight. This prevents "close enough" matches from being selected for tasks that need precision.
- Default to a lightweight fallback set (search + read) available on every request so no agent is ever completely stranded.

**Layer 3 — Batch with code execution when call volume is high.**
- Instead of many sequential tool calls through MCP, agents write code that calls the MCP server internally and returns a structured result.
- Example from Anthropic: copying a Google Drive transcript to Salesforce requires 6 tool calls and ~12,000 tokens of intermediate results. A code-execution approach makes one call with a function that runs the pipeline internally.
- Use code execution for multi-step operations that are always co-located: fetch → transform → write cycles that the agent always chains together.

**Bonus layer — Auto-generate tool definitions from real API traces.**
- Tools like Frigade watch authenticated web apps, intercept the API calls the app itself makes, and auto-generate tool definitions from those traces.
- The generated "recipes" include endpoint + method, auth method, response schema, and human-readable descriptions extracted from the API behavior.
- This solves the "nobody wrote the tool definitions" problem — the source of truth is the running system, not a developer with a text editor.

## Evidence

- **Anthropic Engineering (Nov 2025):** Code execution with MCP addresses token consumption by presenting MCP servers as code APIs — batching what would be 6 sequential tool calls into 1 function call, reducing intermediate result tokens from ~12,000 to ~1,500 in their documented example. — https://www.anthropic.com/engineering/code-execution-with-mcp
- **OpenHelm Blog / Max Beech (Oct 2025):** Dynamic tool selection via vector search reduces token overhead from 50–200 tokens per tool to k×50 where k is the retrieval window. Documents real cost math: 50 tools × 150 tokens at GPT-4o pricing → $18.75/day before any actual work. Proposes capability scoring as a ranking signal beyond semantic similarity. — https://openhelm.ai/blog/ai-agent-tool-selection-dynamic-routing
- **Pragmatic Engineer / Gergely Orosz + Elin Nilsson (Dec 2025, 46 engineers surveyed):** Most MCP users are inside enterprises (invisible to public repo counts). Real tool use patterns: internal file systems, Slack/Teams, GitHub/GitLab, internal APIs, databases. Key finding: "MCP servers have few to zero users publicly, but most users are inside companies." Tool definition quality is the top friction point reported by engineering teams. — https://newsletter.pragmaticengineer.com/p/mcp-deepdive
- **HN Show HN (pancomplex, 2025):** Frigade auto-generates MCP tool definitions by running a browser inside authenticated apps, watching API calls, and extracting endpoint/response/auth patterns into reusable "recipes" — effectively a self-updating MCP server with zero manual definition authoring. — https://news.ycombinator.com/item?id=48847834
- **LangChain Blog (Jul 2024):** Few-shot prompting inside tool definitions (showing example inputs/outputs) materially improves tool-calling accuracy — research showed significant boosts across model families when examples were embedded in the tool schema rather than in a separate prompt section. — https://www.langchain.com/blog/few-shot-prompting-to-improve-tool-calling-performance

## Gotchas

- **Tool explosion is the default failure mode.** Every new capability adds a tool, and nobody removes the old ones. Audit your tool list the way you'd audit dependencies — quarterly, with a removal step.
- **Description quality varies more than anyone admits.** Most tool descriptions are written once by the developer who built the tool, not by someone thinking about how the agent will reason about them. The "when not to use" clause alone can cut mis-selection by 30%.
- **Dynamic selection introduces a new failure mode: silent capability gaps.** If the retrieval step misses the right tool, the agent will pick the second-best option and fail in a way that's hard to debug. Log retrieval scores alongside tool selection decisions.
- **Auto-generated tools inherit the auth model of the system they watched.** A tool generated from a browser session running as "admin" will have admin permissions. Treat auto-generated tools as a starting point for security review, not a finished product.
- **Code execution for batching adds latency on the first call.** The function compilation/run overhead means this pattern only pays off when the alternative is 3+ sequential tool calls. For 1–2 calls, the overhead isn't worth it.
