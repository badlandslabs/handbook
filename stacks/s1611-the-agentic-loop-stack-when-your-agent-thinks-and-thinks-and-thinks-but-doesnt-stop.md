# S-1611 · The Agentic Loop Stack — When Your Agent Thinks and Thinks and Thinks but Doesn't Stop

Your agent started working on a customer support ticket. Three minutes later it has made 47 tool calls, burned $18 in tokens, and sent three contradictory emails. It is looping — not failing visibly, just iterating past the point of usefulness. The agentic loop is the engine that makes agents powerful. It is also the mechanism that makes them expensive, unpredictable, and occasionally catastrophic when the stopping condition is wrong.

## Forces

- **The loop gives agents power but demands a governor.** Without an explicit stop condition, the loop runs until a hard `T_max` fires — by which point cost and context are exhausted.
- **Different loop patterns suit different task shapes.** ReAct interleaves thought and action for interactive tasks. Plan-and-Execute separates planning from execution for complex, multi-step work. Reflection adds self-critique for quality-sensitive outputs. The wrong pattern on the wrong task multiplies both cost and failure rate.
- **Context growth is quadratic in loop depth.** Every step appends a thought, an action, and an observation to the context. After k steps: O(k·s) tokens. Long loops silently degrade model attention on the middle steps — the "lost in the middle" problem — making later steps worse than earlier ones.
- **The Anthropic finding cuts against the hype.** Princeton NLP found a single agent matches or outperforms multi-agent systems on **64% of benchmarked tasks** with the same tools and context. Multi-agent adds ~2.1 percentage points of accuracy at roughly double the cost. The loop pattern matters more than adding agents.

## The Move

Pick the loop pattern that matches your task's shape, then add the three mandatory governors.

### Pattern Selection

- **ReAct (think → act → observe → repeat):** Best for interactive, stateful tasks where each step's output informs the next. Customer support bots, code agents, order-lookup → decision chains. Single agent, tight loop, small search tree.
- **Plan-and-Execute (plan first → execute steps):** Best for complex, multi-step tasks with known subgoals. Research pipelines, contract review, trip planning. High upfront planning cost, but execution is fast and auditable.
- **Reflection (act → critique → revise → repeat):** Best for quality-sensitive outputs where a first draft is not enough. Writing, analysis, code review. Add a second agent or a structured critique step after each major output.

### The Three Mandatory Governors

1. **Hard step limit (`T_max`).** Set a maximum iteration count before the loop starts. Default to 20–50 depending on task complexity. When `T_max` fires, return what you have and log a "loop terminated" signal — not a silent failure.
2. **Cost budget per run.** Track cumulative token cost in the loop state. Halt if cost exceeds a per-task threshold ($0.50 for simple tasks, $5 for complex). This is the only governor that fires before the token counter does.
3. **Context headroom check.** Before each step, measure remaining context window. If less than 20% headroom remains, either compress the conversation history (see S-1000: context exhaustion) or terminate with state preserved for human review.

## Evidence

- **Engineering blog:** Anthropic's "Building Effective AI Agents" — recommends simple, composable loop patterns over complex frameworks, and explicitly advises starting with the simplest possible solution and adding complexity only when evidence demands it. Cross-referenced by 88 HN comments discussing production failures. — https://www.anthropic.com/engineering/building-effective-agents
- **HN Ask thread:** "How are you orchestrating multi-agent AI workflows in production?" (543 points) — respondents building custom loop control with Node.js/Express, LangGraph, and SQLite-structured state; the consensus is that off-the-shelf frameworks handle orchestration topology but not loop governance. — https://news.ycombinator.com/item?id=44301809
- **Research paper / community guide:** "The Agentic Loop: ReAct, Plan-Execute & Reflection" from the LLM Stack book (2026) — documents the three canonical patterns with Python skeletons, shows context growth as O(k·s), and explicitly calls out that wrong early actions create error propagation that compounds through subsequent steps. — https://prakashkagitha.github.io/llm-stack-book/08-agents-harness/02-agentic-loop.html

## Gotchas

- **ReAct's thought/action separation is not free.** Adding `Thought:` lines to context costs tokens without contributing to the task. For simple, single-step tasks, skip the loop entirely.
- **Plan-and-Execute re-plans on every failure.** If a step fails, the executor must decide: retry, skip, or replan. Naive replanning restarts the whole plan. Add a recovery policy before deploying.
- **Reflection loops can oscillate.** An agent critiques its own output, revises, critiques again, and may oscillate between two states without converging. Set a reflection budget (e.g., max 2 critique cycles) to prevent infinite revision.
- **Loop telemetry is not optional.** Log every step: the thought, the action, the observation, cumulative cost, and context usage. Without this, you cannot reconstruct why the agent did what it did when the output is wrong.
