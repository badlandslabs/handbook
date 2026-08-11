# S-2502 · The Minimal Viable Tool Stack · When Your Agent Has 20 Tools and Uses the Wrong One

When your agent consistently picks the wrong tool, takes too many steps, or "gives up" — and your instinct is to add more structure, more orchestration layers, or a tool registry. The real problem is usually upstream: you have too many tools with underspecified descriptions, and the agent is spending its reasoning budget on tool selection instead of task execution.

## Forces

- **Catalog confusion:** A large function catalog forces the model to solve a tool-selection problem before it solves the actual task. Each additional tool increases the probability of mis-selection, and mis-selection compounds across multi-step tasks.
- **Descriptions are the real API:** Agents read tool descriptions to decide — not the code, not the type signatures, not the README. Descriptions are where agentic software differs fundamentally from traditional software.
- **Adding tools is easy; removing them is hard:** Teams accumulate tools over time as they solve individual cases. Nobody owns the catalog holistically, so it grows until it becomes a liability.
- **Description quality is underinvested:** Improving a description costs nothing compared to writing a new tool. But most teams treat tool descriptions as boilerplate, not as the primary interface.

## The move

The minimal viable tool stack: fewer tools, better descriptions, composability handled by the agent rather than the catalog.

- **Cap at 3–5 tools per domain.** If you have more, collapse them. A `run_shell` tool that can invoke anything is more useful than 12 specialized tools the agent must choose between.
- **Write descriptions that explain when NOT to use the tool.** Anthropic's own guidance: "The biggest win is specificity about when NOT to use the tool. Agents pick confidently when there's a clear boundary." Vague capability descriptions create ambiguity the model resolves incorrectly.
- **Treat descriptions as living prompts, not static documentation.** Update descriptions when you observe a mis-selection. A description change costs zero deployment risk compared to a code change.
- **Prefer a single composable tool over a catalog of composable tools.** A shell-style interface (one tool that accepts arbitrary commands) keeps actions in one namespace. Composition happens through the agent's reasoning, not through hardcoded orchestration.
- **Include 2–3 concrete examples per tool.** Examples anchor the model's understanding more reliably than abstract capability descriptions. "Use this to read any file" is weaker than "Use this to read any file. Examples: reading a config file at startup, reading log output after a command, reading a source file to find a function definition."

## Evidence

- **Anthropic Engineering Blog:** "Writing effective tools for AI agents" (2025-09-11) — establishes that tools are "a new kind of software" with fundamentally different contracts than traditional APIs. Key principle: tools most ergonomic for agents end up being intuitive for humans too. The recommended process: build a quick prototype, use an agent to test it, and iterate on descriptions before touching implementation. — https://www.anthropic.com/engineering/writing-tools-for-agents

- **r/LocalLLaMA (1,800+ upvotes):** Former backend lead at Manus with 2 years of agent-building experience argues that large function catalogs force the model to solve a tool-selection problem before solving the actual task. The proposed alternative: a single `run(command="...")` tool exposing Unix-style composable commands. Community response validated the thesis — supporters noted the shell-first framing matches what models already know from training data, and that typed function catalogs add cognitive overhead the model pays for in every call. — https://insights.marvin-42.com/articles/reddit-localllama-unix-agent-tools-en

- **Show HN — Semble (445 points, 151 comments):** Open-source code search for AI agents achieving 98% fewer tokens than grep while maintaining 99% retrieval quality of a 137M-parameter transformer. The project emerged because the author observed that "such tools make the AI's dumb" — large tool catalogs cause agents to over-search and over-read, consuming tokens without improving output quality. The fix was a single, well-scoped tool with a narrow, specific purpose. — https://news.ycombinator.com/item?id=48169874

- **Show HN — Frigade:** Browser-based agent that reverse-engineers authenticated web apps' own API calls and auto-generates MCP tools. The engineering insight: most API webs are confusing, have inconsistent auth, and break on updates. Their solution was to auto-generate tools from observed behavior rather than hand-crafting a large catalog — demonstrating that tool generation from real API traces produces more useful tools than manual catalog building. — https://news.ycombinator.com/item?id=48847834

## Gotchas

- **Adding tools as a first response to failure.** The reflex when an agent picks wrong is to add guardrails or a new tool. More often, the right move is to improve the descriptions of the existing tools. A description change has zero deployment risk and often solves the problem entirely.
- **Designing for human ergonomics.** Tool interfaces designed for humans (verbose schemas, human-friendly output formats, error messages with emoji) are often worse for agents than minimal interfaces. Design for the model's decision-making process, not a developer's experience.
- **Static descriptions that never get updated.** Tool descriptions should be treated like prompts — versioned, tested, and iterated based on observed failures in production. A description that was written in a design doc and never revisited will accumulate edge cases it doesn't cover.
- **Confusing comprehensiveness with capability.** A 50-tool catalog is not more capable than a 5-tool catalog if the 5 tools have better descriptions and the agent can compose them. Comprehensiveness matters for coverage; composition matters for capability.
