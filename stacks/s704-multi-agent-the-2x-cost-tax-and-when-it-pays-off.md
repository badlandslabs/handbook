# S-704 · Multi-Agent: The 2× Cost Tax and When It Pays Off

[Your single-agent pipeline is getting unreliable. The context window is filling up. Adding a second agent feels like the right move — more specialization, cleaner outputs. Three weeks later your costs are double, latency is up 40%, and a task that used to work in one agent now fails because two agents are arguing about who owns the schema.]

## Forces

- **Multi-agent adds cost linearly but accuracy non-linearly.** The median multi-agent setup costs ~2× a comparable single-agent system but only gains +2.1 percentage points of accuracy on benchmarked tasks. Teams budget for capability, not cost.
- **The orchestration pattern is the critical variable.** Picking the wrong coordination strategy doesn't just slow you down — it creates failure modes that look like agent bugs but are actually architectural mistakes. 40% of multi-agent pilots fail within 6 months.
- **Single agent wins most of the time.** Princeton NLP benchmarks found single agents matching or outperforming multi-agent setups in 64% of tasks. The burden of proof should be on multi-agent, not single-agent.
- **Long context kills single agents.** When critical information gets buried in long contexts, model reasoning degrades by up to 73%. This is the honest case for splitting: not "more agents = better" but "shorter contexts = reliable."

## The move

**Split agents when context length is the primary failure mode — not when the task is complex.**

- **Use Orchestrator-Worker** when a central agent must decompose tasks and delegate to specialists: "Here is the research query. You two go find relevant contracts. Return a merged summary." Works for parallelizable work with known output schemas.
- **Use Supervisor (single-agent router)** when classification drives routing: "Classify this ticket, then hand off to the right agent." One agent decides, others execute. Lowest overhead of any multi-agent pattern.
- **Use Hierarchical** (Director → Manager → Worker) only when you have genuine chain-of-command delegation and need accountability trails. Most teams don't need this; CrewAI's 6-agent marketing team is the canonical over-engineered example.
- **Never use Consensus or Auction** for latency-sensitive production flows — they require multiple agent turns to reach agreement, multiplying cost and failure surface.
- **Cost-gate at the architecture level.** Before splitting, compute: (Model price × avg steps/run × tokens/step × monthly volume). Multi-agent with 2 specialist agents at 12K runs/month easily reaches $500–2,000/month in LLM API costs alone, before infrastructure.
- **Instrument steps-per-run per agent** from day one. System A (LangGraph, 3 tools, 2.4 avg steps) vs. System D (multi-agent, 8.1 avg steps) is a 3.4× difference in cost that won't show up in output quality.

## Evidence

- **Benchmark:** Princeton NLP found single agents match/m outperform multi-agent in 64% of benchmarked tasks; multi-agent gains +2.1 percentage points accuracy at ~2× cost — [beam.ai orchestration analysis](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production) citing Gartner 1,445% inquiry surge (Q1 2024 → Q2 2025)
- **Production cost data:** 6-month tracked deployment across 4 systems: LLM API = 60–80% of total operating cost; cost formula = Model Price × Steps/Run × Tokens/Step × Volume; single LangGraph agent (3 tools, 2.4 steps/run) vs. multi-agent (8.1 steps/run) — [Inventiple production cost analysis](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis), April 2026
- **Tool bloat kills single agents:** Shopify Sidekick's tool count grew until a single agent couldn't reliably select the right one — agent routing (which agent handles which tools) became a core architectural problem — [Shopify Engineering / Sidekick](https://shopify.engineering/building-production-ready-agentic-systems), August 2025
- **Why teams still split:** Long-context degradation is the legitimate trigger; buried guardrails start failing, persona bleed causes hallucinations, 73% reasoning degradation in long contexts — [Comet multi-agent systems analysis](https://www.comet.com/site/blog/multi-agent-systems/), January 2026

## Gotchas

- **Mixing frameworks adds coordination debt.** HN thread on multi-agent in production: teams running LangGraph for one agent, CrewAI for another, and a custom Python agent for a third — the coordination surface between them (schema mismatches, auth propagation, shared state) becomes the real engineering problem.
- **Orchestrator-Worker is the safest default.** If you're unsure which pattern to use, start here. It has the clearest failure mode (the orchestrator picks wrong) and the easiest to debug.
- **Flow-first with CrewAI** doesn't mean you need many agents. Wrap a single agent in a Flow for state management — you can add agents later without architectural rewrite.
- **Guardrails don't survive handoff.** Safety constraints set on the orchestrator get lost when a worker agent continues the conversation. Every handoff point needs its own constraint layer.
