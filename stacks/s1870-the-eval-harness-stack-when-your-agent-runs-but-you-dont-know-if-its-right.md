# S-1870 · The Eval Harness Stack — When Your Agent Runs but You Don't Know If It's Right

Your agent completes every task. The logs show green. Then a compliance officer asks how many patient records the agent hallucinated last month — and the answer is "we don't know." Monitoring and evaluation are not the same thing, and the gap between them is where production agents quietly fail.

## Forces

- **Most teams have observability, not evaluation.** A 2025 survey of 1,340 teams found 89% have agent observability (traces, logs) but only 52% run structured evaluations against documented test sets (Galileo, State of Eval Engineering Report, December 2025). Teams know something is off but cannot quantify it or catch regressions.
- **Agents succeed once and fail repeatedly.** Enterprise AI agents show ~60% success on single runs. That drops to ~25% when the same task is attempted 8 times. Standard benchmarks miss this reliability challenge because they measure capability, not consistency (Galileo AI, 2026).
- **The four things agents do that LLMs don't — and why each needs its own metric.** Agents take actions, invoke tools with specific parameters, make sequential decisions, and must recover from external API failures. Traditional LLM metrics (BLEU, perplexity) measure text quality — they cannot evaluate any of this (MachineLearningMastery, February 2026).
- **Retrofitting evaluation is expensive and leaves a blind spot.** Building eval infrastructure after shipping costs 4–6 weeks and causes data collection lag that lets regressions run undetected for days. The healthcare AI team at the center of the Towards Data Science case study learned this the hard way.

## The move

Build the eval harness before the agent ships. The harness is the infrastructure that defines what gets measured, runs the scoring, and acts on the results. It is the architectural backbone of a production evaluation practice.

### Structure around two modes

- **Offline evaluation** — run against curated datasets of known inputs and expected outputs. Catches regressions before deployment. Integrate with CI/CD: fail the pipeline when scores drop below threshold, just like unit tests.
- **Online evaluation** — run against production traffic using shadow mode or sampled traces. Catches drift, distribution shifts, and emergent failure patterns that offline sets miss.

### Measure the four pillars separately

- **Task Success** — did the agent accomplish its objective? Binary or rubric-graded, depending on the task.
- **Tool Invocation Accuracy** — did it call the right tool with the right parameters? This is where agents fail most often: wrong API, wrong arguments, or calling nothing when they should call something.
- **Reasoning Quality** — is the chain of decisions sound, even when the outcome is correct? Capture trajectory traces to debug the path, not just the destination.
- **Failure Recovery** — does the agent handle API errors, timeouts, and dead ends gracefully, or does it loop indefinitely or silently produce bad output?

### Capture trajectory metrics alongside outcome metrics

Outcome metrics (did it succeed?) tell you the score. Trajectory metrics (how did it reason?) tell you why — and whether a future change will break the reasoning pattern even if the current outcome is fine. LangSmith, Arize, and similar platforms expose this as a trace graph. Use it.

### Use LLM-as-Judge with calibration

A second LLM scoring the first agent's output works well for generation quality, but the judge model must be calibrated against human judgment. Target 0.80+ Spearman correlation before trusting the scores (Galileo, 2026). Without this calibration step, LLM-as-Judge is confidence theater.

### Build a rubric hierarchy

Effective evaluation rubrics operate at three levels (Galileo, 2026): top-level dimensions (7), sub-dimensions (25), and concrete criteria (130+). This makes evaluation granular enough to act on — "Behavioral Integrity, Gate B: FAIL" is actionable; "Agent Quality: 72%" is not.

### Integrate into CI/CD, not just dashboards

LangSmith, DeepEval, and Agent-Evaluator all support pytest integration. Treat agent evaluation like unit tests: run on every PR, nightly on main, and event-triggered on production anomalies. Automated pass/fail with thresholds beats dashboards for catching regressions.

## Evidence

- **Enterprise Survey:** 89% of orgs have agent observability, only 52% run structured evaluations. Survey of 1,340 teams, December 2025 (Galileo AI, State of Eval Engineering Report) — [URL](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Open-source eval harness:** Bolt Foundry's Gambit (github.com/bolt-foundry/gambit) — agent harness framework with generate → evaluate → grade → regress loop. Posted on HN with 91 points and 27 comments (HN ID 46641362, ~6 months ago) — [URL](https://news.ycombinator.com/item?id=46641362)
- **Production case study:** Healthcare AI team discovered three months post-deployment that they had no framework for measuring hallucination rate or context faithfulness. Retrofitting evaluation cost 4–6 weeks and left a data collection gap (Towards Data Science, "12-Metric Framework From 100+ Deployments", May 13, 2026) — [URL](https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/)
- **Multi-framework evaluation SDK:** Agent-Evaluator (bullpeng72/Agent-Evaluator, MIT license, 2026) — 7 Harness Gates (A–G) measuring Goal Achievement, Behavioral Integrity, Reliability, Performance Contract, Security Boundary, Multi-Agent Coordination, and Observability across 58 metrics. Auto-recognizes 24 frameworks including LangChain, CrewAI, AutoGen, DSPy, and PydanticAI with a single decorator — [URL](https://github.com/bullpeng72/Agent-Evaluator)
- **Benchmarking context:** GAIA, SWE-bench Verified, and WebArena are the canonical domain benchmarks teams reference. Harness-Bench (arxiv:2605.27922, May 2026) specifically studies configuration-level harness effects in agent workflows — [URL](https://arxiv.org/html/2605.27922v1)

## Gotchas

- **Observability is not evaluation.** You can trace every tool call and still have no idea if the output is correct. Traces show what happened; evaluation judges whether it was right.
- **LLM-as-Judge can be worse than no judge.** An uncalibrated judge model produces confident wrong scores. Calibrate against human-graded samples before deploying — and re-calibrate when you change the agent model.
- **Offline eval does not catch production drift.** Your test set is a snapshot. Real user queries, edge cases, and API behavior changes will surface only in online evaluation. You need both.
- **Tool invocation failures are the most common failure mode and the hardest to catch.** The agent may produce a correct-looking answer while calling the wrong tool — or calling no tool when one is needed. This requires explicit assertion logic, not just output quality scoring.
- **Eval at 58 metrics is still too coarse if you can't act on each one.** The temptation is to measure everything. The skill is knowing which 3–5 metrics, if improved, move the needle on user satisfaction — and which are noise.
