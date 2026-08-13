# S-2594 · The Three-Loop Stack — Choosing Your Agent Control Pattern

You are about to build an agent and you do not know whether to make it react to each step, plan everything upfront, or let it self-critique. The answer is not "the most powerful pattern" — it is "the pattern that matches how the task actually unfolds." Picking wrong costs latency, burns budget, or produces confident failures. Most teams reach for the most complex option.

## Forces

- **Interactivity vs. structure** — some tasks are deeply interactive (next step depends on previous result), others are structurally predictable (same steps, same tools, just more data)
- **Cost vs. reliability** — ReAct calls the LLM every step. Plan-and-Execute calls it twice. Reflexion calls it three times. Each escalation adds cost but reduces failure risk in different ways
- **Debugging vs. autonomy** — tighter loops (ReAct) are easier to trace step-by-step. Looser loops (Plan-and-Execute) are harder to debug but commit to execution paths faster
- **Overhead vs. flexibility** — some tasks genuinely need a planner overhead; others are better off with a simple loop

## The move

Three control patterns cover 90% of production agent use cases. Pick based on how the task unfolds, not the sophistication of the pattern.

### ReAct — the default, for interactive tasks

Interleave reasoning ("I need to find the order"), acting (calling a tool), and observing (reading the result) in a tight loop. Each step informs the next. Best when the task branches based on what you find — customer support lookups, coding agents, research that depends on earlier findings.

```
Think → Call Tool → Observe → Think → Call Tool → Observe → ...
```

Use when: small search tree, exploration is cheap, next step depends on previous output. A 30-line ReAct loop ships on Tuesday. Most teams should start here.

### Plan-and-Execute — for structured, multi-step pipelines

A capable planner LLM writes a numbered step list upfront. A separate, cheaper executor walks the list. The planner commits once to the order; the executor handles execution. Best for research workflows, multi-document summarization, ETL pipelines, anything where steps are independent and parallelism is possible.

```
Plan (once) → Execute step 1 → Execute step 2 → ... → Assemble result
```

Use when: steps are independent and can run in sequence (or in parallel), you want a smaller/cheaper model for execution, or the task has enough structure that a plan is worth writing. If every step calls the same two tools in the same order, pay for the plan once.

### Reflexion — for quality or safety-critical outputs

After completing a task, the agent generates a self-critique evaluating its own performance. That critique is stored and injected as context on the next attempt. Best for code generation, writing, or any task where a second pass with domain awareness materially improves output quality.

```
Execute → Self-critique (pass/fail + reasoning) → Store reflection → Retry or finish
```

Use when: output quality is measurable or evaluable, failures are costly, or the domain has clear standards the agent can assess against.

## Evidence

- **Survey/analysis:** The agent pattern landscape has consolidated around these three (ReAct, Plan-and-Execute, Reflexion) from academic papers (Yao et al. 2022 for ReAct; Wang et al. 2023 for Plan-and-Solve) plus one emerging fourth pattern. A practitioner analysis notes: "most teams over-engineer — reaching for Tree-of-Thoughts when a 30-line ReAct loop would have shipped on Tuesday." — *DEV Community, "ReAct, Plan-and-Execute, or Reflection? The Three Agent Patterns Every Engineer Needs in 2026"*, Gabriel Anhaia, January 2026 — [URL](https://dev.to/gabrielanhaia/react-plan-and-execute-or-reflection-the-three-agent-patterns-every-engineer-needs-in-2026-355p)
- **Industry analysis:** Multi-agent orchestration research shows 40% of multi-agent pilots fail within six months of production deployment. The failure pattern is not that the technology doesn't work — it is that teams pick the wrong orchestration pattern for their problem. "Organizations use an average of 12 agents, projected to climb 67% within two years." — *beam.ai, "6 Multi-Agent Orchestration Patterns for Production (2026)"*, Fredrik Falk, August 2026 — [URL](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Practitioner report:** A developer who used LangChain agents for a year in production reported hitting walls: "Where I hit walls with LangChain: the abstraction leaked the moment I needed a custom loop or error handling... I rebuilt the architecture from scratch." They now use LangChain only for RAG pipelines, and build custom orchestration for autonomous agents. — *r/LangChain, "Why I stopped using LangChain agents for production autonomous workflows (and what I use instead)"*, Unlikely_Software_32, 6 months ago — [URL](https://www.reddit.com/r/LangChain/comments/1r9dh5m/why_i_stopped_using_langchain_agents_for/)

## Gotchas

- **Tree-of-Thoughts is almost never the right choice** for business workflows. It explores multiple reasoning paths in parallel — expensive and slow. Reserve it for genuinely novel problems with high branching factors.
- **Sequential chains are underrated for stable pipelines.** If the steps are fixed and the data is clean, a simple sequential pipeline is faster, cheaper, and easier to debug than a full agent loop. Not every workflow needs a loop.
- **Pattern mixing is legitimate but watch the cost.** A Plan-and-Execute where each execution step runs its own ReAct loop is valid — but track your token counts. The pattern combination that works is one planner + one executor + ReAct inside executor steps.
- **ReAct's tight coupling makes long tasks fragile.** A failure in step 8 of a 10-step ReAct loop loses the work from steps 1-7 unless you checkpoint state. Plan-and-Execute is more amenable to checkpointing since steps are pre-defined.
