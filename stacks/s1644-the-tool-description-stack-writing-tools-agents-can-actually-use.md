# S-1644 · The Tool Description Stack

Your agent has the right tools. Your agent still calls them wrong.

MCP (Model Context Protocol) has won the integration layer — tens of thousands of MCP servers, Anthropic/Google/Linux Foundation backing, a full protocol stack. But adoption of the standard is not the same as adoption of good practice. A research audit of 856 tools across 103 MCP servers found that **97.1% contain at least one "smell"** — a tool description flaw that misleads the agent about what the tool actually does. The protocol works. The tools are the problem.

## Forces

- **Tool descriptions are written for humans, not agents.** Documentation prose, underspecified parameters, and unstated limitations are fine for a developer reading code. They are catastrophic when the LLM has to infer behavior from a JSON schema and a two-line description.
- **More tools means more confusion, not more capability.** Anthropic's engineering team found that loading all tool definitions upfront causes context bloat that degrades agent reliability. Yet most MCP implementations load everything at once.
- **"Accurate tool calling" isn't even on most teams' radar.** Only 5% of production teams cite tool calling accuracy as a top challenge per the Cleanlab enterprise survey — yet this is likely the root cause behind much of their unexplained failure rate.
- **Tool description quality is invisible until it isn't.** A bad description rarely causes an obvious crash. It causes silent wrong behavior: the agent calling the wrong tool, the wrong parameters, or the right tool at the wrong time.

## The move

Write tool descriptions as job postings, not API documentation. The agent needs to know what the tool is *for*, not just what it *does*.

**Be concrete about purpose and output shape.** "Searches a database" is a description. "Returns the customer's 5 most recent order records as JSON objects with order_id, date, and status fields" is a tool. The difference is whether the agent can reason about correctness.

**State limitations explicitly, not implicitly.** 89.8% of MCP tool descriptions fail to state their limitations. If a tool returns at most 100 rows, say so. If it times out after 5 seconds, say so. If it requires a non-null customer_id, say so. Every unstated constraint is a trap the agent will step in.

**Prefer fat tools over thin tools.** One tool that does `GET_CUSTOMER_INFO(customer_id)` is safer than five tools with overlapping SQL capabilities. Anthropic's engineering team recommends batching related tool calls — write code that calls multiple tools internally rather than giving the agent raw access to each. This constrains the search space and reduces mis-execution.

**Use terse, job-description-style system prompts for the agent.** InfoQ's production multi-agent case study at a tier-1 telco found: "The best-performing agents have terse, job-description-like system prompts; cleverness in prompts is technical debt."

**Load tools on-demand, not all at once.** Anthropic's code execution with MCP post describes the context bloat problem: when MCP clients load all tool definitions upfront, each definition consumes context tokens, degrading performance. Implement lazy loading — surface only the tools relevant to the current subtask.

**Define expected output shape for every tool.** If a tool succeeds, what does success look like? If it fails, what does failure look like? Return types and error codes should be explicit in the description, not left to inference.

## Evidence

- **Research paper (arXiv 2602.14878, 2026):** 97.1% of MCP tool descriptions contain at least one smell. 89.8% omit stated limitations. 56% fail to clearly state their purpose. Only 2.9% are completely smell-free. — [https://arxiv.org/html/2602.14878v3](https://arxiv.org/html/2602.14878v3)
- **Engineering blog (Anthropic, Nov 2025):** "Direct tool calls consume context for each definition and result. Agents scale better by writing code to call tools instead." Documents MCP context bloat pattern and on-demand tool loading as the solution. — [https://www.anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Engineering case study (InfoQ, July 2026):** Production multi-agent system for SOC at tier-1 telco using A2A + MCP. Found "terse, job-description-like system prompts" outperform elaborate prompt engineering. Pair MCP with a privileged reviewer agent that enforces safety as code. — [https://www.infoq.com/articles/multi-agent-security-operations/](https://www.infoq.com/articles/multi-agent-security-operations/)
- **Enterprise survey (Cleanlab, August 2025):** Only 5% of 95 engineering leaders with production agents cite accurate tool calling as a top challenge — indicating widespread underdiagnosis of the tool description problem. 70% of regulated enterprises rebuild their agent stack every 3 months. — [https://cleanlab.ai/ai-agents-in-production-2025/](https://cleanlab.ai/ai-agents-in-production-2025/)

## Gotchas

- **Copying API docs as tool descriptions works for humans and fails for agents.** JSON schemas describe structure; they don't describe intent, constraints, or failure modes. Write the intent first, then derive the schema.
- **Augmenting descriptions improves task success but increases execution steps by 67%** (per arXiv study). Better descriptions → agent explores more options → more steps. Design tools narrow enough that this overhead doesn't compound.
- **MCP server proliferation has outpaced MCP server quality.** Thoughtworks notes "tens of thousands" of MCP servers now exist, ranging from JetBrains-quality enterprise tools to single-purpose hobby projects. A tool being available doesn't mean it's safe to give to an agent.
- **Tool count is a liability past a threshold.** Beyond ~20 tools, the agent's tool selection degrades regardless of description quality. Break the tool surface into role-specific subsets and load them on-demand per subtask.
