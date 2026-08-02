# S-2039 · The Agent Tool Surface Stack — When Your Agent Has 50 Tools But Can't Really Use Any of Them

You give your agent a rich toolset: file read, file write, shell, HTTP, database, search, calendar, email, Slack, GitHub. Forty-three tools. The agent stares at the menu and picks wrong half the time. When it picks right, it calls the tool with hallucinated parameters. When the parameters are right, the tool returns truncated output and the agent loops. You've optimized for coverage; you've destroyed utility.

This is the **tool surface problem** — the gap between what tools you *have* and what tools your agent can *actually use*.

## Forces

- **Context is finite, tools are not.** Every tool definition competes for token space in the prompt. More tools = worse tool selection.
- **Tool design assumes a rational caller.** Traditional APIs assume developers who read docs. Agents hallucinate, misinterpret, and call wrong.
- **Protocol fragmentation.** Pre-MCP, every tool integration was custom per model. Building N tools for M models = N×M work. This made tool count balloon without quality.
- **Security and capability trade off.** The tools powerful enough to be useful (shell, HTTP, database write) are dangerous enough to require guardrails. Teams over-constrain and under-power.
- **Evaluation is hard.** Tool-calling quality is hard to measure automatically, so it rarely gets measured — it ships broken.

## The move

**Principle 1: Fewer tools, better tools.**

Anthropic's engineering team found that more tools ≠ better outcomes. Target 5–12 high-quality tools that map to specific workflows, not one tool per API endpoint. A `list_contacts` tool is nearly useless; `search_contacts` and `message_contact` each do one thing well. Each tool definition should describe *when to use it*, not just what it does.

**Principle 2: Design tools for agents, not for developers.**

Tools are a new kind of software contract — between deterministic systems and non-deterministic agents. Traditional API design assumes a caller who reads docs and passes correct types. Agent-tool design must assume: wrong parameter types, hallucinated parameter names, and calls that make sense to the model but not the task. Anthropic recommends a prototype → evaluate → analyze → refine loop where you use an agent to identify failure patterns in tool behavior.

**Principle 3: Use MCP as the integration layer.**

The Model Context Protocol went from 100K to 97M+ monthly SDK downloads in ~14 months — the fastest-adopted protocol in AI infrastructure history. As of December 2025, Anthropic donated MCP to the Agentic AI Foundation under the Linux Foundation, backed by OpenAI, Google, Microsoft, AWS, and Block. MCP decouples tools from models: implement a tool server once, use it across any MCP-compatible client. This eliminates the N×M integration problem and lets you focus on tool quality instead of wiring.

**Principle 4: Instrument every tool call for failure modes.**

Four classes of tool failures are endemic: (1) **tool hallucination** — the model calls a non-existent tool or invents a response; (2) **parameter mismatch** — wrong types, missing fields, hallucinated names; (3) **silent failure** — tool returns "success" without doing the thing (missing permissions, truncated output); (4) **retry loops** — the model gets stuck retrying a broken tool 17 times. Every tool needs: structured error responses, a "capability not available" signal, and a retry limit enforced at the orchestration layer, not by the model.

**Principle 5: Constrain the attack surface, not the capability.**

Browser agents, code executors, and shell access are the tools that make agents genuinely useful. The mistake is choosing between "powerful and unsafe" versus "safe and useless." The right move is programmatic constraints (process sandboxing, network allowlists, read-only modes) layered under the tool, not LLM-based judgment inside it. arXiv:2511.19477 found that architecture matters more than model scale for browser agents — proper sandboxing + accessibility-tree context management achieves ~85% on WebGames vs. ~50% for naive approaches.

## Evidence

- **Anthropic Engineering Blog:** Writing Effective Tools for Agents — recommends few, workflow-specific tools over broad API wrappers; iterative evaluation loop; tools designed for agent perception patterns, not developer ergonomics — [https://www.anthropic.com/engineering/writing-tools-for-agents](https://www.anthropic.com/engineering/writing-tools-for-agents) (September 2025)

- **Fordel Studios / arXiv:** MCP in Production: Engineering Reality — 97M+ monthly MCP SDK downloads, 13,230+ public servers, Linux Foundation governance; 88% of open-source MCP servers have broken authentication, single CVE affected 437,000 dev environments — [https://fordelstudios.com/research/mcp-production-engineering-guide](https://fordelstudios.com/research/mcp-production-engineering-guide) (March 2026, updated April 2026)

- **arXiv:2511.19477:** Building Browser Agents: Architecture, Security, and Practical Solutions — proper architecture yields ~85% success on WebGames benchmark vs. ~50% naive approach; model capability is not the limiting factor — [https://arxiv.org/html/2511.19477](https://arxiv.org/html/2511.19477) (November 2025)

## Gotchas

- **Tool count is a liability, not a feature.** Every tool in your prompt competes for selection quality. Audit tool count the same way you audit dependencies.
- **Parameter validation at the tool layer is non-negotiable.** The model will pass `"ten"` as an integer, a field name that doesn't exist, or an empty object. Reject these with structured errors, not vague failure messages.
- **MCP server auth is an afterthought in most open-source implementations.** If you're deploying MCP servers internally, treat authentication as a first-class concern — the protocol makes it easy to expose tools; the defaults don't make it secure.
- **Silent failure is worse than loud failure.** A tool that returns "completed" when it didn't run is more dangerous than one that throws an exception. Every tool needs a verifiable success signal, not just a status code.
- **Don't give agents broad tools and hope they'll self-restrain.** A shell tool with "be careful" in the description is not sandboxed. Programmatic constraints (container isolation, allowlists, timeouts, read-only flags) are the actual guardrails.
