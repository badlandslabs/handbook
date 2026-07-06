# S-699 · Stack Stratification: MCP Is the Universal Tool Layer — Agentic Stacks Are Now 3 Distinct Layers

Every team that ships a production agent hits the same wall around month two: their "monolithic" agent stack has too many responsibilities crammed into one control surface. The fix isn't a bigger framework — it's recognizing that the agent stack has stratified into three independent disciplines, each with different defensibility, different选手, and different failure modes.

## Forces

- **One codebase tries to do orchestration, sandboxing, and tool integration simultaneously.** These concerns evolve at different rates and require different expertise. Treating them as one problem means任何一个变更 touches everything.
- **N×M integration debt compounds silently.** Connecting K agents to M tools is O(K×M) custom code. MCP collapses this to O(K+M) by making tools speak one protocol.
- **Sandboxing is its own discipline.** Agents that execute code, browse the web, or write files need isolation layers — but those layers have nothing to do with orchestration logic.
- **Framework vendors can't be best-in-class at all three layers simultaneously.** LangGraph, CrewAI, and AutoGen all compete on orchestration. None of them are E2B or Modal.
- **MCP adoption has reached escape velocity.** 97M+ monthly SDK downloads, 5,800+ servers, donated to Linux Foundation — this is no longer a bet, it's infrastructure.

## The move

Recognize the three-layer model and source each layer from the best tool for it:

- **Layer 1 — Orchestration:** LangGraph for state-machine/graph-based workflows (supervisor routing, conditional edges, checkpoints, human-in-the-loop). CrewAI for rapid role-based prototyping. AutoGen for research-heavy collaborative patterns. Pick one and commit — mixing orchestration frameworks mid-project is expensive.
- **Layer 2 — Sandboxing:** E2B for cloud sandboxed code execution. Modal or Shuru for serverless compute with fine-grained billing. Firecracker microVMs for latency-critical local execution. This layer handles everything an agent can touch that could be harmful: file I/O, network calls, shell commands.
- **Layer 3 — Tool/Context Protocol:** MCP as the universal interface between agents and external capabilities. One MCP server works across Claude, GPT, Gemini, and local models without per-LLM rewrites. For proprietary tools without MCP servers, wrap them in a thin MCP server (JSON-RPC 2.0 interface) rather than hardcoding tool definitions per agent.

Apply model cascading at the orchestration level: route to a cheap model (GPT-4o-mini, Haiku) first; escalate to a frontier model (Claude Sonnet 4, GPT-4.5) only when confidence is low or the task hits a trigger condition. This alone recovers 40–60% of inference spend.

## Evidence

- **HN thread:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers. These layers have very different defensibility profiles and why going monolithic is the wrong call." — phil, HN commenter, 16 days ago — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **MCP growth metrics:** MCP grew from ~100 servers (Nov 2024) to 5,800+ servers and 300+ clients by late 2025. Monthly SDK downloads hit 97M+ (Python + TypeScript). Anthropic donated MCP to the Linux Foundation under the AAIF. — [https://guptadeepak.com/the-complete-guide-to-model-context-protocol-mcp-enterprise-adoption-market-trends-and-implementation-strategies](https://guptadeepak.com/the-complete-guide-to-model-context-protocol-mcp-enterprise-adoption-market-trends-and-implementation-strategies)
- **Real cost gap:** Production agent costs run 5–15× higher than prototype estimates due to infrastructure, monitoring, and reliability engineering absent in development. First 3 months require a 1.5× multiplier on the upper bound. Token/API spend is only 30–50% of total cost. — [https://www.xcapit.com/en/blog/real-cost-ai-agents-production](https://www.xcapit.com/en/blog/real-cost-ai-agents-production)
- **Framework decision convergence:** By 2026, LangGraph became the production default for planner-executor and hierarchical patterns (state machines, retries, debugging). CrewAI for role-based teams (manager + workers). AutoGen leads on multi-agent collaborative patterns. "Pick LangGraph unless you have an explicit reason for the other two." — [https://www.youngju.dev/blog/llm/2026-03-09-llm-agent-framework-autogen-crewai-langgraph-comparison.en](https://www.youngju.dev/blog/llm/2026-03-09-llm-agent-framework-autogen-crewai-langgraph-comparison.en)
- **Cascade failures as top production risk:** "Cascade failures are what actually takes down production systems most often." Teams invest in adversarial injection testing but neglect inter-agent failure propagation paths. — [https://news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105) (HN Ask: How are you testing AI agents before shipping to production?)
- **MCP as "USB-C for AI":** One port that works with many peripherals. Swap the LLM host without rewriting every connector. — [https://www.gend.co/blog/model-context-protocol-mcp](https://www.gend.co/blog/model-context-protocol-mcp)
- **Agent-cache multi-tier caching:** Valkey/Redis-backed caching for LLM calls, tool calls, and sessions — existing options locked into one tier (LangChain = LLM only, LangGraph = state only). Three-tier coverage. — [https://news.ycombinator.com/item?id=47792122](https://news.ycombinator.com/item?id=47792122)
- **Y Combinator Spring 2025 batch:** Over half of the 144 companies are building agentic AI solutions — a leading indicator of where the startup ecosystem is investing. — [https://news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)

## Gotchas

- **Don't pick an orchestration framework and then force it into a layer it wasn't designed for.** LangGraph is a state machine. CrewAI is a role-assignment system. AutoGen is a conversation framework. Using any of them for the wrong pattern means you're fighting the abstraction.
- **MCP solves the N×M integration problem only if you actually use it for new tools.** Wrapping a legacy REST API in MCP adds indirection without benefit if that API is only used by one agent.
- **Sandboxing is not optional for agents with file system or execution access.** A coding agent without isolation can corrupt state, exfiltrate data, or consume unbounded resources. E2B and Modal exist because this gap is real and expensive.
- **Cascade failures across agents are the dominant production failure mode** — not single-agent errors. Design each inter-agent handoff with explicit error handling, timeout budgets, and escalation paths. An agent that times out waiting for a peer should fail loudly, not retry forever.
