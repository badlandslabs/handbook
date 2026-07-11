# S-940 · The Orchestration Pattern Stack — When Your Agent Loop Structure Determines Everything

You chose LangGraph because it felt enterprise-grade. Your agent works. Then someone benchmarks it against a ReAct loop on a simple FAQ task: same model, 3× the tokens, 2× the latency, identical output. You over-engineered the orchestration for a problem that didn't need it. But flip the scenario — that same ReAct agent hits a 20-step compliance workflow and it hallucinates a mid-sequence step and nobody catches it until the report is wrong. The orchestration pattern isn't a style preference. It's the architecture that determines cost, latency, correctness, and failure modes for every task your agent touches.

## Forces

- **Simple tasks penalize sophisticated loops.** ReAct loops cost tokens on every step. Plan-and-Execute pays a planning overhead upfront. Reflexion pays a reflection overhead per step. A FAQ bot that could answer in one call gets 8 tool-call turns because that's what the orchestration demands. MH TechIn (2026) benchmarked CrewAI at 3× more tokens and latency than simpler patterns on simple tasks.
- **Complex tasks reward structured reasoning but punish naive loops.** An agent processing a 20-step compliance workflow with ReAct accumulates hallucination risk at every turn. By step 15, it may act on a mid-sequence assumption that was never verified. Tree of Thoughts or Reflexion catches this — but they cost more on simple paths.
- **Framework choice locks the orchestration pattern.** LangGraph exposes state machines and lets you pick ReAct or Plan-and-Execute per agent. CrewAI defaults to role-based collaborative loops. AutoGen defaults to multi-agent conversation patterns. Switching frameworks mid-architecture means reimplementing your reasoning loops.
- **Token budget and latency are architecture decisions.** A ReAct agent on a 200K-token context window burns tokens twice per step (reason + act) in every turn. On long workflows this compounds to 10× the cost of a Plan-and-Execute that commits to a full plan upfront.

## The move

Match the orchestration pattern to the task complexity profile — don't default to the most sophisticated one.

**Layer 1 — Pattern selection by task type:**

- **ReAct (Reason + Act):** Default for tool-using agents with 1–8 steps and moderate variability. Alternates reasoning ("what should I do next?") with acting (tool call or output). Low overhead per step, predictable token burn. Fails on long chains because hallucinations compound.
- **Plan-and-Execute:** Best for long workflows (8+ steps) with parallelizable sub-tasks. The planner decomposes the full task upfront, then an executor runs steps. High upfront planning cost, lower per-step cost. Wrong plan = wrong execution — needs verifiable subgoals.
- **Reflexion:** Best for tasks with verifiable output (test assertions, schema validation, code generation). After each action, the agent reflects on whether the result is correct and self-corrects. Trades speed for accuracy. Two axes of failure: wrong reflection or right reflection ignored.
- **Tree of Thoughts:** When correctness matters more than cost on combinatorial or search problems. Explores multiple reasoning branches, evaluates each, picks the best. 3–5× token cost vs ReAct. Only worth it when wrong = expensive.
- **Self-Consistency (sampling wrapper):** Run ReAct N times, vote on the most common answer. Effective for numeric and classification tasks. No planning overhead, N× cost. Drop-in improvement.

**Layer 2 — Guard every loop:**

- Always cap max iterations (LangChain: `max_iterations=15`, AutoGen: `max_turns`). Unbounded loops burn tokens until the model halts.
- Detect identical reasoning loops (same observation → same next action in 3 consecutive turns → inject a re-plan prompt or escalate).
- Instrument per-step token cost. If step N costs more than 2× the average of steps 1 through N-1, something is wrong.
- Build a step taxonomy: `planner_step`, `tool_call`, `tool_result`, `reflection`, `re_plan`. This is the granularity you need to debug failure modes.

**Layer 3 — Framework selection:**

| Framework | Default Pattern | Token Efficiency | Production Readiness | Best For |
|-----------|----------------|-------------------|----------------------|----------|
| **LangGraph** | You choose | High | Enterprise-grade | Complex stateful workflows, fine-grained control |
| **CrewAI** | Role-based collaborative | 3× overhead on simple tasks | Growing | Fast prototyping, role-based multi-agent |
| **AutoGen (MAF)** | Multi-agent conversation | Medium | Research-oriented | Multi-agent research, emergent behaviors |

LangGraph leads on production token efficiency and enterprise governance (MH TechIn, 2026). CrewAI wins on prototyping speed. AutoGen excels for research into multi-agent emergent behaviors. The worst outcome is using a framework's default pattern for the wrong task type.

## Evidence

- **Benchmarking post — ReAct vs Plan-and-Execute vs Reflexion decision criteria:** Geodocs.dev's Agent Multi-Step Reasoning Specification (May 2026) maps each pattern's failure modes and cost profiles, with rule-of-thumb guidance: ReAct as default, Plan-and-Execute for long workflows with parallelizable steps, Reflexion for tasks with verifiable outputs, Tree of Thoughts when correctness > cost. — https://geodocs.dev/ai-agents/agent-multi-step-reasoning-spec
- **Framework comparison with token/latency benchmarks:** MH TechIn (2026) benchmarked CrewAI at 3× more tokens and latency than other frameworks on simple tasks, matching on complex scenarios. LangGraph leads on production readiness and enterprise governance. — https://www.mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide
- **Real production incident — Plan-and-Execute vs ReAct tradeoff:** MoltBot Engineering (April 2026) documented a case where a ReAct agent handling a 15-step customer onboarding workflow hallucinated a mid-sequence verification step, producing a compliance report that looked correct until audit. The fix was switching to Plan-and-Execute with explicit subgoal verification between steps. — https://ceooftheuniverse.github.io/vmsaas-live/blog-agent-planning.html

## Gotchas

- **Don't default to Plan-and-Execute.** The upfront planning cost pays off only on 8+ step tasks with parallelizable sub-steps. For simple tasks, it's pure overhead.
- **Framework defaults are not task defaults.** CrewAI defaults to role-based collaborative loops. If your task is a single-agent tool caller, that overhead is unnecessary. Configure per-agent pattern, not per-framework.
- **Reflexion failures are harder to detect than ReAct failures.** A ReAct loop that goes wrong produces a visible bad action. A Reflexion loop that reflects incorrectly produces a confident wrong answer that looks like success. Build output validators (schema checks, test assertions) for every Reflexion agent.
- **Loop detection is not the same as loop prevention.** Capping iterations catches runaway loops but doesn't prevent wasted tokens on suboptimal paths. You need both: per-turn identical-action detection AND an iteration cap.
