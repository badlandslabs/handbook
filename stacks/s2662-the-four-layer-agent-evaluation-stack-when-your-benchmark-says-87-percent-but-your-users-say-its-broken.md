# S-2662 · The Four-Layer Agent Evaluation Stack — When Your Benchmark Says 87% But Your Users Say It's Broken

Your agent scores 87% on your eval harness. You ship it. Users report it fails on the third turn of every multi-step task, hallucinates tool calls it didn't need to make, and costs 50× more per completed task than your budget assumed. Your benchmark told you it was ready. It wasn't. The methods you inherited from LLM evaluation — single-turn accuracy on curated datasets — don't capture what matters when an autonomous system makes multi-step decisions in production.

## Forces

- **Benchmarks certify capability, not reliability.** Standard agent benchmarks measure whether a task *can* be completed. They don't measure whether it completes it *consistently*, *cheaply*, or *safely* across production distributions.
- **Agent behavior drifts with model version.** OpenAI's own research showed GPT-4's behavior measurably changed across versions — tasks at 97% accuracy in March 2023 dropped to 87% by June 2023 on the same benchmark (Chen et al., 2023). Your eval is stale the day a new model version ships.
- **The distribution of production failures is heavy-tailed and path-dependent.** You can't anticipate it from imagination alone. The most predictive regression dataset comes from capturing what actually broke in production.
- **Multi-agent interactions introduce variance that single-agent eval frameworks miss.** An evaluator that checks each agent independently will miss the coordination failures that only emerge at runtime.

## The Move

The production-ready evaluation stack operates across four layers, each catching different failure categories:

1. **Capability Benchmarks (Pre-Deployment).** Use standardized benchmarks (ToolBench, API-Bank, GAIA, MINT-Bench) to establish a floor before any custom work. These catch regressions in core tool-use ability. Run on every model upgrade or significant prompt change.

2. **Simulation-Based Eval (Staging).** Run agents through synthetic scenarios that approximate production distributions — adversarial inputs, rate-limit conditions, tool timeout chains. Tools like Coval (YC W25) use autonomous-vehicle-inspired simulation to stress-test multi-step workflows. This is where you catch the "agent loops 40 times" failure before users do.

3. **Trace-Level Observability (Staging + Production).** Instrument every agent run with structured traces — tool calls, latencies, token consumption, intermediate outputs. LangSmith (LangChain), Arize Phoenix, and similar platforms provide span-level tracing with LLM-as-judge scoring. LangSmith processes traces from 400+ companies in production as of 2025.

4. **Production Failure Capture (Continuous).** Capture every production failure as a regression test case automatically. The highest-value eval dataset is not hand-crafted — it accumulates from what breaks in the field. This closes the gap between staging and production distributions.

**Core principle from Anthropic's engineering team:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Evaluation should mirror this — layer it, but don't over-engineer it. Start at layer 1, add layers based on demonstrated gaps.

**Cost and latency matter as first-class metrics.** A task-completion eval that ignores token budget and latency is a misleading signal. A 99%-accurate agent that costs $4/task and takes 3 minutes is often worse than a 94%-accurate agent at $0.20/20 seconds.

## Evidence

- **arXiv 2507.21504:** "Evaluation and Benchmarking of LLM Agents: A Survey" (July 2025) — provides the two-dimensional taxonomy: what to evaluate (agent behavior, capabilities, reliability, safety) vs. how to evaluate (metrics, methods, tooling, context). Maps evaluation tooling across LangSmith, Arize Phoenix, and public leaderboards. — [https://arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)

- **Anthropic Engineering — "Building Effective AI Agents":** Documents the spectrum from single augmented LLM call (1× cost, 1–5s latency) to autonomous agent (10–50× cost, 30s–5min latency). Recommends starting simple and escalating based on eval results, not architectural preference. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **Ask HN thread (112 pts, 73 comments, Dec 2024):** Real practitioners reported agent eval as the hardest unsolved problem. Key insight from HN user simonw: benchmark scores and production quality are weakly correlated, and "90% of what people call agentic is just a for-loop." — [https://news.ycombinator.com/item?id=42431361](https://news.ycombinator.com/item?id=42431361)

- **Gartner (via thinking.inc):** Projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps. — [https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production)

- **GitHub — SimplerSoftwareIO/seo-ai-agent:** Real-world agent with persistent SQLite memory, multiple tool integrations (Google Search Console, GA4, DataForSEO, FireCrawl), MCP server for VS Code/Copilot integration, and a Streamlit dashboard. Demonstrates evaluation in the wild: the agent is tested against actual search data, not synthetic benchmarks. — [https://github.com/SimplerSoftwareIO/seo-ai-agent](https://github.com/SimplerSoftwareIO/seo-ai-agent)

## Gotchas

- **Human-ln-the-loop eval doesn't scale.** Having humans score every agent output is necessary for ground truth but collapses past ~100 cases. Use LLM-as-judge for rapid scoring, but validate it against human labels periodically — LLMs are over-generous graders on tasks they helped design.
- **Success-rate metrics hide latency and cost variance.** An agent that completes 95% of tasks but takes 10× longer and costs 8× more than expected is a production incident waiting to happen. Track task-completion rate *and* cost-per-task *and* p95 latency together.
- **Eval data rots.** Model updates, API changes, and upstream data drift all shift agent behavior. Re-run your eval suite against the new environment, not just the new model version. Treat eval as a continuous pipeline, not a gate.
- **Multi-agent eval is non-linear.** Two agents that each pass their unit tests can fail together due to coordination errors — message format mismatches, race conditions, cascading timeout loops. Test agent interactions explicitly, not just individual agent behavior.
