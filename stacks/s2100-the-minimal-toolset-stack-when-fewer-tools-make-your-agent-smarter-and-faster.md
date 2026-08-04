# S-2100 · The Minimal Toolset Stack — When Fewer Tools Make Your Agent Smarter and Faster

The conventional wisdom says: give your agent more tools so it has more capabilities. More tools means more power. More coverage. More everything. So you connect your MCP server, wire up 50 tools across a half-dozen services, and watch your agent's tool list grow. What actually happens: it gets slower, noisier, less reliable, and more expensive. The problem isn't that your agent lacks tools. The problem is that too many tools degrade the reasoning signal that makes it useful in the first place.

## Forces

- **Context is a zero-sum resource.** Every tool definition, input schema, and description consumed by the context window is context not spent on the task itself. With 50+ tools loaded, the agent spends tokens understanding options instead of executing.
- **Model intelligence is the real capability.** Foundation models are trained on vast corpora of shell scripts, directory navigation, and file manipulation. When you give an agent `grep` and `cat` instead of 30 specialized search tools, you're calling on learned behavior rather than injected behavior.
- **Specialized tools require constant maintenance.** Each tool is a contract: prompt, schema, error handling, version. A tool-per-API agent accumulates maintenance debt proportional to its surface area. A filesystem agent requires zero per-API maintenance.
- **Token cost compounds with tool count.** Loading 3-4 MCP servers (GitHub at ~50 tools, Playwright at 24+, Chrome DevTools at 26+) can exceed 50,000 token overhead before a single tool is called.

## The move

The minimal toolset pattern replaces many narrow tools with a few general-purpose primitives the model already understands.

**The core shift: filesystem + bash instead of tool-per-API.**

- Replace a `list_contacts`, `send_email`, `create_workflow`, `update_template` tool family with a **virtual filesystem** that exposes those resources as files and directories
- Replace specialized query tools with a **bash tool** that runs `grep`, `cat`, `ls`, `jq` against a virtual filesystem
- Trust the model's pre-trained shell literacy to compose the primitives into the desired behavior
- When code execution is needed, give the agent the ability to **write and run code** that calls services directly — the agent decides how to interact, not the tool author
- Scope tools dynamically: load only the MCP servers relevant to the current task, not all servers all the time
- For browser-based agents: use a **vision-first DOM model** — screenshots + extracted DOM tree — with a small action registry of universal browser primitives (click, type, scroll, extract), not per-site automation tools

## Evidence

- **Engineering post (Vercel, Dec 2025):** Vercel's internal text-to-SQL agent `d0` went from 18 specialized tools (80% success rate) to a single `execute bash` tool with filesystem access. Result: **100% success rate**, **3.5x faster execution**, **37% fewer tokens**, **42% fewer steps**. "The agent got simpler and better at the same time. All by doing less." — [https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools)
- **Engineering post (Knock, March 2026):** Knock built their agent using a virtual filesystem + bash approach rather than tool-per-API. "We'd be exposing a tool per resource in the management API, which would bloat the context window without us implementing a more sophisticated tool routing layer." The agent gets a structured representation of resources as files, then uses bash primitives to query and modify. — [https://knock.app/blog/how-we-built-the-knock-agent-virtual-filesystem-and-bash](https://knock.app/blog/how-we-built-the-knock-agent-virtual-filesystem-and-bash) (reprinted at [https://genesis-aka.net/information-technology/professional/2026/07/13/files-over-tools-how-we-built-our-agent-with-a-virtual-filesystem-and-bash](https://genesis-aka.net/information-technology/professional/2026/07/13/files-over-tools-how-we-built-our-agent-with-a-virtual-filesystem-and-bash))
- **MCP discussion + analysis (2025-2026):** GitHub MCP server ships ~50 tools, Playwright MCP has 24+, Chrome DevTools MCP has 26-27. A team working with 70 tools reported measurable latency and token cost impacts; the MCP GitHub discussion notes these servers "cross the ~50,000 token overhead" mark with just 3-4 servers loaded. The pattern is confirmed across the MCP community and independent analysis. — [https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2036](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2036); [https://github.com/kurtisvg/kvg.dev/blob/main/content/posts/20260110-tool-bloat-ai-agents/index.md](https://github.com/kurtisvg/kvg.dev/blob/main/content/posts/20260110-tool-bloat-ai-agents/index.md)
- **Browser-use production architecture (May 2026):** The browser-use library (77K+ stars) runs agents with just a small action registry — universal browser primitives — fed by a screenshot + DOM extraction loop. Production deployments handle millions of runs using SQS-to-Lambda with a stateless agent loop that does not require per-site tool definitions. — [https://browser-use.com/posts/production-architecture-browser-use](https://browser-use.com/posts/production-architecture-browser-use)

## Gotchas

- **Not all agents are equal.** The filesystem + bash approach works because models have strong pre-trained shell literacy. For specialized domains (scientific computation, proprietary APIs without standard interface patterns), the model may not have enough in-context knowledge to compose useful behavior — specialized tools are still necessary there.
- **Sandbox before bash.** Giving an agent `bash` on a real filesystem is a security risk. Pair it with virtualized or sandboxed filesystem access (e.g., in-memory filesystem, WASM-based shell like `just-bash`, or containerized execution) that has no access to the host system.
- **The MCP ecosystem doesn't optimize for this yet.** Most MCP servers ship all their tools at once. You still need to implement scoped tool loading — only serve the tools relevant to the current task context, not the full server schema on every call.
- **Browser agents need fallback for non-DOM content.** Screenshot + DOM works for most web pages but fails on canvas-rendered content, WebGL, and complex SVGs. A hybrid architecture (accessibility tree + selective vision) handles both cases.
