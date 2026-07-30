# S-1874 · The Orchestration Pattern Selection Stack — When Your Multi-Agent System Could Go Many Ways

You need a multi-agent system. You know that much. But do your agents need a fixed chain, parallel branches, a supervisor, or a self-correcting loop? Every architecture blog gives you four options and a decision tree that ends in "it depends." The benchmark data now exists. Use it.

## Forces

- **Sequential pipelines are cheap and predictable but accumulate context and error.** Each agent passes its full output to the next, so token costs and latency grow linearly. Errors propagate forward with no backtracking.
- **Parallel fan-out is fast but coordination-heavy.** Independent agents work simultaneously — great for latency, painful when their outputs need coherent synthesis. Merge failures are a common source of silent quality drops.
- **Hierarchical supervisors are flexible but introduce a bottleneck.** One agent decomposes tasks and routes to specialists. Powerful for complex domains, but the supervisor becomes the critical path and a single point of failure.
- **Reflexive loops are the most accurate but cost 2.3× sequential baseline.** Self-correction via internal reflection wins on quality for complex extraction tasks — at a price that only makes sense when the cost of error is high.
- **Princeton NLP found single agents match or beat multi-agent on 64% of benchmarked tasks.** Multi-agent adds ~2.1 percentage points of accuracy at roughly double the cost. The burden of proof for multi-agent is high — you need a real reason, not a vibe.
- **Gartner reports 40% of multi-agent pilots fail within six months of production deployment** — most from picking the wrong pattern or misunderstanding how it breaks, not from agent capability issues.

## The move

Match your orchestration pattern to the cost-sensitivity of your task, the independence of subtasks, and the consequence of error. The arXiv benchmark (Kulkarni & Kulkarni, March 2026) on 10,000 SEC filings across 500 configurations gives you actual numbers to anchor the decision:

- **Use sequential pipeline** when: tasks are a fixed chain of steps, volume is high (>75K docs/day), cost discipline matters more than marginal accuracy gains. Baseline F1 ~0.87 at 1.0× cost. Latency is O(n) with agent count — predictable, budgetable.
- **Use parallel fan-out with merge** when: subtasks are independent, latency is the constraint, and merging logic is well-specified. Fan-out reduces wall-clock time but requires robust merge logic. Tokens explode if merge prompt context grows unbounded.
- **Use hierarchical supervisor** when: tasks are complex, domain-specialized, and benefit from a coordinator that can route flexibly. Occupies the best Pareto position for cost-accuracy: F1 0.921 at 1.4× baseline cost (SEC filing benchmark). Supervisor must be a capable model — it carries the most reasoning load.
- **Use reflexive self-correcting** when: accuracy is paramount and error cost exceeds compute cost. Highest F1 (0.943) but at 2.3× baseline cost. Best for high-stakes extraction, compliance, legal review. Not viable as a default.
- **Default to single agent** until proven otherwise. If one LLM call with good retrieval and in-context examples solves it, do that first. Anthropic's engineering guidance is explicit: "Start simple, only add complexity when needed."

For hybrid needs: the benchmark shows combined hierarchical configurations recover 89% of reflexive accuracy gains at only 1.15× baseline cost. That's the practical sweet spot for most production systems.

## Evidence

- **arXiv benchmark (10K SEC filings, 500 configs):** Sequential pipeline = F1 0.87 at 1.0× cost; hierarchical supervisor = F1 0.921 at 1.4× cost; reflexive = F1 0.943 at 2.3× cost. Fan-out occupies middle ground depending on merge complexity. — [arXiv:2603.22651](https://arxiv.org/html/2603.22651v1)
- **HockeyStack production experience:** Splitting single generalist-agent calls into smaller, narrowly-scoped agent calls improved latency from >30s to <5s per task, cut cost by half, and made failures granular and debuggable. The initial assumption that "fewer API calls = better" was empirically wrong. — [HockeyStack Applied AI](https://www.hockeystack.com/applied-ai/optimizing-latency-and-cost-in-multi-agent-systems)
- **Anthropic engineering guidance:** Multi-agent research system uses orchestrator-worker pattern for parallelism, with lead agent decomposing tasks and subagents operating concurrently. Core insight: "The essence of search is compression — subagents facilitate compression by operating in parallel with their own search tool calls." — [Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)
- **GitHub Blog on multi-agent failure modes:** "Most multi-agent workflow failures come down to missing structure, not model capability." Agents make implicit assumptions about state, ordering, and validation. Explicit interfaces and structured coordination prevent more failures than better prompts. — [GitHub Blog](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/)
- **HN discussion (multi-agent in daily workflow):** "The biggest underappreciated problem is state coordination. Frameworks handle individual agent capabilities well. What they don't handle: preventing two agents from silently overwriting each other's work on shared state. It's a classic race condition but in AI systems the output looks reasonable, so you don't notice it until production." — [Hacker News](https://news.ycombinator.com/item?id=47270020)

## Gotchas

- **Picking a pattern is not a one-time decision.** Teams evolve from sequential (safe, cheap) toward hierarchical or reflexive as cost tolerances and accuracy requirements become clear. Start cheap, upgrade surgically.
- **Context accumulation kills sequential pipelines.** Each agent in a chain receives all prior output. At 5+ agents, you are burning tokens and risking truncation. If your chain exceeds 3 steps, consider parallel fan-out or a supervisor with selective context passing.
- **Fan-out merge is the hidden failure point.** Parallel branches are easy to parallelize; coherent merging is hard. Invest in merge logic before shipping parallel agents — it's where quality silently degrades.
- **Supervisor is the bottleneck and the blast radius.** A weak supervisor infects the entire system. Budget for the best model in the coordinator role, not the workers.
- **Multi-agent observability is non-negotiable in production.** When 5 agents contribute to a cascading failure, you need distributed tracing per agent — not just a final output log. This is where frameworks (LangGraph, AutoGen) add real value: structured state management and trace visualization, not agent capability.
