# S-1299 · The Tool-Grant's Problem — When Your Agent Can't Do Anything Useful but Gives It Full System Access

You need your agent to actually accomplish tasks, not just answer questions. The moment you give it real tools — a browser, a shell, an MCP server, code execution — you inherit every security, reliability, and cost problem those tools carry. The moment you don't, you have a chatbot. Most teams ship neither: an agent with toy tools that fail at the edges of its narrow domain and real tools that fail catastrophically everywhere else.

## Forces

- **More tools → more capability, more blast radius.** A browser tool lets an agent navigate any website. It also lets an agent click anything, fill any form, and exfiltrate any data it can read. The capability unlock and the attack surface expand together.
- **Tool quality is the ceiling, not the model.** Anthropic's review of production agent deployments found that the most effective implementations were "not using complex frameworks or specialized libraries" — they were careful about which tools they exposed and how. The model gets too much blame for failures that live in the tool layer.
- **MCP promises interoperability but delivers token overhead.** Every MCP server dumps its schema into context before the agent does anything useful. A standard GitHub MCP server can consume ~55,000 tokens before the first tool call. CLI tools cost zero context tokens but require the agent to generate valid shell commands — which smaller models do poorly.
- **Browser automation sounds powerful and is operationally painful.** Browser Use (YC W25, $17M seed) made it trivially easy for agents to navigate any website. It also introduced unreliability: dynamic content, CAPTCHAs, login flows, and anti-bot detection. Agents that click through UIs are slower, flakier, and harder to debug than agents that call APIs.

## The Move

**Choose tools by workflow specificity, not by what's technically possible.**

- **Structured API tools (REST/GraphQL MCP)** — When the agent needs to interact with a known, stable API. This is the highest reliability option: deterministic inputs, deterministic outputs, easy to log and replay. Build an MCP server or tool wrapper that exposes only the operations the workflow needs, with the minimum parameter surface. Do not expose raw CRUD endpoints — wrap them in domain actions ("create_github_issue", not "POST /repos").
- **Browser tools** — When the target has no API or the API is too expensive to reverse-engineer. Browser Use, Anthropic computer-use-in-Docker, and Coasty (YC S26) all approach this differently: DOM parsing vs. screen observation vs. screen+keyboard recording. The right choice depends on whether the target is an internal web app (Browser Use works well) or a legacy desktop app (Coasty's VM-based approach wins). Always run browser tools in an isolated VM with minimal privileges.
- **Code execution tools** — When the agent needs to do computation, data processing, or orchestrate other tools. smolagents' CodeAgent (HuggingFace, 28k stars) pioneered having the LLM write Python code that *calls* tools, rather than generating JSON tool-call dictionaries. This cuts step count by ~30% and is more natural for RL-trained models. Sandboxing is non-negotiable: Docker container with no network access, no filesystem access outside a temp dir, CPU/memory limits, and a timeout.
- **Filesystem tools** — Only when the workflow requires reading or writing files (codebases, documents). Scope strictly: restrict to project directories, never home directory or system paths. The attack surface of a "read any file" tool is "everything the process can read."
- **Shell/CLI tools** — For local tooling (git, docker, npm). Higher reliability than generative tools for well-understood operations. Lower capability ceiling than LLM-native approaches. Best used for orchestration, not for generating complex command pipelines from scratch.

**Design the tool interface as carefully as the model prompt.**

A tool is an API. Its description, parameter names, types, and constraints determine whether the agent uses it correctly. Bad tool design creates failure modes that no amount of prompt engineering fixes:

- Name tools by *intent*, not implementation: `send_email_to_customer` not `smtp_submit`.
- Make failure modes explicit in the tool description: "Returns empty list if no results, raises ValueError if date is in the future."
- Limit parameter values where possible. An agent that calls `delete_file(path="/")` has a tool design problem, not a safety problem.

**MCP is the right abstraction, not necessarily the right implementation.**

MCP's value is the discovery and schema layer: agents can enumerate what tools exist without hardcoding. The transport layer (stdio vs. HTTP/SSE) is an operational decision. HuggingFace's smolagents, Lastmile AI's mcp-agent, and Anthropic's agent SDKs all converge on MCP as the tool interface standard. Use it — but treat MCP servers as you would any third-party API: verify schemas, test failure modes, and scope access.

## Evidence

- **Anthropic engineering post (Dec 2024):** "The most successful implementations weren't using complex frameworks or specialized libraries. Instead, they were building with simple, composable patterns." Found that the critical variable was tool design quality, not model choice. Defines agentic systems as those where "LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks." — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **HuggingFace smolagents GitHub README:** CodeAgent writes actions as Python code (not JSON/dict tool calls), reducing step count by ~30% vs standard approaches. 28,400 stars, Apache 2.0. Core agent logic fits in ~1,000 lines. Supports MCP natively via `MCPClient`, multi-agent hierarchies, and vision. — [github.com/huggingface/smolagents](https://github.com/huggingface/smolagents)

- **Browser Use (YC W25):** Raised $17M seed. Their core insight: vision-based browser agents ("look at the screen and click") are slow and unreliable. Their approach: DOM-aware element extraction that makes website buttons and forms "AI-readable" as text, without needing screenshots. Founding demo built in 5 weeks, open-sourced, then raised funding. — [TechCrunch](https://techcrunch.com/2025/03/23/browser-use-the-tool-making-it-easier-for-ai-agents-to-navigate-websites-raises-17m/) and [browser-use.com](https://browser-use.com/)

- **Coasty (YC S26):** API for computer-use agents targeting legacy desktop software and web apps without usable APIs. Operates via VM-based screen observation + mouse/keyboard execution. Includes approval gates and a replayable event log for auditability. HN discussion highlighted the checkpoint/invariant model as a strong fit for compliance-heavy workflows. — [news.ycombinator.com/item?id=48922706](https://news.ycombinator.com/item?id=48922706)

- **Lastmile AI mcp-agent (Show HN, Jan 2025):** Implements four orchestration patterns (Router, Orchestrator-Worker, Evaluator-Optimizer, OpenAI Swarm) composably on top of MCP. Author's framing: "Pretty soon every service is going to expose an MCP interface, and mcp-agent is about letting developers orchestrate these services into applications." — [news.ycombinator.com/item?id=42867050](https://news.ycombinator.com/item?id=42867050)

- **Jesse's Superpowers coding agent (fsck.com, Oct 2025, 435 HN points):** Skills are not loaded into context until the model actively seeks them. Each skill doc is <2k tokens. Agent runs shell scripts to search for relevant skill snippets as needed. A long end-to-end coding session consumed ~100k tokens total. System runs git, runs tests, manages files, uses a "feelings journal" for agent self-reflection. — [blog.fsck.com/2025/10/09/superpowers/](https://blog.fsck.com/2025/10/09/superpowers/)

## Gotchas

- **Connecting an MCP server can cost 55k tokens before the first tool call.** Profile the schema size of every MCP server you connect. Large enterprise MCP servers can easily dominate your context budget.
- **Browser tools fail silently on anti-bot defenses.** CAPTCHAs, Cloudflare challenges, and rate limiting don't show up in screenshots — the agent just clicks random elements forever. Add explicit detection + fallback logic.
- **Sandboxing code execution is harder than it sounds.** A Docker container with `--network=none` still has a filesystem. A filesystem-limited container still has environment variables and credentials. Code agents need multiple layered restrictions.
- **The "capability via more tools" trap.** Teams add tools to cover edge cases, creating a large, confusing tool surface that confuses the agent and amplifies the probability of the wrong tool being selected. Fewer, more composable tools outperform many narrow tools.
- **Anthropic's computer-use demo requires you to read the security warnings.** Their docs explicitly require: dedicated VM/container, no sensitive credentials in the environment, domain allowlist for internet access, human confirmation for actions with real-world consequences. Ignoring this and running it against a browser with your credentials is a self-inflicted incident.
