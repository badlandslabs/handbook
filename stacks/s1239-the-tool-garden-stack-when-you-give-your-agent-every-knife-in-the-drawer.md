# S-1239 · The Tool Garden Stack — When You Give Your Agent Every Knife in the Drawer

You need your agent to be capable. Your solution: connect it to everything. A Brave Search MCP, a GitHub MCP, a Slack MCP, a filesystem MCP, a code execution MCP, a Jira MCP, maybe three more for good measure. The agent can now theoretically do anything. In practice, it spends tokens on tool discovery, makes wrong tool choices, and has an attack surface the size of a parking lot.

## Forces

- **Capability vs. surface area tension.** Every tool you expose is a token cost (GitHub MCP alone costs ~26K tokens to load), a failure mode, and a potential exploit vector. The MCP ecosystem has 13,230+ public servers. More is not better.
- **The context-starvation trap.** Loading all tool definitions upfront is the default. It's also the path to degraded performance — Claude's own docs flag context window exhaustion as the primary cause of agent mistakes. By the time the agent reaches the relevant tool, it may have already forgotten key instructions.
- **Security arrives late.** A 2025 analysis found 43% of MCP servers have command injection flaws. With 10 plugins, exploit probability exceeds 92%. The ecosystem grew too fast for the security conversation to keep pace.
- **Multi-tool orchestration is the high-value use case, not tool quantity.** The real win is chaining GitHub + Slack + Linear in one conversation with zero custom code — not having 15 search tools.

## The Move

Narrow the tool surface deliberately. The patterns that survive production:

- **One MCP server per capability family.** Group by domain (code execution, web search, file system, API integrations). Don't give the agent five different ways to search the web.
- **Load tools on-demand, not upfront.** Anthropic's Tool Search Tool (Nov 2025) reduced token overhead by 85% compared to loading all definitions at once. The agent discovers relevant tools when it needs them, not when the session starts.
- **Constrain output types strictly.** Use `additionalProperties: false`, required/optional fields, and specific enums. Anthropic measured an 18-point accuracy improvement (72%→90%) from tool use examples alone — showing the model *how* to call a tool correctly is as important as describing what it does.
- **Verify before acting.** Give the agent a pass/fail signal for every tool call outcome. Without it, you become the verification loop. Browser Use (YC W25) extracts xPaths for deterministic reruns — the agent can verify its own work against a known-good DOM state.
- **Sandbox aggressively.** Browser agents like Browser Use run in isolated VMs. Intuned (YC S22) runs each automation project in its own isolated machine with session reuse handled at the infrastructure layer. Anthropic's own computer-use demo recommends: dedicated VM, minimal privileges, allowlisted domains only.
- **Scope tokens per tool.** Budget how many tokens a given tool definition can consume before it's worth splitting into a focused sub-agent. Large tool definitions (Jira alone ~17K tokens) should be isolated or replaced with narrow wrappers.

## Evidence

- **MCP ecosystem scale and speed:** Anthropic launched MCP in November 2024 with roughly 100 community servers. By 2025, SDKs hit 97M+ monthly downloads. By March 2026, there were 13,230+ public servers across GitHub, Cursor, VS Code, ChatGPT Desktop, Microsoft Copilot, and Gemini. — [Anthropic Engineering Blog: Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp), [OpenClaw: MCP Examples](https://openclaw.direct/mcp-guide/model-context-protocol-examples)
- **Tool definition bloat is a real production problem:** GitHub MCP (35 tools) costs ~26K tokens to load. Slack MCP (11 tools) costs ~21K. Jira alone costs ~17K. The combined token overhead of a full tool garden can exceed the actual work payload. Anthropic's Tool Search Tool solved this by on-demand discovery, reducing token overhead by 85%. — [Anthropic Engineering Blog: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- **Browser automation is the highest-volume external tool category:** Browser Use (YC W25) became the largest open-source browser agent community, with a cloud offering. Intuned (YC S22) builds on Claude Agent SDK and handles auth/session reuse, scheduling, and concurrency at the infrastructure layer. Both explicitly recommend sandboxing and minimal-privilege VMs. — [HN: Launch Intuned](https://news.ycombinator.com/item?id=48445171), [HN: Launch Browser Use](https://news.ycombinator.com/item?id=43173378)

## Gotchas

- **Loading all MCP servers at session start is the default and it's wrong.** Profile your token consumption per server. Split large servers (Jira, GitHub) into focused sub-agents or use Anthropic's Tool Search Tool for on-demand discovery.
- **MCP security hasn't caught up to MCP adoption.** 43% of servers have command injection flaws. Use OAuth scoping, namespace isolation, rate limits, and sandboxing. Don't give agents credentials they don't need.
- **"The agent can do more things" ≠ "the agent does things better."** Each new tool adds to the decision space the model must navigate. The verification burden grows with the tool count. Fewer, well-scoped tools with clear success criteria outperform a comprehensive tool garden.
- **Context window degradation is silent.** Claude won't tell you it's forgetting instructions because the context is full — it just starts making worse decisions. Monitor context usage with a status line and truncate aggressively.
