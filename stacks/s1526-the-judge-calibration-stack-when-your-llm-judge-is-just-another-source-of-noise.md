# S-1526 · The Judge Calibration Stack — When Your LLM Judge Is Just Another Source of Noise

You wire an LLM-as-judge into your eval pipeline, run it against 500 traces, and get a beautiful dashboard showing 91% quality. Three weeks later, a user reports your agent booked a flight to the wrong city and sent a calendar invite for the wrong date. The judge had been lying to you — consistently, confidently, and with high correlation to human ratings. You calibrated nothing. This is the Judge Calibration Stack.

## Forces

- **Speed vs. accuracy** — human review catches subtle failures the judge misses, but annotating 100+ examples is slow and expensive; the pipeline cannot wait for perfection
- **Coverage vs. reliability** — broader eval criteria make scoring noisier; tighter criteria make the judge fragile and prone to gaming
- **The judge's own noise** — LLM judges have systematic biases (position, verbosity, self-preference) that add variance on top of the agent variance you're trying to measure
- **The regression paradox** — a judge with 80% correlation to humans can still mask failures that humans would catch; correlation measures alignment of *rankings*, not agreement on *outcomes*

## The Move

Build a calibrated judge pipeline with three gates: a golden dataset, a bias audit, and a CI regression block.

### 1. Build the golden dataset from real failures, not thought experiments

- Mine production traces for failures: flagged outputs, user corrections, manual reviews, API errors
- Every new failure category that slips through becomes a new golden entry
- Minimum viable size: 100+ labeled examples covering the distribution you care about
- Tag each example with the failure mode: wrong tool call, hallucinated citation, silent logic error, format mismatch

### 2. Audit the judge for three systematic biases

- **Position bias**: swap the order of candidates (A vs B → B vs A) and check if the judge reverses its verdict; a reliable judge scores both orderings the same
- **Verbosity bias**: give the judge two semantically equivalent outputs where one is longer; a biased judge prefers the longer one
- **Self-preference**: if the judge model matches the agent model, check whether it rates that model's outputs higher than a different model's outputs on the same task
- Use Cohen's Kappa (not Pearson correlation) as the primary calibration metric — it measures *actual agreement* on binary outcomes, not correlation of continuous scores

### 3. Calibrate with a threshold, not a feeling

- Require Cohen's κ ≥ 0.6 against human labels before trusting the judge on that criterion
- If kappa drops below threshold after a model or prompt change, require human review for that slice until re-calibrated
- Track kappa per evaluation dimension — a judge may be reliable on format checks but unreliable on reasoning quality

### 4. Wire the eval into CI as a regression gate

- The judge runs in CI on every PR against the golden dataset; a drop in aggregate score below threshold blocks merge
- Run golden traces on every deploy candidate, not just on code changes — model provider updates silently degrade behavior
- Sample 5–10% of live production traffic for async judge evaluation; failing production traces become new golden entries

## Evidence

- **GitHub repo (agent-eval-harness):** Full eval harness with LLM-as-judge calibrated against human labels via Cohen's kappa, with a CI regression gate that merge-blocks on quality drops — [github.com/ashishlandiwal/agent-eval-harness](https://github.com/ashishlandiwal/agent-eval-harness)
- **GitHub repo (llm-judge-calibrator):** Open-source tool that detects position bias, verbosity bias, and self-preference in LLM judges using position-swap experiments and Cohen's Kappa — [github.com/joaquinhuigomez/llm-judge-calibrator](https://github.com/joaquinhuigomez/llm-judge-calibrator)
- **Research paper (NVIDIA, 2025):** "Judge's Verdict" benchmark evaluating 54 LLMs as judges; demonstrates that Pearson correlation (r ≥ 0.80) is insufficient and that Cohen's Kappa captures systematic bias that correlation masks — [arxiv.org/html/2510.09738v1](https://arxiv.org/html/2510.09738v1)
- **Industry guide (DigitalApplied, 2026):** Production eval methodology recommending ≥ 100 labeled examples for judge calibration, κ ≥ 0.6 as minimum threshold, and 60–80% of dev time spent on evaluation for high-reliability teams — [digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology](https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)
- **Industry guide (LangWatch, 2025):** Framework distinguishing trajectory-level evaluation from output-level evaluation; identifies "silent failures" where agents reach correct answers via wrong reasoning paths — [langwatch.ai/blog/framework-for-evaluating-agents](https://langwatch.ai/blog/framework-for-evaluating-agents)

## Gotchas

- **Correlation is not agreement.** Two judges can have r = 0.95 and still disagree on 30% of individual cases — Pearson r measures how well rankings track, not how often verdicts match. Always report Cohen's Kappa alongside correlation.
- **A calibrated judge on one dimension is not calibrated on another.** A judge reliable for factual accuracy (κ = 0.72) may be unreliable for reasoning quality (κ = 0.31). Calibrate and threshold per criterion, not globally.
- **The golden dataset decays.** As your agent improves and production traffic shifts, old goldens no longer represent the distribution. Re-annotate and refresh quarterly, or on any major agent architecture change.
- **Silent failures require trajectory inspection, not just output scoring.** A judge that scores the final answer "correct" will miss the agent that used last year's financial report and happened to produce the right number. You need trace-level metrics alongside judge scoring.
