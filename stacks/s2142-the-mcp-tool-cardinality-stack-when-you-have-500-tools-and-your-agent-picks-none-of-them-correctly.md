# S-2142 · The MCP Tool Cardinality Stack — When You Have 500 Tools and Your Agent Picks None Correctly

You connected your agent to the MCP ecosystem. You have 500 tools available. Your agent consistently ignores the right tool, hallucinates parameters, or times out selecting from an overwhelming menu. This is not a model intelligence problem. It is a tool cardinality problem: your agent's tool-selection mechanism breaks at scale, and the fix lives in how you organize, describe, and load tools — not in the model itself.

## Forces

- **MCP's success is also its liability.** The ecosystem has thousands of MCP servers. Connecting an agent to all of them seems powerful. But every tool definition consumes context tokens, and every additional tool increases the probability the model selects the wrong one — not from ignorance, but from noise overwhelming signal.
- **Loading strategy dominates tool design.** Anthropic's own engineering guidance (November 2025) recommends that agents should write code to call tools rather than calling tools directly — bundling related operations into scripted workflows to amortize token costs. This is a loading strategy masquerading as a design pattern.
- **Flat tool lists are a context attack.** A flat array of 200 MCP tools with verbose descriptions is a hostile prompt. The model must read every description to rule out each tool. The correct tool is often buried under similar-sounding alternatives.
- **Tool description quality is non-obvious.** Red Hat's MCP engineering post (August 2025) found that their first iteration — one MCP tool per backend API endpoint — created a combinatorial blast radius. The fix was to group tools semantically, not by API endpoint.
- **Selection beats loading.** Projects like Strata (YC P25) report 83%+ accuracy on complex multi-app workflows using semantic tool selection rather than exhaustive tool loading. The difference is architectural: you route to the right tool rather than loading all tools and hoping the model self-selects.

## The Move

### Prune the tool surface before it reaches the model

- **Establish a tool taxonomy, not a flat list.** Group MCP tools into domains (e.g., `code`, `data`, `communication`, `infrastructure`). Load only the domain relevant to the current task, not all domains all the time.
- **Use tool bundling as the default pattern.** As Anthropic's code-execution-with-MCP post recommends: write a script that calls multiple related tools in sequence, expose that script as a single tool. A "deploy service" tool that internally calls `check_health`, `push_image`, `update_config`, and `notify_slack` is one tool, not four.
- **Write descriptions for the model, not for humans.** Include preconditions, failure modes, and mutual exclusion in the description. "Use this tool when X and NOT Y. Fails if Z." beats "Gets document from Google Drive."
- **Lazy-load on intent, not on startup.** For agents with >50 tools, implement an intent-classification step: first classify the user's goal into a tool domain, then load only that domain's tools. This is what Strata does with semantic routing.
- **Enforce single-responsibility at the MCP server level.** One MCP server should do one thing. A server named `filesystem` should not also do `git` and `docker`. If you find yourself putting qualifiers in a tool name (e.g., `code_search_v2_beta`), split it.
- **Containerize MCP servers for isolation and portability.** Mirantis's K8s deployment guide (December 2025) treats each MCP server as an independent container with its own credentials, reducing blast radius and enabling per-tool rate limiting. This also makes the tool surface auditable.

## Evidence

- **Engineering blog:** Anthropic's "Code execution with MCP" documents that direct tool calls consume context per definition and per result, recommending code-writing as the amortized pattern. Their MCP SDKs implement on-demand tool loading. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Product post:** Strata (YC P25) reports 83%+ accuracy on complex multi-app workflows using semantic tool selection over exhaustive loading, achieving this through intent routing before tool invocation. — [URL](https://news.ycombinator.com/item?id=45347914)
- **Engineering post:** Red Hat's TPA/Trustify team found that 1:1 MCP tool-to-API-endpoint mapping created poor agent experiences, and restructured toward semantically grouped tool definitions. — [URL](https://www.redhat.com/en/blog/mcp-server-development-make-agentic-ai-your-apis-customer-zero)
- **Engineering guide:** Mirantis documents containerized MCP server deployment on Kubernetes as the production pattern, enabling isolation and per-tool access control. — [URL](https://www.mirantis.com/blog/agents-and-mcp-on-kubernetes-part-1/)
- **Community repo:** The vectara/awesome-agent-failures repo documents "Tool Hallucination" and "Tool Description Mismatch" as two distinct failure modes, with separate mitigation strategies for each. — [URL](https://github.com/vectara/awesome-agent-failures)

## Gotchas

- **Adding more tools never fixes a bad selection.** Teams often respond to tool failures by adding more specific tools. This increases the selection problem exponentially. Fix selection before adding tools.
- **Tool descriptions are not API documentation.** An API doc describes parameters and return types. A tool description for an agent needs failure modes, mutual exclusivity, and when NOT to use it. The model reads the description to decide whether to use the tool, not just how.
- **Semantic routing adds a failure point.** Intent classification before tool loading is powerful but introduces its own failure mode: if the router misclassifies the intent, the agent never reaches the right domain. Test the router independently, not just end-to-end.
- **MCP's transport is not its tool design.** MCP defines how tools are communicated, not how they are designed. Teams copy MCP server configs from the registry without redesigning the tool interface for their agent's actual use case. The server that works for a human developer using a CLI may be unusable by an agent with a different reasoning pattern.
