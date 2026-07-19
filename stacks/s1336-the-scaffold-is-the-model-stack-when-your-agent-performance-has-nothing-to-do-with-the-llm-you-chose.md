# S-1336 · The Scaffold-Is-the-Model Stack — When Your Agent Performance Has Nothing to Do with the LLM You Chose

You spent two weeks evaluating GPT-4o versus Claude Sonnet versus Gemini 2.5. You picked the winner, shipped it, and your agent still fails 35% of the time in production. The problem is not the model. The problem is the scaffold — the reasoning backbone, the tool-calling loop, the memory architecture around it. An 11-15 point performance spread exists for the same model across different scaffolds. Most teams never measure it.

## Forces

- **Scaffold choice is invisible in leaderboard benchmarks.** Every public benchmark ranks models, not scaffolds. But when AlphaEval evaluated the same model (Claude Code + Opus 4.6) across different scaffolding architectures, the spread dwarfed inter-model differences. The research-production gap is not primarily a model gap — it's a scaffold gap.
- **Scaffold selection is a one-time decision made casually.** Teams spend weeks on model selection and hours on the agent loop. The ratio is inverted. The scaffold determines how many tool calls the agent makes, how it handles errors, whether it replans, and how it uses memory — all of which dominate cost and reliability in production.
- **Different scaffolds fail in different ways you must be willing to live with.** ReAct wastes tokens on long chains. ReWOO breaks silently on unexpected tool responses. Plan-and-Execute is rigid. Reflexion is expensive. There is no universally best scaffold — only the one whose failure mode your use case can survive.
- **Evaluating a scaffold means evaluating a distribution, not a mean.** An agent that succeeds 60% of the time on a single run but degrades to 25% consistency over 8 runs is not a 60% agent. The scaffold controls consistency as much as peak performance.

## The move

Treat the scaffold as your primary evaluation variable, not the model.

- **Run scaffold comparisons before model comparisons.** Test ReAct, Plan-and-Execute, ReWOO, and Reflexion (or equivalent patterns in your framework) on your actual task distribution with the same base model. The winner will surprise you. AlphaEval found scaffold-driven spreads of 11-15 points — larger than most inter-model deltas you will encounter.
- **Measure consistency, not just accuracy.** Run each scaffold configuration 5-10 times on the same test cases. Track both the pass rate and the variance. A scaffold with 70% mean but 65% consistency across runs is worse than 65% mean with 90% consistency for most production use cases. The CLEAR framework formalizes this as the Reliability dimension (drops from 60% single-run to 25% across 8 runs are common — identify your threshold).
- **Pick the scaffold by its documented failure mode.** Do not optimize for best-case performance; optimize for acceptable-worst-case behavior:
  - ReAct: exploratory tasks, unknown tool schemas, debugging — pays in token cost
  - Plan-and-Execute: well-defined task chains, audit requirements — pays in rigidity
  - ReWOO: parallel tool calls, known tool reliability — pays in brittleness on surprises
  - Reflexion: self-correctable tasks (coding, writing, analysis) — pays in compute cost per attempt
  - ReflAct or goal-state variants: environments requiring persistent belief tracking — pays in added reasoning overhead
- **Pin your scaffold to a specific task class, not the whole agent.** A single agent may need different scaffolds for different tool types. Strands Agents' evaluation framework treats tool-call fidelity separately from trajectory quality for exactly this reason.
- **Regression-test the scaffold, not just the model.** When you change the model, re-run the scaffold comparison. The same model can perform differently under a scaffold that was tuned for its predecessor. Build scaffold evaluation into your CI pipeline alongside model eval.
- **Use CLEAR dimensions to structure scaffold comparison.** Cost (token spend per task), Latency (time-to-completion), Efficiency (tool calls per successful run), Assurance (safety/policy compliance), Reliability (consistency across runs). A scaffold that scores well on accuracy but poorly on cost or reliability is a production liability.

## Evidence

- **AlphaEval production-grounded benchmark (arXiv:2604.12162, April 2026):** Evaluated agent configurations across 94 real-world tasks sourced from 7 companies across 6 O\*NET occupational domains. Best configuration (Claude Code + Opus 4.6) achieves only 64.41/100 — and scaffold choice produces an 11-15 point spread for the same model, exceeding most inter-model differences. Key finding: "scaffold matters as much as model." — [https://arxiv.org/abs/2604.12162](https://arxiv.org/abs/2604.12162)
- **Agent K experiential learning framework (alphaXiv, November 2024):** Agent K consistently outperformed ReAct-style agents across all evaluated baselines on Kaggle data science tasks, earning 4 gold and 4 silver medals in official competitions. Demonstrates that scaffold-architecture improvements dwarf model-upgrade gains in domain-specific agent tasks. — [https://www.alphaxiv.org/overview/2411.03562](https://www.alphaxiv.org/overview/2411.03562)
- **ReflAct paper (arXiv:2505.15182):** Analysis of ReAct found that reasoning steps become ungrounded and misaligned with the agent's actual state, causing compounding errors. ReflAct's goal-state reflection mechanism dramatically improves strategic reliability — showing scaffold-level changes can eliminate entire failure mode families that model upgrades cannot fix. — [https://arxiv.org/abs/2505.15182](https://arxiv.org/abs/2505.15182)
- **CLEAR framework analysis (arXiv:2511.14136, November 2025):** Surveyed 120 agent evaluation frameworks and analyzed 12 major benchmarks. Identified that reliability assessment is systematically absent: agent performance drops from ~60% (single run) to ~25% consistency across 8 runs on the same tasks. Current benchmarks evaluate none of CLEAR's five dimensions — creating a 37% gap between lab results and production deployment. — [https://arxiv.org/abs/2511.14136](https://arxiv.org/abs/2511.14136)

## Gotchas

- **Benchmark leaderboards do not test scaffolds.** Public benchmarks (SWE-bench, WebArena, GAIA) evaluate model capability under a fixed scaffold. They tell you what a model can do in the benchmark's scaffold — not what your scaffold will extract from any given model. Always run your own scaffold comparison on representative tasks.
- **Changing the model can invalidate your scaffold tuning.** Scaffolds are often tuned to a model's token pattern, tool-call style, and reasoning strengths. Swapping the model without re-running scaffold comparisons is a common source of silent regression.
- **Scaffold diversity creates maintenance burden.** Each scaffold variant in your codebase is a code path that needs its own test coverage, error handling, and monitoring. The ROI of scaffold exploration must be weighed against the operational complexity of supporting multiple scaffolds.
- **"Best scaffold" is task-distribution-dependent.** A scaffold that excels at exploratory web browsing will underperform on structured API calls. Do not generalize scaffold rankings across task types — segment your test cases by task class and match scaffolds accordingly.
