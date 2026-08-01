# S-1946 · The Tool Surface Stack

*When your agent has access to every tool it could ever need, and still fumbles the task.*

You built an MCP server. You exposed 47 tools. You gave the agent file access, web search, Slack, Jira, three databases, and a calculator. The agent still opens Slack, reads the message, stares at it, and asks for clarification. Or it calls the calculator 12 times for what a human would do in their head. The tools are there. The agent doesn't use them right.

## Forces

- **Tool count vs. tool clarity** — More tools give the agent more options, but also more surface area for ambiguity. The model picks a tool based on your description, not your intent, and a vague description is an invitation to pick wrong.
- **Description is prompt** — The tool's name, JSON schema, and description string are the only thing the model sees. Your Python implementation, your tests, your README — none of it reaches the agent. Teams optimize the invisible.
- **Schema bugs cascade** — An ambiguity in step 2 of a 5-step agent task corrupts steps 3, 4, and 5. By the time you see the wrong answer, the root cause is three steps back.
- **"Agent washing" inflates expectations** — Gartner estimates only ~130 of the thousands of vendors claiming agentic AI are genuinely agentic; the rest are rule-based bots, RPA, or LLM chat relabeled as agents. When teams adopt a tool labeled "agentic," they inherit a tool surface designed for marketing, not reliability.

## The move

**Design tool descriptions as prompts. Design the tool surface as a minimal necessary set.**

- **Write every tool description as a decision guide, not a docstring.** State the tool's purpose, when to use it (and when not to), what inputs mean in context, and what the output looks like. The model reads this on every turn — treat it like a system prompt fragment.
- **Keep the tool surface lean at first.** Start with the smallest set that covers the task. Add tools only when you observe the agent reaching for a capability it doesn't have — not when you imagine it might need one.
- **Use a protocol, not a custom integration.** MCP (Model Context Protocol) — released by Anthropic in late 2024 and now adopted by OpenAI, Google, Microsoft, and most major IDEs — has become the de facto standard for exposing tools to agents. Building on MCP instead of custom function calling reduces per-tool integration cost and makes your tools reusable across clients. MCP defines JSON-RPC transport for tools, resources, and prompts.
- **Validate schema quality with model-in-the-loop testing, not just code review.** Call your tools with ambiguous parameters and see what the model does. The goal is to make the correct call obvious and the wrong calls feel wrong to the model.
- **Distinguish tools by failure mode, not category.** A web search tool that returns stale data and a browser-use tool that gets blocked by Cloudflare are both "web tools" but have completely different recovery paths. Name and describe them accordingly.

## Evidence

- **Research paper:** 97.1% of 856 MCP tools studied (Feb 2026, arxiv 2602.14878) had at least one "smell" in their description — 56% failed to state purpose, 38% used generic parameter names. Tool schema quality is the dominant failure mode, not model capability.
  — [arxiv:2602.14878](https://arxiv.org/abs/2602.14878)

- **HN discussion:** A January 2025 HN thread ("Ask HN: Are there any real examples of AI agents doing work?") surfaced deep skepticism about "agent washing" — the practice of relabeling workflow automation and rule-based bots as AI agents. Top comments contrasted Anthropic's definition (agents dynamically direct their own processes and tool usage) against vendor claims, with practitioners reporting that most "agent" products were brittle automation under a new label.
  — [Hacker News: Ask HN (86 pts, 76 comments)](https://news.ycombinator.com/item?id=42629498)

- **Real-world tool integration:** Browser-use (107K GitHub stars, MIT license) exposes browser control as an agent tool — the agent clicks buttons, fills forms, and navigates to complete multi-step web tasks. Reddit community testing found it the strongest open-source browser agent performer, ahead of ChatGPT agent and Manus on cost-effectiveness, but still requiring careful prompt framing to avoid dead ends.
  — [GitHub: browser-use/browser-use](https://github.com/browser-use/browser-use) · [Reddit: r/AI_Agents benchmark thread](https://www.reddit.com/r/AI_Agents/comments/1slc8rj/)

- **MCP adoption:** MCP defines a standardized JSON-RPC protocol for tools, resources, and prompts. Adopted ecosystem-wide: OpenAI Agents SDK, Microsoft Foundry, Google Gemini tools, GitHub Copilot, and hundreds of open-source MCP servers (HN MCP, filesystem, Slack, Jira, browser, database tools). Microsoft published a full MCP case study curriculum showing cross-language implementations across .NET, Java, TypeScript, JavaScript, Rust, and Python.
  — [Microsoft: mcp-for-beginners case studies](https://github.com/microsoft/mcp-for-beginners) · [Digital Consulting Team: MCP production guide (June 2026)](https://digital-consulting-team.com/en/blog/building-production-grade-ai-agents-mcp-tools-orchestration-en)

- **Tool taxonomy:** Neo4j's agent tools breakdown categorizes tools by risk and function: web search (low-risk, read-only), retrieval (low-medium), file I/O (medium-high), computer-use/browser automation (high, broad access), and business APIs like email/CRM (high, external effects). The risk profile of each category determines how much autonomy to grant.
  — [Neo4j: Agent tools taxonomy (May 2026)](https://neo4j.com/blog/agentic-ai/agent-tools/)

## Gotchas

- **Don't expose every capability you've built.** If a tool exists but the agent doesn't need it for the current task, it's noise in the context and noise in the model's attention. Tools are a commitment, not a menu.
- **A tool's JSON schema is part of the prompt.** Required fields without defaults force the model to hallucinate values. Optional fields with defaults that aren't stated confuse the model about when it's done. Review the schema the same way you review a prompt.
- **Browser automation tools fail silently against anti-bot defenses.** If your agent needs web access, budget for Cloudflare, CAPTCHAs, and rate limits — they break the "agent completes task autonomously" promise in production. Test against real anti-bot environments, not clean demo pages.
- **"Works in Cursor" ≠ "works in production."** Many MCP servers and browser agents are tuned for the agent's own environment (Claude Code, Cursor, VS Code). A tool that works in a coding agent may have entirely different failure modes when deployed headless in a server environment.
