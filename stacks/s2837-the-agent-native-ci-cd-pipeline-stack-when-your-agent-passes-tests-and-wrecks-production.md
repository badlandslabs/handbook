# S-2837 · The Agent-Native CI/CD Pipeline Stack — When Your Agent Passes Tests and Wrecks Production

When your agent goes green in CI, ships to production, and within 48 hours silently starts hallucinating tool calls: your pipeline tested the wrong thing.

## Forces

- **Agent behavior lives outside code** — prompts, model checkpoints, tool definitions, and retrieval configs change without a version bump or a diff
- **Conventional CI can't catch what it can't see** — lint and unit tests pass because they test code, not capability
- **The eval-observability gap** — 89% of production agent teams run observability, but only 52% run evals; quality silently decays in that 37-point gap
- **Latency is a feature** — an agent that works but takes 4 minutes per task is a different product than one that takes 8 seconds
- **Cost compounds across turns** — a 10-step trajectory costs 10x more than a 1-step trajectory, and most CI never measures it

## The Move

Build a tiered evaluation pipeline that gates on behavior, not just code. The pipeline has three tiers, each with a different cost, latency, and risk profile:

### Tier 1 — PR Gate (minutes, deterministic, cheap)
- Run on every pull request. Must complete in under 5 minutes.
- Replay committed agent trajectories from `.agentrun.json` files — deterministic replay of prior runs
- Check tool-call schema compliance, retrieval hit rates, and happy-path completion
- Block the PR if any critical path fails. This is not optional.
- Framework: use `pytest --ac-replay` or `agent-regression-canary` YAML task definitions

### Tier 2 — Nightly Gate (hours, LLM-as-judge, moderate cost)
- Run on a nightly schedule against a golden dataset of 50–200 representative tasks
- Use LLM-as-judge to score task completion, reasoning coherence, and tool selection
- Calibrate judge prompts against human labels targeting ≥0.80 Spearman correlation
- Track cost-per-task and latency-per-task as first-class metrics; alert on >20% drift from baseline
- Tools: DeepEval, LangChain AgentEvals, or the trajectory evaluation layer in agent-eval-harness

### Tier 3 — Canary with Auto-Rollback (production, shadow mode)
- Route 5–10% of production traffic through the new agent version in shadow mode
- Compare trajectory distributions: tool call frequency, error rates, cost, and latency
- Auto-rollback if error rate exceeds baseline by >2σ or cost-per-task exceeds budget
- Capture production traces and add novel failure patterns back to the golden dataset

### Longitudinal Guard (weeks, trend analysis)
- Track capability drift over time: pass rates on golden dataset tasks plotted week-over-week
- A downward trend of >5% over 4 weeks signals silent degradation even if absolute scores look acceptable
- Version-control every component that affects behavior: prompt files, tool definitions, retrieval configs, model endpoint — commit with hash, enable git-bisect diagnosis

## Evidence

- **Engineering Blog — RockB (June 2026):** 5 eval gates that don't exist in traditional pipelines — golden dataset offline eval, regression blocks, cost gates, shadow evaluation, canary auto-rollback. Notes that 89% of production agent teams run observability but only 52% run evals. — [baeseokjae.github.io/posts/agent-ci-cd-eval-pipeline-integration-guide-2026](https://baeseokjae.github.io/posts/agent-ci-cd-eval-pipeline-integration-guide-2026)

- **Research Post — Zylos Research (April 2026):** Regression suite organized across 4 categories (happy-path 99%+, edge cases 95%+, adversarial stable refusal rate, off-topic consistent handling). Version-controlling prompts and tool definitions with committed hashes enables git-bisect-style diagnosis when regressions appear. — [zylos.ai/en/research/2026-04-14-ai-agent-longitudinal-evaluation-production-regression](https://zylos.ai/en/research/2026-04-14-ai-agent-longitudinal-evaluation-production-regression)

- **GitHub — reaatech/agent-eval-harness:** Production-ready TypeScript evaluation harness with trajectory evaluation (coherence, goal completion, conversation flow), tool-use validation across 13+ issue types, cost tracking for 8 LLM models with budget enforcement, latency budgets, golden trajectory comparison, and CI/CD regression gates. — [github.com/reaatech/agent-eval-harness](https://github.com/reaatech/agent-eval-harness)

- **GitHub — phoenix-assistant/agent-regression-canary:** Regression testing framework for AI coding agents using YAML task definitions with workspace, expected file changes, and scoring. Supports Claude Code, Codex, Cursor, and custom agents. — [github.com/phoenix-assistant/agent-regression-canary](https://github.com/phoenix-assistant/agent-regression-canary)

- **ArXiv — AlphaEval (April 2026):** Survey of 27 AI product companies finds 63% report low confidence in whether model updates actually improve their products, 25.9% have no explicit evaluation criteria, and 70.4% rely on developers testing as a side task. — [arxiv.org/abs/2604.12162](https://arxiv.org/abs/2604.12162)

- **HN Discussion (July 2025):** Practitioners consistently report evaluations as vital for improving production AI systems. LLM-as-judge noted as reliable for structured tasks but prone to sycophancy on ambiguous ones; recommend pairing with deterministic tool-call validation. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **Treating eval scores as dashboards instead of gates** — if a failing eval doesn't block deployment, it won't be fixed; it will be ignored
- **Golden datasets go stale** — production patterns change; treat dataset maintenance as a first-class engineering task, not a one-time setup
- **Judging the judge** — an uncalibrated LLM-as-judge can be systematically biased; always cross-validate against human labels on a 10% sample
- **Cost only matters if you measure it** — most CI pipelines never track per-task cost; without this signal, you can't distinguish an efficient agent from an expensive one
- **Silent model updates** — OpenAI and Anthropic push model updates to API endpoints without notice; without a golden dataset replay on a cadence, you won't know your agent regressed until users report it
