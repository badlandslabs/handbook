# S-2052 · The Tool Paradox: When Giving Your Agent More Tools Makes It Worse

When you keep adding capabilities to your agent and watch it get less reliable.

## Forces

- **The tool accumulation trap.** More tools feel more powerful. In practice, performance degrades with each addition — not from the tools themselves, but from how the LLM selects among them.
- **Token overhead is hidden until it bites.** Tool definitions sit in context. Every tool added is more tokens per call. At scale (thousands of agent invocations/day), this is a material cost.
- **Selection degrades before execution does.** LLMs don't get worse at using tools when you add more — they get worse at *choosing* which one. The decision problem compounds faster than the execution problem.
- **Descriptions are the real interface.** Most "wrong tool" calls aren't capability failures — they're description failures. Vague or overlapping descriptions cause the LLM to guess.
- **Lazy-loading solves the wrong problem for the wrong reason.** On-demand tool loading is sound for token efficiency, but teams adopt it to justify adding more tools — defeating the purpose.

## The Move

**Give your agent a maximum of 5 tools. Pick the ones that directly answer your highest-value queries. Optimize descriptions over count.**

- **Limit the visible toolset.** Anthropic's production guidance: use the smallest toolset that covers your task. Performance curves down as tool count grows, even when every individual tool works perfectly.
- **Scope tools narrowly, not broadly.** A `search_web(query)` tool beats a `web_agent(url, task)` tool. Narrow tools let the LLM reason about *which* to use; broad tools force it to reason about *how*.
- **Write descriptions that answer three questions.** Anthropic's MCP guide: every tool description should state (1) when to call it, (2) what inputs it needs, (3) what structure it returns. Vague descriptions are the leading cause of wrong tool selection.
- **Lazy-load at the protocol level, not the capability level.** Load tool definitions only when needed (e.g., MCP's on-demand loading), not to justify adding more tools. The goal is fewer tools in context, not just fewer in the initial prompt.
- **Audit tool call accuracy monthly.** Track which tools get called, in what sequence, and whether the selections are correct. Wrong tool selection is a distribution shift — it changes as the model's training or your prompt evolves.
- **Separate data retrieval from action.** Don't give agents a single "database" tool that does everything. Break into `query_db` + `write_db` + `schema_lookup` so the LLM can reason about the operation type.

## Evidence

- **Anthropic engineering guide:** "The most successful implementations use simple, composable patterns... Performance degrades as tool count grows." Recommends starting with the smallest viable toolset and adding only when evidence demands it. — [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **HN discussion on building agents (543 points, 88 comments):** Commenters confirm that "giving the model more tools" correlates with worse outcomes in practice. One practitioner: "80% of what I thought I needed, the model handled better with just 3 tools." Framework abstraction layers compound the problem by obscuring which tools are actually called. — [Hacker News: Building Effective AI Agents](https://news.ycombinator.com/item?id=44301809)
- **Anthropic MCP efficiency guide:** Token overhead from tool definitions is the primary scaling bottleneck for MCP-based agents. Recommends on-demand tool definition loading rather than loading all available MCP tools upfront. — [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Digital Applied analysis of computer use agents:** Three major providers (Claude, OpenAI, Gemini) converged on distinct, narrow tool abstractions rather than unified "do everything" tools. Claude uses portable screenshot + keyboard/mouse across VMs; OpenAI uses macOS-native background sessions; Gemini uses DOM-aware browser automation. None attempts to give agents full desktop access. — [Computer Use Agents 2026](https://www.digitalapplied.com/blog/computer-use-agents-2026-claude-openai-gemini-matrix)

## Gotchas

- **Adding a tool feels like progress; it usually isn't.** The psychological reward of shipping a new capability masks the reliability cost of a larger selection space.
- **Tool descriptions decay.** A description that worked at launch degrades as the model's behavior shifts across versions. Treat descriptions as first-class code that needs review.
- **The 3-tool agent outperforms the 10-tool agent on most tasks.** Not because the 10 tools are broken, but because the selection problem is harder.
- **"Universal" tools are anti-patterns.** A single `do_task(description)` tool that tries to cover everything forces the LLM to decompose internally — which is the agent's job, not the tool's job.
- **Token accounting hides the real cost.** Tool definition tokens appear in every call. A 50-line JSON schema loaded 10,000 times/day is a significant and growing cost that most teams don't track.
