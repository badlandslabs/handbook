# S-2643 · The Token Budget Stack — When More Tokens Means More Right Answers

Your research agent answers surface-level questions correctly but fails on anything requiring multi-step investigation. Your coding agent completes simple tasks but produces shallow work on complex ones. You keep adding better prompts, more tools, and stricter guardrails — and the success rate barely moves. Meanwhile, Anthropic's analysis of their own multi-agent system found that **token usage alone explains 80% of performance variance** on the BrowseComp benchmark. The other 20% splits between number of tool calls and model choice. The implication is uncomfortable: for open-ended agentic tasks, the primary variable to optimize is not prompt quality or model selection — it is how many tokens you are willing to spend. This is the **token budget stack**: the structural patterns for allocating, managing, and enforcing token expenditure as the primary dimension of agent quality control.

## Forces

- **Token spend and quality correlate nonlinearly.** Simple queries need few tokens; complex ones need exponentially more. A fixed token cap per request either wastes budget on easy tasks or silently fails on hard ones.
- **Token budgets and autonomy are in tension.** Agents that spend freely solve harder problems but can burn through monthly API quotas in hours. Hard caps prevent runaway costs but make agents give up prematurely.
- **Token accounting is typically post-hoc.** Most teams learn about their token spend from the monthly bill, not from real-time dashboards. By then the damage — or the opportunity — is already realized.
- **Parallel subagents compound the problem.** An orchestrator spawning 8 parallel workers each with a 32K-token context means the ceiling can be hit before any of them complete meaningful work.

## The move

**1. Budget tokens to the task category, not the request.** Classify incoming tasks by expected complexity (quick lookup, multi-source research, complex coding, open-ended investigation) and assign each class a token budget tier. Quick lookups get 2K-token workers; deep research gets 64K-token workers. Anthropic found that for browsing agents, simply distributing work across parallel subagents facilitates the "compression" needed to distill insights — but compression requires tokens to spend.

**2. Budget tokens per subagent, not just per orchestrator.** In an orchestrator-worker pattern, the orchestrator plans and spawns specialist subagents. Each subagent needs its own token allocation. Anthropic's architecture assigns each worker a separate budget so the orchestrator can spawn 4–8 parallel workers without losing control of total spend. The orchestrator itself stays lean; the workers do the heavy lifting.

**3. Use token budget as an architectural signal, not a throttle.** When a subagent exhausts its budget, it does not return "I failed" — it returns the best partial result it found. The orchestrator synthesizes partial results across workers, then decides whether the synthesis is sufficient or a follow-up round is warranted. This is how Anthropic handles research tasks that cannot be pre-scoped: multiple rounds of parallel exploration, each funded by its own budget.

**4. Instrument token spend per tool call, not just per request.** The 80% variance finding came from analyzing BrowseComp trajectories. Teams replicating it found that the signal comes from tracking tokens spent on individual tool calls and their results. A "successful" tool call that returns useless data still consumed tokens. A failed tool call that redirects the agent toward the right approach may be the highest-value spend in the entire trajectory.

**5. Enforce budget as a first-class constraint, not a circuit breaker.** Budget exhaustion should be a planned exit — the agent wraps up, summarizes what it found, and returns a well-formed result with a `budget_exhausted` flag. This is categorically different from hitting an API limit and failing mid-stream. Design the agent's final-step prompt to produce a synthesis when budget signals trigger, so the investment already made is not wasted.

**6. Reserve headroom for synthesis, not just exploration.** A common mistake: agents spend their entire budget on information gathering and have zero tokens left for the actual answer. Reserve a fixed percentage (Anthropic recommends ~15%) of the budget for the final synthesis step. The agent should track cumulative spend and self-regulate — this is the "compression" principle in action.

## Evidence

- **Anthropic Engineering Blog (June 2025):** "Token usage by itself explains 80% of the variance" in BrowseComp performance — more than model choice or number of tool calls. The post describes their orchestrator-worker system where subagents operate in parallel with separate budgets, and the orchestrator synthesizes results across rounds. — [URL](https://www.anthropic.com/engineering/multi-agent-research-system)

- **HN Ask HN "Multi-agent workflows in production" (2026):** Multiple practitioners report that token budget management is the hardest operational problem. One contributor (swrly) describes session state with dual scoping — `agent`-level memory that persists across runs vs. `swirl`-level memory for one run only — specifically to manage memory costs over long conversations. Another (go4horizon) notes their orchestration is "managed by an agent" that self-regulates token allocation. — [URL](https://news.ycombinator.com/item?id=47660705)

- **AI Workflow Lab "Multi-Agent Systems 2026 Guide":** Describes the MCP + A2A protocol combination where the orchestrator uses A2A to delegate to specialist agents and MCP to interact with tools — but notes that without per-agent token budgets, the combined system can exceed expected costs by 10–50x on complex tasks. The guide recommends "token budget per agent" as a core architectural decision. — [URL](https://aiworkflowlab.dev/article/building-multi-agent-ai-systems-2026-architecture-patterns-mcp-production-orchestration)

## Gotchas

- **Token budget and context window are different constraints.** A 128K context window does not mean you should budget 128K tokens. Context is storage; budget is spend. Budget should reflect the expected value of the answer relative to API cost, not the maximum the model can handle.
- **Token efficiency ≠ task success.** An agent that reaches the right answer in 500 tokens is not always better than one that takes 5,000. For hard problems, the lower-token agent may be confidently wrong. Track success rate alongside token efficiency — optimizing cost per token in isolation produces agents that give fast, wrong answers.
- **Per-request budgets fail for multi-turn conversations.** If a user has an ongoing conversation across 12 messages, a per-request budget means each message starts fresh — the agent never has enough context to handle complex follow-ups. Budget across the session, not the request.
- **Budget signals in the prompt compete with task signals.** If you tell the agent "you have 2,000 tokens remaining," the model spends cognitive effort on budget management that could go toward the task. Anthropic's approach handles budget enforcement structurally (in the orchestration layer) rather than instructionally (in the prompt).
