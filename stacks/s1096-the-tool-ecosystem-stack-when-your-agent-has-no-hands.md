# S-1096 · The Tool Ecosystem Stack — When Your Agent Has No Hands

An agent without tools is a language model with confidence issues. The question isn't whether to give an agent tools — it's which tools, how many, and how to design them so the agent can actually use them. The gap between "tools exist" and "tools work" is where most agentic projects quietly die.

## Forces

- **Generality vs. reliability is the core trade-off.** A single broad tool (e.g., "run any shell command") is easy to define but fragile in execution. Many narrow tools are reliable but create a combinatorial decision space the agent can get lost in.
- **The contract is inverted from traditional software.** Normally code talks to code deterministically. Tools talk to non-deterministic agents that may call the tool, ignore it, misunderstand it, or hallucinate their way past it. The design assumptions that work for APIs do not work for agents.
- **Tool proliferation is a trap.** MCP has made it trivially easy to expose hundreds of tools. LangChain's 2026 survey found 89% of teams have implemented observability — but observability for what? Agents with too many tools spend tokens deciding what to call and degrade in quality.
- **Browser and code execution dominate.** Every serious production agent needs at least one of these two. The browser gives agents access to the human-facing web; code execution gives them programmatic control over their environment.

## The move

**Design tools as focused capabilities, not API wrappers.** The best production tool sets share a few properties:

- **Specific, action-oriented names.** Anthropic's engineering blog (Sep 2025) recommends tool names that describe the action, not the system: `submit_expense_report` rather than `expense_api`. Agents use names to decide whether to call a tool.
- **Descriptions written for an agent that has no context.** A tool's description is not API documentation — it's the signal the agent uses to decide whether this tool solves the current problem. Anthropic recommends descriptions that include: what the tool does, when to use it, and what failure looks like.
- **Give agents a minimal viable toolset first, expand on evidence.** Start with the 3–5 tools the agent needs to complete its core task. Measure which ones get used, which get misused, and which are never called. Add tools based on failure patterns, not on hypothetical future needs.
- **Browser automation is the most universally useful tool for customer-facing agents.** Browser Use (browser-use/browser-use) has 104k GitHub stars and 11k forks as of mid-2026. Its agents control browsers via Playwright's accessibility tree — no vision model needed. The toolset includes page navigation, element clicking, text input, tab management, file upload, and JavaScript evaluation. Competitors include Skyvern (open-source), Browser MCP (cloud-based with proxy rotation), and OpenAI Operator (sandboxed, for ChatGPT Pro users).
- **Code execution is the most universally useful tool for developer-facing agents.** File system read/write, shell command execution, and structured output parsing give agents the ability to read their own context, modify their environment, and verify their work. Anthropic recommends presenting MCP servers as code APIs the agent can write against, rather than as direct tool calls — this lets the agent process results in the execution environment without additional LLM calls.
- **Observability tooling is table stakes, not optional.** LangChain's 2026 survey (n=1,340) found 89% of teams building agents have implemented observability. At minimum, log every tool call: what was invoked, with what arguments, and what came back. LangSmith, Phoenix (Arize), and Opik are the common choices.
- **Tool routing and triage matter at scale.** When agents have 10+ tools, a routing layer that pre-filters candidate tools based on the current goal reduces error rates and token costs. Anthropic's article describes converting MCP server tool lists into agent-editable code files — effectively a hand-crafted routing heuristic that the agent can introspect.

## Evidence

- **Engineering blog: Tool design principles from Anthropic.** Anthropic's September 2025 post on writing tools for agents is the most concrete primary source. Key findings: tools are "a new kind of software contract between deterministic systems and non-deterministic agents"; specificity beats generality in tool descriptions; agents benefit from writing code against tools rather than calling tools directly. — [URL](https://www.anthropic.com/engineering/writing-tools-for-agents)
- **GitHub: browser-use as the canonical browser tool.** 104k stars, 11k forks. Scores 87.4% on the Odusseus benchmark, outperforming OpenAI, Anthropic, Google, and Microsoft's computer-use agents. Use cases include form filling, grocery shopping, job applications, and personal research assistants. — [URL](https://github.com/browser-use/browser-use)
- **Survey: LangChain State of Agent Engineering.** 1,340 professionals surveyed Nov–Dec 2025. 57% have agents in production (up from 51% the prior year). 89% have implemented observability. 52% run offline evals. 75%+ use multiple models. — [URL](https://www.langchain.com/state-of-agent-engineering)

## Gotchas

- **Tool description rot is invisible.** As your product changes, tool descriptions drift out of sync with tool behavior. The agent keeps calling the tool because the name still sounds right, but the outputs are wrong. Build a periodic description audit into your eval loop.
- **MCP tool proliferation creates a discovery problem.** Exposing 100 tools via MCP is easy; the agent then has to search through all of them to find the right one. Use namespaces, tool groups, and explicit routing descriptions to help the agent narrow its search.
- **Browser automation breaks on layout changes.** Any CSS class, element ID, or XPath that your browser tool relies on is a fragility point. Use semantic selectors and Playwright's accessibility tree rather than pixel-based or DOM-index-based selectors. The browser-use team's self-healing harness (browser-harness) explicitly addresses this.
- **Code execution without sandboxing is a production incident waiting to happen.** If your agent has shell access, it can run `rm -rf /`. Scope execution to specific directories, enforce timeouts, and log all commands before they execute.
