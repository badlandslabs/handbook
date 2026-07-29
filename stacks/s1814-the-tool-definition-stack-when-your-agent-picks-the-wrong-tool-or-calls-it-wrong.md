# S-1814 · The Tool-Definition Stack — When Your Agent Picks the Wrong Tool or Calls It Wrong

You give your agent tools. You give it another tool. You debug why it keeps reaching for the wrong one, passing the wrong arguments, or ignoring a tool entirely. The problem is rarely the number of tools — it's how they are defined. Tool interface design is the most underestimated driver of agent reliability.

## Forces

- **A tool that works for humans fails agents.** Ambiguous names, freeform descriptions, relative paths, optional parameters with unclear defaults — these are fine for human developers, but agents pick the wrong interpretation every time. The interface that works for people fails for software.
- **More tools create a routing problem, not just a capability problem.** Anthropic's customer work shows that 0-5 tools is tractable; 5-15 requires grouping and routing logic; 15+ without hierarchy causes the agent to spend more cycles selecting tools than using them. The Shapley value of each new tool decreases sharply past a threshold.
- **Stale state is the silent killer of browser and file tools.** The agent reasons about the world as it was — not as it is. Dynamic content (modals, dropdowns, autocomplete) changes between observation and action. The tool definition is correct; the world it describes is not.

## The move

**Design tool interfaces as if the agent will always take the worst interpretation.** Three layers:

- **Three canonical tool types, clearly separated.** OpenAI's taxonomy: *Data tools* (read, search, retrieve — no side effects), *Action tools* (write, execute, update — with side effects), *Communication tools* (send email, post to Slack — deliver to a human). Agents need this separation to reason about what changes and what doesn't.
- **Poka-yoke the interface — eliminate wrong calls structurally.** Anthropic: "Change the arguments so that it is harder to make mistakes." Anthropic spent *more time optimizing tools than the overall prompt* when building the SWE-bench agent. Their specific win: switching from relative filepaths to mandatory absolute filepaths eliminated a class of path errors entirely. The principle: if documentation can be wrong, documentation is wrong. Use types, enums, and required fields to make incorrect calls uncompilable.
- **Design for outcome, not coverage.** Anthropic: "Start with the simplest solution." The most reliable agent stacks give fewer, better-defined tools rather than many weakly-defined ones. A `search_database(query)` with strict schema beats three loosely-documented search endpoints.
- **Snapshot state after every action for browser and file tools.** The Agent Browser Protocol (ABP) — a Chromium fork for AI agents — captures the entire page state after each action: freeze JS execution, serialize DOM, return the snapshot. The agent then reasons from a consistent, immutable frame rather than a page that may have shifted mid-thought. This addresses the stale-state failure mode structurally rather than prompting around it.
- **Version your tool schemas.** When a tool's parameters change, old agent sessions still hold old tool definitions in context. A versioned schema with a changelog field lets the agent detect drift and recover gracefully.
- **Add a "dry-run" parameter to action tools.** Before executing a write, send, or update action, the tool returns what it *would* do without doing it. Let the agent review the plan, and a separate call executes. This transforms opaque side effects into transparent ones.

## Evidence

- **Engineering Blog:** Anthropic's SWE-bench agent development — absolute paths over relative paths eliminated a recurring error class. Tool optimization outperformed prompt optimization. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Engineering Blog:** Shopify Sidekick scaling data — tool count growth triggers a distinct architecture inflection at 0-5 (single agent), 5-15 (routing), 15+ (grouping/hierarchical). The solution was not better prompting but structural tool organization. — [shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **Show HN:** Agent Browser Protocol — "Most browser-agent failures aren't really about the model misunderstanding the page. Instead, the problem is that the model is reasoning from a stale state." Open-source Chromium fork with post-action state freeze. — [github.com/theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol)
- **Developer Guide:** OpenAI agent taxonomy — three tool types (Data, Action, Communication) with standardized definitions enabling many-to-many agent-tool relationships. — [openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents)
- **Pattern Reference:** Anthropic's poka-yoke application to tool design — structural prevention over documentation over validation. — [agentpatterns.ai/tool-engineering/poka-yoke-agent-tools](https://www.agentpatterns.ai/tool-engineering/poka-yoke-agent-tools)

## Gotchas

- **Documenting a tool is not the same as designing it.** A description that says "use this for X" is ignored when the agent has 12 other tools and is optimizing for a plausible fit. Structure the interface so the wrong choice is mechanically harder than the right one.
- **Adding a tool to fix a failure is the first reflex and the wrong reflex.** The first instinct after a tool failure is to add another tool. The second reflex should be: can I fix the interface of the existing tool? Anthropic's data: optimizing one tool's definition often outperforms adding a second.
- **Browser tools fail silently in ways file tools don't.** A file tool returns an error code; a browser tool returns a screenshot that looks plausible but reflects the wrong state. Log both the tool result *and* the state snapshot at call time, so you can replay what the agent saw.
- **Sandboxing is not optional for action tools with execution.** Llama.cpp's built-in native tools (read_file, write_file, exec_shell_command) ship with explicit "do not enable in untrusted environments" warnings. Any agent with filesystem or shell access in a shared environment is a remote code execution surface.
