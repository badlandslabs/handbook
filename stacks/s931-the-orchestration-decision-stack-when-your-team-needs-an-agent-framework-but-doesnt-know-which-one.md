# S-931 · The Orchestration Decision Stack — When Your Team Needs an Agent Framework But Doesn't Know Which One

You need agents in production. You evaluated LangGraph, CrewAI, AutoGen, and OpenAI Agents SDK — all look reasonable in demos. Your team starts building. Three months later you're locked into an abstraction that fights your workflow, a migration that costs six weeks, or a prototype that nobody can debug. The framework wasn't the problem; the mismatch between your workflow and your framework was.

## Forces

- **No framework is universally best.** Each major framework makes different tradeoffs on the control-abstraction axis — picking one without understanding those tradeoffs means living with them later.
- **Migration is expensive.** Moving from CrewAI's role-based handoffs to LangGraph's state-machine model means rewriting 60–80% of your orchestration logic. The framework you prototype with tends to be the framework you ship with.
- **Abstraction hides cost.** S-925 documents the latency and token overhead of orchestration layers, but the cost you can't see is the debugging tax: when your agent loops or makes a bad decision, you need to trace through YOUR logic and the framework's logic simultaneously.
- **The decision tree is about workflow shape, not feature lists.** "Does it support tools?" and "Does it support multi-agent?" are table stakes — the real question is whether the framework's model of computation matches your workflow's shape.
- **Teams conflate scaffolding speed with architectural fit.** A framework that gets you from zero to demo in two days might be the worst choice for a production system with different reliability requirements.

## The move

### The four-frameworks comparison (mid-2026)

| | LangGraph | CrewAI | AutoGen | OpenAI Agents SDK |
|---|---|---|---|---|
| **Model of computation** | Directed state machine | Role-based team | Message-based negotiation | Handoff + guardrail primitives |
| **Abstraction level** | Low — you define nodes/edges | High — agents + tasks + crews | Medium — agents + group chat | Low — agents + tools + handoffs |
| **Multi-agent native** | Yes (explicit graph) | Yes (built in) | Yes (built in) | Yes (via handoffs) |
| **Production maturity** | High (LangChain ecosystem) | High (crew-based deployments) | Transitioning (→MS Agent Framework) | Growing (OpenAI ecosystem) |
| **Debugging ergonomics** | Good (graph = traceable) | Moderate (crew logs) | Moderate (chat traces) | Good (simple primitives) |
| **When to pick it** | Complex stateful workflows, custom control flow | Fast team-based prototypes, role-clear domains | Research/experimental, Microsoft ecosystem | Lightweight, OpenAI-first, minimal abstraction |

### Decision tree

**1. Start here: is your workflow a graph or a team?**
- If agents have distinct roles with clear handoffs → CrewAI. The abstraction maps directly to your mental model.
- If agents share mutable state and decisions branch based on previous steps → LangGraph. The state machine is the right primitive.
- If you want minimal scaffolding and are building OpenAI-first → OpenAI Agents SDK.

**2. What's your iteration speed vs. control requirement?**
- CrewAI: fastest prototype-to-working. Ships in days. When you need custom routing logic, you fight the abstraction.
- LangGraph: slowest to prototype, highest control. Right choice when you need to trace exactly why a decision happened.
- OpenAI Agents SDK: middle ground. Good if you're staying in the OpenAI ecosystem and want to stay close to the metal.

**3. Are you in the Microsoft ecosystem?**
- AutoGen is in transition to Microsoft's Agent Framework. New projects should avoid it unless you're committed to that migration path.

**4. One structural decision that overrides all others:**
Build your **tool integrations as MCP servers regardless of framework choice**. The interoperability pays when you need to switch frameworks or add agents. Every other pattern is reversible; this one is not.

```python
# Framework-agnostic MCP tool definition — use this regardless of which you pick
# This pattern survives framework migrations

from mcp.server import MCPServer
from mcp.types import Tool, TextContent

server = MCPServer(
    name="your-tools",
    tools=[
        Tool(
            name="search_knowledge_base",
            description="Search internal docs. Returns top-k chunks with source URLs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="write_to_crm",
            description="Create or update a CRM record. Idempotent on external_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "object": {"type": "string"},
                    "external_id": {"type": "string"},
                    "data": {"type": "object"}
                },
                "required": ["object", "external_id", "data"]
            }
        ),
    ]
)

# LangGraph usage
from langgraph.prebuilt import create_react_agent
graph = create_react_agent(model, tools=server.tools)

# CrewAI usage
from crewai import Agent
agent = Agent(role="Researcher", tools=server.tools)  # same MCP tools

# OpenAI Agents SDK usage
from agents import Agent
agent = Agent(model=model, tools=server.tools)  # same MCP tools
```

### The anti-patterns

- **Choosing by GitHub stars.** LangGraph has the most stars; it's also the most complex. Stars correlate with community size, not fit.
- **Prototyping in CrewAI, migrating to LangGraph.** The mental model is different enough that migration is a rewrite, not a port.
- **Using AutoGen for new projects in 2026.** The Microsoft migration path is not backwards-compatible. Evaluate only if you're already invested.
- **Skipping the MCP abstraction.** Every framework speaks MCP. Defining tools once and swapping the framework underneath is the only real escape hatch.

## Receipt

> Verified 2026-07-11 — Researched via Gheware DevOps blog (Jun 2026), Knovo.dev framework comparison (Mar 2026), Nexus CrewAI vs AutoGen comparison (Aug 2025), LetsDataScience 2026 roundup. Cross-referenced against S-925 (framework overhead), S-930 (toolkit), S-05 (multi-agent patterns). Frameworks are in active development — re-evaluate at each major version release.

## See also

- [S-925 · The Framework Overhead Stack](s925-the-framework-overhead-stack-when-your-orchestration-layer-costs-more-than-your-llm.md) — the hidden cost of the layer you chose
- [S-930 · The Agent Toolkit Stack](s930-the-agent-toolkit-stack-when-your-agent-has-a-toolbelt-but-no-belt-loop.md) — what goes in the toolbelt after you pick the framework
- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — the abstract patterns the frameworks implement
- [S-10 · MCP](s10-mcp.md) — the protocol that lets tools outlive your framework choice
