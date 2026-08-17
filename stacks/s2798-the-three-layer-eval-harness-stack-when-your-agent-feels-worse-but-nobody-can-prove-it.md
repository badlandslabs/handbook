# S-2798 · The Three-Layer Eval Harness Stack

_When a customer reports your agent "feels worse today," you have no alert, no number, and no way to prove they're right or wrong — because your eval harness doesn't exist yet_

## Forces

- Most eval harnesses measure the wrong thing: they test against fixed golden datasets and catch yesterday's regressions, while production quietly drifts in a direction nobody anticipated
- The three failure layers are temporally separated — drift happens over days, compounds over weekends, and surfaces as a customer complaint, not a monitoring alert
- Agent evaluation is fundamentally harder than LLM evaluation: you're scoring trajectories across dozens of steps, not a single response — tool selection, parameter validity, error recovery, and end-to-end goal completion all matter independently
- LLM-as-judge is powerful but expensive and needs calibration; using it everywhere is cost-prohibitive and introduces evaluator bias that compounds over time
- The exponential effort curve: the first 70% of agent quality is cheap; the next 20% requires multi-agent setups and external memory; the last 10% costs hundreds per run and still carries ~10% error rates

## The move

Build a three-layer eval harness. Each layer catches a different failure mode, runs at a different cadence, and has a different cost profile. You build them in order — you cannot skip to Layer 3.

**Layer 1 — Prompt unit tests (known regressions, locked fixtures)**
- Write explicit test cases: input → expected output structure or behavior
- Run on every PR. Cost: ~$1–5/month. Catches: specific regressions on cases that broke before
- Fail-fast. This is your gate.

**Layer 2 — Property tests on outputs (unknown regressions + schema drift)**
- Define invariants: "output always contains field X," "tool calls always include a valid ID," "response never exceeds N tokens"
- Run on every PR + hourly on sampled production traffic
- Cost: ~$5–20/month. Catches: unexpected output shapes, new failure modes, slow schema drift
- Use LLM-as-judge selectively here — for quality dimensions that require semantic judgment, not structural checks

**Layer 3 — Golden-trace drift detection (slow quality decay + data drift)**
- Store verified good agent trajectories ("golden traces") from when the system was working correctly
- Run nightly: compare current production traces against golden traces using trajectory-level similarity scoring
- Cost: ~$10–40/month. Catches: accumulated drift in agent behavior, quality decay, upstream data changes that silently break agent assumptions
- This is where the "feels worse today" failure mode surfaces — before the customer reports it

**For agent-specific evaluation, add trajectory scoring:**
- Score three things per agent run: goal completion, tool-use correctness (13+ issue types: wrong tool selected, invalid parameters, hallucinated tool calls), and conversation coherence
- Track cost-per-task and latency budgets — agents that loop burn money silently
- Use pass@k: run the same task k times and measure success rate, not single-run accuracy (Anthropic's research shows the exponential effort curve makes single-run evaluation systematically misleading)

## Evidence

- **Engineering blog — Autoolize:** The three-layer harness framework with cost estimates and cadence: Layer 1 catches known regressions on every PR, Layer 2 runs property tests hourly on production samples, Layer 3 compares against golden traces nightly — Sadig Muradov, founder, April 2026 — [autoolize.com/blog/eval-suites-catch-drift](https://autoolize.com/blog/eval-suites-catch-drift)
- **Engineering post — Anthropic:** Identifies the exponential effort curve for long-running agents and the two core evaluation failures (one-shotting and premature victory declaration) requiring separate tooling from single-response eval — November 2025 — [anthropic.com/engineering/effective-harnesses-for-long-running-agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **GitHub repo — Caliper:** Lightweight pass@k reliability harness for agent skills — runs tasks k times, tracks success rate over time, catches reliability regressions as models update — [github.com/edonadei/caliper](https://github.com/edonadei/caliper) (39 stars, MIT)
- **GitHub repo — agent-eval-harness:** Production TypeScript harness with trajectory scoring, tool-use validation (13+ issue types), cost tracking, and golden trace regression suites — [github.com/reaatech/agent-eval-harness](https://github.com/reaatech/agent-eval-harness)

## Gotchas

- Building Layer 3 before Layer 1 produces unreliable golden traces: you capture the broken behavior as the baseline and then never catch regressions against it
- LLM-as-judge needs human calibration — without it, the evaluator accumulates the same biases as the agent being evaluated; sample human-rated traces and compare judge scores against them regularly
- Trajectory-level evaluation is non-deterministic by design: run each eval case 3–5 times minimum (pass@k) and report the distribution, not the mean
- Offline evals on curated datasets plateau as your only signal: production traffic sampling is the only way to catch failure modes you haven't imagined yet
- Cost tracking without a budget ceiling is a gotcha: a single looping agent run can cost $12+ while passing all quality evals; budget enforcement must be a separate gating mechanism
