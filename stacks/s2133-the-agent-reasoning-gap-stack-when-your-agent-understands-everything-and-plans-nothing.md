# S-2133 · The Agent Reasoning Gap Stack — When Your Agent Understands Everything and Plans Nothing

Your agent passes every benchmark. It answers questions accurately, uses tools correctly, and references context precisely. Then a user gives it a real goal — "automate our weekly reporting pipeline" — and the agent picks one tool, gets stuck, tries another, drifts from the original intent, and produces something adjacent to what was asked. The problem is not intelligence. The problem is that understanding and planning are different cognitive operations, and most agentic systems invest heavily in the former while leaving the latter to chance.

## Forces

- **Planning is underemphasized in the literature.** Most benchmarks measure tool use accuracy and factual recall. Planning — decomposing a goal into a sequence of sub-goals, checking progress, and replanning on deviation — is harder to measure and therefore harder to improve.
- **LLMs are strong reasoners but weak planners.** A model's ability to chain logic in a single prompt is well-established. Its ability to maintain a goal state across 15 tool calls over 10 minutes, while handling partial failures and changing context, is not.
- **Scope clarity is the highest-leverage input.** Cognition's review of 18 months of Devin in production found the single biggest predictor of success: whether the task had clear, upfront requirements. Agents degrade sharply when requirements emerge mid-execution.
- **Replanning is the failure mode no one tests.** The agent assumes its initial plan is still valid long after conditions have changed. Without explicit checkpoint-and-revise logic, the agent compounds the first wrong assumption into a cascade of wrong actions.

## The Move

The reasoning gap closes at the architecture level, not the prompt level. You need explicit planning infrastructure — not just a system message that says "think step by step."

- **Separate planning from execution.** Build a dedicated planning step that takes the user's goal, decomposes it into an ordered task list, and commits that plan to durable storage before any tool is called. The executor then iterates through the list, not through free-form tool selection.
- **Use reflection as a first-class tool.** After each action, the agent evaluates: did this action bring me closer to my goal? If not, should I revise the plan? Anthropic found that explicit reflection ("examine your last action, did it succeed?") significantly improved completion rates on multi-step tasks.
- **Scope contracts before tool calls.** Before starting, have the agent produce a written scope: what it will do, what it won't do, what success looks like, and what conditions would cause it to ask for clarification. Present this to the user or an approval gate before proceeding.
- **Plan with dependencies, not just sequence.** A task list is not a plan. A plan specifies which tasks depend on others completing first, which can run in parallel, and which are optional. Orrery (a spec-decomposition tool) surfaced this distinction: pure sequencing produces linear chains; dependency-aware planning enables parallel execution and graceful partial completion.
- **Set explicit stop conditions.** Define what "done" looks like before starting, and give the agent a maximum step count. LangChain's planning documentation explicitly calls out bounded stopping rules as a critical failure-mode guard.
- **Store the planning state separately from conversation history.** The plan, its current position, and the revision log should be distinct from the chat log. This lets you inspect what the agent intended versus what it actually did, which is the core diagnostic for planning failures.

## Evidence

- **Anthropic Engineering Blog:** "Building Effective AI Agents" (Dec 2024) — Found that the most successful implementations use simple, composable patterns rather than complex frameworks. Key finding: reflection (explicitly evaluating the success of each action) meaningfully improves multi-step task completion. Recommended distinguishing *workflows* (predefined code paths) from *agents* (LLM-dynamic loops), and starting with the former. — [URL](https://www.anthropic.com/engineering/building-effective-agents)
- **Cognition Blog:** "Devin's 2025 Performance Review: Learnings From 18 Months of Agents At Work" (Nov 2025) — After 18 months in production at thousands of companies (Goldman Sachs, Santander, Nubank), Devin merged hundreds of thousands of PRs. Finding: Devin is senior-level at codebase understanding but junior at execution. Strongest predictor of success: clear upfront scoping. Sharply degrades on mid-task requirement changes. Struggles with soft skills and implicit constraints. — [URL](https://cognition.ai/blog/devin-annual-performance-review-2025)
- **LangChain Blog:** "Planning for Agents" by Harrison Chase (July 2024) — Identified planning as one of three core agent limitations (alongside UX and memory). Documented current approaches: single-step reasoning via CoT, task decomposition into sub-tasks, self-reflection for error correction, and the importance of bounded stopping rules to prevent infinite loops. — [URL](https://www.langchain.com/blog/planning-for-agents)
- **Hacker News Discussion:** Ask HN "How are you scaling AI agents reliably in production?" (2025) — Practitioners using Temporal and LangGraph for state/checkpointing; consensus that explicit plan persistence between steps was critical for debugging and recovery. — [URL](https://news.ycombinator.com/item?id=44909029)

## Gotchas

- **"Think step by step" is not planning.** Chain-of-thought in a single prompt produces reasoning trace, not a persisted plan. The plan must survive across turns and tool calls, which requires explicit state management.
- **The plan becomes obsolete faster than you expect.** API responses change data, downstream dependencies fail, user requirements evolve. An agent that replans only at the start of a session — not after each significant action — will follow a stale plan into failure.
- **More reasoning steps ≠ better reasoning.** Studies on extended thinking show diminishing returns and sometimes worse outcomes past a threshold. Budget reasoning tokens, but also budget for the agent to know when to stop reasoning and start acting.
- **Planning quality is invisible in happy-path testing.** Your eval suite likely tests whether the agent completes the task correctly. It probably doesn't test whether the agent would complete it correctly if a sub-step failed at step 3 of 7. Add adversarial planning tests: remove a tool, add an unexpected constraint, change a requirement mid-execution.
