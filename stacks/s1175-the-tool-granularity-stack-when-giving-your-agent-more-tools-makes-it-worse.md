# S-1175 · The Tool Granularity Stack

When your agent can do anything but keeps picking the wrong tool — the problem isn't the model. It's how you've packaged the tools.

## Forces

- More tools mean more capability surface — but tool selection degrades past 40–50 tools, regardless of model quality
- Coarse tools (e.g. "do everything with this API") are safer to hand over but require more reasoning from the model
- Fine-grained tools (e.g. "create a row", "update a field") are precise but flood the context and increase call volume
- Tool naming and description are the interface contract — poorly named tools cause silent failures that are hard to debug
- Browser control and code execution are the two tools teams reach for first and fight over longest in production

## The Move

Design tools as narrow, idempotent, and self-documenting. Let the model choose; let the harness validate.

### Tool design principles that hold in production

- **Narrow over wide.** A tool that does one thing reliably beats one that does five things uncertainly. "search_documents(query)" beats "search_and_summarize_and_format(query, style, length)".
- **Idempotent operations.** Every tool call should be safe to retry. GET requests, append-only writes, read-then-confirm patterns.
- **Typed inputs, typed outputs.** JSON schemas on both ends. A tool that returns unstructured text is a black box; one that returns `{status, data, error}` gives the harness something to validate.
- **Self-contained descriptions.** Include what the tool does AND what it does NOT do. "searches internal docs — does not write or modify anything" prevents hallucinated writes.
- **Browser automation via CDP/MCP, not screenshots.** Browser Use (104k stars, YC W25) extracts interactive DOM elements and maps them to model actions. Claude Computer Use and OpenAI CUA both use CDP. Direct pixel-based approaches are slower and less reliable.
- **Code execution in sandboxed containers, not on the host.** Every production team running code-exec tools runs them in Docker/Kubernetes. Browser Use runs browsers in isolated containers. The tool is the capability; the sandbox is the safety boundary.
- **MCP as the tool interface standard.** Anthropic's Model Context Protocol (97M SDK downloads by late 2025) gives you a standard wire format for tools, resources, and prompts. One MCP server (e.g. for a calendar API) plugs into multiple AI clients with no per-client wiring.

### The 40–50 tool ceiling

MCP production data shows tool selection accuracy degrades measurably past 40–50 available tools. When you hit this ceiling, route to specialized sub-agents rather than adding more tools to the parent. A "research agent" with 20 tools + a "writer agent" with 20 tools outperforms a single "research-and-write agent" with 40 tools.

## Evidence

- **Engineering blog:** Anthropic's "Building Effective AI Agents" — after working with dozens of teams, the canonical finding is that the most successful implementations use simple, composable patterns: optimized single LLM calls + retrieval + in-context examples, then tool use when the loop is necessary. Three patterns: extended reflection, tool use, hierarchical agents. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **HN thread:** "Building Effective AI Agents" discussion (543 points, June 2025) — practitioners consistently report that frameworks add abstraction layers that obscure prompts and make debugging harder. "A few clearly defined LLM calls with some light glue logic usually leads to something more stable, easier to debug, and much cheaper to run" — [news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **Open-source repo:** Browser Use (YC W25) — 104k GitHub stars. Makes websites accessible to AI via DOM element extraction + model action mapping. Production deployments run browsers in Docker containers for sandboxing. Supported models: Gemini, Sonnet, Qwen, DeepSeek-R1, ChatOllama — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **Technical deep-dive:** MCP production analysis — tool selection degrades past 40–50 tools. Stdio transport best for local dev; HTTP for production multi-client. Production MCP servers need careful tool naming, idempotent operations, explicit failure semantics — [iron-mind.ai/blog/claude-mcp-explained](https://iron-mind.ai/blog/claude-mcp-explained)

## Gotchas

- **Don't give an agent admin access to its own tools.** A code-exec tool that can spawn more code-exec agents, or a browser tool that can install extensions, will eventually do something unexpected at scale.
- **Tool descriptions are prompts.** "read_file" vs "read_file — reads a text file and returns its contents" differ in how reliably the model uses them correctly. Write descriptions like you write user-facing copy.
- **The harness validates tool outputs, not just inputs.** A tool that returns a success status but an empty dataset is different from a tool that returns an error. The loop needs to know the difference.
- **Browser tools fail silently on anti-bot measures.** Cloudflare, CAPTCHAs, and aggressive rate limiting will cause agents to loop or return corrupted state. Build explicit detection for these failure modes.
- **Code execution tools are the highest blast radius.** A miswired code-exec tool can delete files, exfiltrate secrets, or spin up expensive cloud resources. Always run in a sandbox, always log every command, always set hard resource limits (CPU time, memory, network access).
