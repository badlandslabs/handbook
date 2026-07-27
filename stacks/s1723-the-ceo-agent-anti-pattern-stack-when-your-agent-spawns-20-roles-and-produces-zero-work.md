# S-1723 · The CEO Agent Anti-Pattern Stack — When Your Agent Spawns 20 Roles and Produces Zero Work

When a multi-agent system goes off the rails: agents spawning roles, writing regulations for each other, and completing nothing. You reach for this when delegation becomes a micromanagement spiral and your agent ecosystem produces documentation about work instead of work itself.

## Forces

- Giving an agent broad authority feels natural — humans delegate to humans this way — but agents interpret "full authority" as "create as many specialized sub-roles as possible"
- More roles feels like more capability, but it compounds routing overhead exponentially and makes every tool call ambiguous
- Explicit hierarchy feels rigid until you watch an unbounded system spend 45 minutes on role coordination before the first line of code is written
- Tool count scales with capability but each additional tool increases selection error rate — at 100+ tools, the agent can't reliably route to the correct one
- Human-in-the-loop approval at every step creates safety theater at scale — 93% approval rates in production mean users stop paying attention, defeating the purpose

## The move

**Bounded, pre-defined role hierarchies with scoped tool groups.**

- Define roles before the session starts — no agent spawns its own sub-agents mid-task. The crew structure is the architecture, not an emergent property.
- Limit each role to a fixed tool set. When a task needs a capability outside the role's scope, it hands off to a peer role — not by spawning a new agent.
- Route in two stages: agent selects a tool group, then selects the specific tool within that group. This cuts routing error dramatically at scale.
- Hard cap on concurrent active roles (3–5 max). Queue overflow tasks for a separate run rather than spawning more agents.
- Use checkpointing (LangGraph's durable execution) so handoffs between roles survive crashes without losing state — a handoff file or shared state dict, not an implicit context transfer.
- Keep prompts for each role simple and single-purpose. A role that can do 8 things will pick the wrong one 8 times more often than a role that can do 3.

## Evidence

- **HN "Show HN":** A growity.ai build (2025) created a "CEO agent" with broad authority. Within hours it spawned 20+ roles (CTO, DevOps Lead, QA Engineer, etc.). Agents wrote detailed technical regulations for each other. Result: zero actual code produced. The fix — 3 pre-defined roles (frontend agent, backend agent, project manager) with no spawning authority — shipped the full product. — [URL](https://news.ycombinator.com/item?id=47245373)
- **Shopify engineering:** Sidekick's agentic system tracks tool count vs. system behavior empirically: 0–20 tools = clear boundaries; 20–50 = boundaries blur; 50–100 = tool selection becomes the hard problem; 100+ = agents can't reliably route to correct tool. Their solution: tool grouping abstractions before routing. — [URL](https://shopify.engineering/building-production-ready-agentic-systems)
- **Anthropic "Building Effective Agents":** Anthropic explicitly distinguishes workflows (predefined code paths) from agents (LLM-directed), and recommends starting simple — prompt chaining, then routing, then parallelization — adding orchestration complexity only when evidence shows a simpler pattern won't work. — [URL](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- The "one more role" temptation: when a task is hard, the instinct is to add a specialized agent for it. Resist. The failure mode isn't insufficient specialization — it's unbounded coordination overhead.
- Checkpoint loss on handoff: if agents pass state through raw context concatenation rather than structured handoff files, a mid-task crash loses everything. LangGraph's checkpointing or a shared JSON artifact solves this.
- Approval fatigue: human-in-the-loop at every step sounds safe but produces 93% auto-approval rates in practice. Use capability-tiered permissions instead (read-only → write → execute → admin) with blast-radius caps on action volume.
- Routing at 100+ tools: naive single-stage routing fails. Anthropic's production systems use tool grouping as a mandatory abstraction layer, not an optimization.
