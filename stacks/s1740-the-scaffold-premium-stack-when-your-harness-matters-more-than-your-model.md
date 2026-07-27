# S-1740 · The Scaffold Premium Stack — When Your Harness Matters More Than Your Model

You benchmark Claude Opus 4.7 at 87.6% on SWE-bench Verified and write the number into your procurement deck. Three months later your team ships the same model and it scores 67%. Nobody changed the model. Nobody changed the benchmark. Only the agent scaffold around the model changed — and that difference was worth 20+ points. The scaffold, not the model, is what decides what AI can actually do.

## Forces

- **Published benchmark scores are scaffold scores, not model scores.** Every leaderboard headline conceals the harness configuration it was run under. GAIA bare-model leader scores 44.8%; the same model under the HAL scaffold scores 74.6% — a 30-point gap from scaffolding alone.
- **The scaffold gap dwarfs the model gap.** SWE-bench Pro shows that changing the harness on the same model produces a 22-point swing. Swapping between frontier models with the same harness changes the score by roughly 1 point. Teams optimizing model selection are tuning the wrong variable.
- **Scaffolding quality is invisible until production.** Evaluation harnesses are built to show the model in its best light. Production scaffolds — the actual tool-calling loops, retry logic, context management, and error handlers — are built to be reliable, not to maximize scores.
- **The procurement trap.** Engineering leaders evaluate agents using leaderboard scores, then build their production systems with different harnesses. The model they "selected" performs nothing like the model they evaluated.

## The Move

Stop treating model selection as the primary optimization axis. Treat scaffold design as the engineering variable that moves the needle.

- **Profile before procurement.** Run your own evaluation harness against candidate models using your actual tool definitions, retry logic, and context constraints — not the leaderboard harness. This is the only number that matters for your system.
- **Design the harness as a first-class artifact.** Tool-calling schemas, retry policies, context window management, and structured output formats are not implementation details. They are the performance boundary of your agent. Treat them with the same rigor as model selection.
- **Use leaderboard scores as sanity bounds, not selection criteria.** A 93% SWE-bench score tells you the ceiling. Your production scaffold tells you your floor. The gap between them is where you spend engineering effort.
- **Benchmark the scaffold independently.** Isolate harness changes from model changes in your eval runs. When you improve your tool-calling loop and scores go up, attribute the improvement to the scaffold, not the model.
- **Apply the 1-point heuristic.** If you're evaluating a model upgrade, expect at most ~1 point of benchmark movement under your existing harness. If you need more than that, improve the harness first.
- **Instrument the full tool-use loop.** Scaffolding improvements that reduce tool-call failure rates, shorten context, and improve retry behavior compound across every step the agent takes. These compounding gains dwarf single-model upgrades.

## Evidence

- **Benchmark Analysis:** On SWE-bench Pro, changing the harness produces 22+ point swings with identical model weights. Swapping between frontier models changes scores by roughly 1 point under the same harness — confirming scaffold quality outweighs model selection as an engineering lever. — [Agent MarketCap / SWE-bench analysis](https://agentmarketcap.ai/blog/2026/04/07/agent-scaffolding-premium-swe-bench-harness-quality), April 2026
- **Production Benchmark Gap:** GAIA benchmark shows bare-model leader at 44.8% (GPT-5 Mini) vs. same model under HAL scaffold at 74.6% (Claude Sonnet 4.5) — a ~30 point gap attributable to harness design. Scaffold leaders also outperform bare-model leaders on WebArena (74.3% vs 68.7%). — [Codersera AI Benchmark Roundup, May 2026](https://codersera.com/blog/ai-agent-benchmarks-state-of-leaderboard-may-2026/)
- **Scaffold-to-Production Divergence:** Particula.tech documented a SWE-bench swing from 42% to 78% on the same model achieved purely through harness improvements — a 36-point delta from scaffolding alone. — [Particula.tech / Agent Scaffolding Beats Model Upgrades](https://particula.tech/blog/agent-scaffolding-beats-model-upgrades-swe-bench), 2026

## Gotchas

- **Comparing published leaderboard scores across organizations is comparing different systems.** Each score embeds a specific harness configuration that is not disclosed. A model scoring 5 points higher on a public leaderboard may score 15 points lower under your production harness.
- **Harness improvements are brittle if not instrumented.** Without isolated eval runs that control for model changes, you cannot tell whether performance gains came from the scaffold or from a model update. Build eval infrastructure that separates these variables from day one.
- **The scaffold premium evaporates if your tools are unreliable.** A perfect harness around a flaky tool API produces an agent that confidently calls broken tools at scale. Scaffold quality and tool reliability are co-dependent — invest in both.
