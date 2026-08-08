# S-2320 · The Agent Evaluation Stack — Making Your Measurement Loop Tell the Truth

You ran the eval. The score came back 94%. You shipped. Production fell over on inputs your test set never covered — because your evaluation was measuring the wrong thing, at the wrong level, against the wrong ground truth.

## Forces

- **Agents are stochastic pipelines, not functions** — a pass/fail on final output hides which step failed, which tool call drifted, and whether a correct answer was reached through a stable or fragile path
- **pass@k flatters; pass^k reveals** — an 85% per-step agent looks great at pass@3 (97.3%) but succeeds all three attempts only 34.3% of the time; the gap between these numbers is the reliability lie your metrics tell
- **89% of organizations have observability, but only 37% run online evals** — teams can see what agents do but not whether they're doing it well; the tooling outpaced the judgment
- **Golden datasets are the highest-leverage artifact, not the framework** — evaluating agents without a curated golden set is like testing code without known inputs; you get noise, not signal
- **LLM-as-judge needs its own calibration** — an uncalibrated judge is a second stochastic system layered on top of the first; without human-in-the-loop calibration, you're measuring the judge's opinion, not the agent's quality

## The Move

Build a three-tier evaluation architecture that checks the reasoning path alongside the output, bridges offline testing with production monitoring, and gates CI on scores that actually predict real performance.

**Tier 1 — Golden dataset (the foundation):**
- Curate 200–500 examples from real production traces, not synthetic prompts; label each with expected output and acceptable alternatives
- Every diagnosed production failure becomes a labeled dataset row — every new failure mode adds a fixture to the regression suite
- Distinguish pass^k (all k attempts succeed — the honest production metric) from pass@k (at least one attempt succeeds — the flattering one); track both

**Tier 2 — Graded evaluation levels:**
- **Run-level:** Did the agent complete the task? Binary or rubric score on final output (DeepEval, promptfoo, or custom scorers)
- **Trace-level:** Inspect the execution path — which tool was called, with what arguments, in what order; catch silent loops, wrong tool selection, and argument drift before they ship
- **Thread-level:** Evaluate multi-turn behavior over extended conversations — does the agent maintain context, recover gracefully, and avoid context window traps?

**Tier 3 — Calibrated LLM-as-judge:**
- Use a small golden set (50–100 human-labeled examples) to calibrate the judge before trusting its scores at scale
- Measure judge alignment with human annotations using Spearman correlation; re-calibrate whenever you switch models
- Run deterministic checks first (regex, schema validation, cost/latency thresholds) — reserve expensive LLM-judge calls for cases where deterministic checks show quality drops or for subjective dimensions (tone, safety, coherence)
- Sample 10% of production traces for LLM-judge scoring to manage cost while maintaining signal

**CI gate:**
- Block PRs when offline eval scores drop below the alignment floor — a documented threshold the team sets as the quality contract
- If the golden set fails but the judge says pass, recalibrate before shipping — the floor exists to prevent regressions, not to be worked around

## Evidence

- **LangChain State of Agent Engineering survey:** 89% of organizations have observability for agents, but only 52% run offline evals on test sets and only 37% run online evals — the tooling to see agents has outpaced the tooling to judge them — https://www.langchain.com/resources/agent-evals
- **Show HN — Auditi (open-source):** Builder noted "the hardest part isn't the prompts or orchestration — it's answering 'is this agent actually good?' in production. Tracing tells you what happened. But I wanted to know how well it happened." — https://news.ycombinator.com/item?id=46974783
- **Show HN — Meta-agent:** Framework that continuously improves agent harnesses from production traces; streams unlabeled traces through an LLM judge, uses small labeled holdout sets to calibrate — https://news.ycombinator.com/item?id=47665630
- **GitHub — evalharness (siddhashutosh):** Reusable LLM evaluation harness with golden test sets, LLM-as-judge scoring, regression detection against baseline, and CI quality gate that fails the build when quality drops — https://github.com/siddhashutosh/evalharness
- **GitHub — Agent Eval Arena (mizcausevic-dev):** TypeScript evaluation harness with golden datasets, multi-scorer execution, regression detection across model versions, cost-quality leaderboards, and CI gates for model promotion — https://github.com/mizcausevic-dev/agent-eval-arena
- **InfoQ — Evaluating AI Agents in Practice:** "Single-turn accuracy metrics (BLEU, ROUGE) don't capture multi-turn behavior, tool failures, or state management. Hybrid evaluation combining automated scoring with human judgment is non-negotiable for production agents" — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned
- **Thoughtworks — Evaluating AI Agents in Production:** "Golden datasets are not the commodity — evaluation frameworks are. The single highest-leverage activity is curating a few hundred high-quality examples representing your real distribution. Real production traces beat synthetic every time" — https://www.thoughtworks.com/en-us/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production

## Gotchas

- **Metrics that flatter:** Never report pass@k as your reliability metric if you're deploying to production — use pass^k. The gap between 97.3% and 34.3% for a "reliable" agent is not a rounding error.
- **Judge without calibration:** Running LLM-as-judge on your golden set without first measuring its alignment against human labels produces a number that predicts the judge's quality, not your agent's. Calibrate first, trust second.
- **Offline-only evals:** Spending weeks on pre-deployment coverage while skipping production monitoring means you'll catch known edge cases but miss the unknown unknowns that only surface under real distribution.
- **Golden set staleness:** A dataset that never gets updated from production failures is a snapshot, not a measurement system. Build the pipeline to convert every diagnosed failure into a labeled fixture automatically.
- **Ignoring operational constraints in eval:** Latency, cost per task, token efficiency, and tool reliability are first-class quality dimensions — an agent that produces correct output but costs 10x more than acceptable is not passing.
