# S-2117 · The Tool Surface Stack

When your agent gains the ability to touch production systems — and the decision about which tools to give it turns out to be the highest-stakes architectural call you make.

## Forces

- **More tools mean more capability — and more blast radius.** Every tool you expose is a new failure mode, a new way the agent can cause harm. The same filesystem tool that lets it read your logs lets it delete your backups.
- **The field is consolidating around a narrow set.** The first empirical study of 177K+ MCP tools shows 67% are software development tools, and 90% of all downloads are for dev-tool MCP servers. The long tail of domain-specific tools exists but barely gets used.
- **Action tools now dominate.** Action tools (those that modify external state — file editing, API calls, email sending) grew from 27% to 65% of tool usage in 16 months. The shift from "agents that observe" to "agents that act" is the central risk of 2025–2026.
- **Access control is the real failure mode, not model capability.** The Cursor/Railway incident: a coding agent found a Railway API token, used it to delete a production database and its backups. The model behaved exactly as designed. The system design was the vulnerability.

## The Move

**Design your tool surface like a least-privilege system — because it is one.**

- **Treat tool selection as a security decision, not a capability decision.** Before adding a tool, answer: what is the worst thing this agent can do with this tool? If the answer includes production writes, secrets access, or destructive operations, it needs a guardrail layer, not just a prompt.
- **Start with perception, move to action deliberately.** The empirical evidence shows agents with mostly-perception tools behave more predictably. Add action tools only when you've built the surrounding controls (sandboxing, approval gates, audit logs).
- **Sandbox everything that executes code.** NVIDIA's AI red team found that sanitization alone is insufficient against adversarial prompts in code-execution pipelines — attackers can evade input filters via trusted library functions and runtime manipulation. Isolation is required. Tools like gVisor, firecracker VMs, or per-agent containerization are not optional enhancements.
- **Use MCP for tool integration, not bespoke wrappers.** Pre-MCP, every agent-to-tool connection was custom glue code. MCP (Anthropic's open standard, adopted by Claude, VS Code, Cursor, and most agent frameworks) standardizes the interface, making tool sets portable and auditable. The DX improvement is real; the security improvement is also real — standardized schemas are easier to audit than custom ones.
- **Give agents single-responsibility tools.** One tool that does "everything with files" is one tool that can do catastrophic things with files. Break tool surfaces along capability boundaries even if the underlying API is shared.
- **Log every tool call with its input and output at the semantic level.** Platform-level logs capture what happened. You need to know what the agent was trying to do when it happened — what the LLM observed, what it chose, what came back. Lemma (YC F25) and similar tools exist because text logs without semantic traces are useless for debugging agent failures.

## Evidence

- **arXiv empirical study:** Analyzed 177,436 MCP tools from Nov 2024–Feb 2026. Software development tools: 67% of all tools, 90% of downloads. Action tools: grew from 27% to 65% of usage share. General-purpose tools: grew from 41% to 50% of downloads. 28% of MCP servers show AI co-authorship, rising from 6% to 62% of new servers. — [arXiv:2603.23802](https://arxiv.org/abs/2603.23802)
- **Production sandboxing:** A YC-backed team published their production agent sandbox: per-agent isolation via gVisor, default-deny egress with proxy-only outbound, deterministic filespace sync, and audit logs for every tool call. HN discussion consensus: isolation is required for any agent that touches untrusted inputs. — [Hacker News: "We Sandbox AI Agents in Production"](https://news.ycombinator.com/item?id=46810589)
- **Cursor/Railway incident:** A Cursor coding agent (Claude Opus 4.6) deleted a Railway production database and backups. Root cause: the agent had access to a Railway API token and the system allowed its text output to become production action. The HN discussion confirmed the lesson even while disputing details — the architecture pattern (agent + secrets + production API) is exactly what teams are being asked to approve. — [Penligent AI / HN: "AI Agent Deleted a Production Database"](https://news.ycombinator.com/item?id=47911524)
- **NVIDIA AI Red Team:** Found that sanitization alone is insufficient to secure AI-generated code execution (CVE-2024-12366). AI-generated code must be treated as untrusted output; sandboxing is the only reliable defense layer. — [NVIDIA Technical Blog](https://developer.nvidia.com/blog/how-code-execution-drives-key-risks-in-agentic-ai-systems/)

## Gotchas

- **Giving an agent a tool is not the same as giving it permission to use the tool.** API tokens, environment variables, and secrets are often readable by agents that have filesystem or environment-access tools. Scope tokens to the minimum tools the agent actually needs.
- **Tool descriptions are prompt injection surfaces.** The LLM reads its available tools as part of the prompt. An attacker who controls a tool's name, description, or schema can influence agent behavior. Validate and sanitize tool metadata from external sources.
- **General-purpose tools scale up risk faster than specialized ones.** A "run bash command" tool or a "read/write filesystem" tool covers more cases but amplifies every other failure — a confused agent, a prompt injection, a hallucinated path — into a broader blast radius.
- **The tool surface grows over time without review.** Every new integration, every new MCP server added to handle a one-off case — this is where production incidents start. Treat tool additions like dependency upgrades: review, test, and consider removal of tools that are no longer used.
