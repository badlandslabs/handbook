# S-1163 · The Orchestrator-Worker Stack — When One Agent Isn't Enough But Five Are Chaos

[You have a task that exceeds what a single LLM context can hold, or requires parallel workstreams, or demands specialist skills you can't fit into one prompt. You've seen multi-agent demos — they look elegant. Then you try to build it, and within a week your agents are looping, losing context, duplicating work, or one agent goes rogue and spawns twenty sub-agents. The fix isn't adding more agents. It's a specific, minimal architecture for coordination that actually holds up in production.]

## Forces

- **Parallelism vs. coordination cost.** Subagents operating simultaneously compress time-to-completion but introduce synchronization, context-passing, and failure-propagation problems that don't exist in single-agent systems.
- **Separation of concerns vs. context fragmentation.** Specialists with focused prompts and tools are more reliable, but splitting work across agents means the LLM managing handoffs has no shared working memory — it must reconstruct state from artifacts.
- **Authority vs. scope creep.** An orchestrator agent with broad authority (like the HN practitioner whose "CEO agent" created 20 sub-roles and had agents writing memos to each other) becomes a liability. But too much top-down control makes the system sequential and negates the parallelism benefit.
- **Standardized handoffs vs. LLM-native continuity.** Agents passing work via unstructured text assume the receiving LLM will understand the prior agent's reasoning. In practice, structured formats (JSON schemas, markdown task files) dramatically reduce hallucinated context.

## The Move

**Supervisor + Specialists, with coordination via shared artifacts — not direct agent-to-agent calls.**

1. **One supervisor.** A single orchestrator agent decomposes the user's task into subtasks, assigns them to specialists, and synthesizes results. It holds the global plan. It does not execute subtasks itself.

2. **Specialists run in parallel.** Each specialist gets its own context window and tool set. Parallelism is the primary benefit of multi-agent architecture — if specialists run sequentially, you paid the coordination cost for no speed gain.

3. **Agents coordinate through artifacts, not calls.** Specialists write outputs to a shared workspace (markdown files, JSON blobs, task status files). The supervisor reads these artifacts. No agent calls another agent's LLM directly. This eliminates circular dependencies and makes the system auditable.

4. **Roles with hard constraints.** Give every agent a narrow, explicit mandate with defined outputs and a maximum scope. The HN growity.ai team learned this the hard way: their CEO agent with "broad authority" created chaos within hours. A tightly scoped role with bounded artifacts prevents scope creep.

5. **Explicit state in the coordination layer.** The supervisor tracks task status (pending, in_progress, done, failed) in a shared state object. This is not implicit in conversation history — it is a structured data structure the orchestrator reads on every cycle.

6. **Async by default.** Long-running specialist tasks should be non-blocking. The supervisor polls or waits on artifact completion signals. Synchronous multi-agent calls lead to timeouts, cascading failures, and poor user experience under load.

7. **Fail fast and escalate.** When a specialist fails after retries, the supervisor marks the task as failed and escalates — either retries with a different specialist, falls back to a default behavior, or surfaces the failure to the user. Silent failure cascades are the most dangerous failure mode in multi-agent systems.

## Evidence

- **Anthropic engineering blog:** Their Research feature uses an orchestrator-worker pattern where a lead agent plans the research process, spawns parallel subagents that search simultaneously, then synthesizes findings. Key insight: "Parallel compression — subagents operate in parallel with separate context windows, exploring different aspects before condensing important tokens." The separation of concerns between planning (orchestrator) and execution (workers) was central. — [Anthropic Engineering: Multi-Agent Research System, June 2025](https://www.anthropic.com/engineering/multi-agent-research-system)

- **TURION.AI field notes:** After deploying multi-agent systems across a dozen production contexts, they concluded: "Supervisor + Specialists" is the pattern that actually works in production. The timeline they observed: "Demos looked great in 2023. Production deployments looked cursed in 2024. By 2025–2026, viable patterns emerged." Key finding: most production multi-agent systems are actually this pattern — simple, debuggable, effective. — [TURION.AI: Multi-Agent Orchestration Infrastructure Lessons, March 2026](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)

- **HN practitioner (yego/growity.ai):** Built a real SaaS (Telegram Ads automation) with a 3-role Claude Code setup (CEO, backend, frontend). Agents coordinate through a shared docs repo with structured subdirectories (tasks/, messages/, decisions/, tracking/). Direct lesson: "Agents don't talk to each other directly. They coordinate through a shared docs repo." When they gave the CEO agent broad authority without constraints, it created 20 roles and had agents writing memos to each other within hours. The fix was hard role boundaries and structured artifact-based coordination. — [HN: Multi-agent Claude Code setup, 2025](https://news.ycombinator.com/item?id=47245373)

## Gotchas

- **Don't let agents spawn agents.** Hierarchical nesting (orchestrator → agent → sub-agent → sub-sub-agent) rapidly becomes undebuggable. If you need more depth, decompose at the supervisor level, not by delegating to a sub-agent that then spawns more agents.
- **Context window per agent, not shared.** Each specialist's context window is independent. If you need shared state, put it in artifacts — not in a shared conversation that one agent has to scroll through to find context relevant to its task.
- **Cost scales with agent count.** Every additional parallel agent adds an LLM call. The supervisor's synthesis step adds another. Before adding a specialist, confirm the task actually benefits from parallelism (long-horizon research, simultaneous API calls, diverse tool access) — not just because it feels more "agentic."
- **Test handoff boundaries.** The most common failure point is not agent logic — it's the gap between two agents' handoff. Write explicit schemas for what a specialist should produce, and validate the output format before the supervisor tries to consume it. This is analogous to API contract testing.
