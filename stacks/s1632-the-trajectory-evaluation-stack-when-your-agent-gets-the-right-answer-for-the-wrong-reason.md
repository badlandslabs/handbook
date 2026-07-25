# S-1632 · The Trajectory Evaluation Stack — When Your Agent Gets the Right Answer for the Wrong Reason

Your agent scores 94% on task completion. Your dashboards are green. You ship. Three days later a user reports the agent recommended a workaround that violates your security policy — it happened to not cause harm this time, so the tool-chain evaluation never flagged it. The agent reached the right destination via a reckless path, and endpoint scoring signed off on both.

This is the trajectory problem: checking whether an agent arrived is not the same as checking whether it traveled safely. Teams that run only outcome metrics miss the failure mode that produces right answers badly — and those right answers badly are where liability lives.

## Forces

- **Endpoint scoring is a false negative factory.** An agent can reach the correct final state through a sequence of policy violations, unnecessary tool calls, or lucky guesses — and an outcome-only eval will reward it.
- **Reasoning paths compound.** A single bad step in a 12-step trajectory can poison downstream steps. Trajectory evaluation catches where the reasoning went wrong, not just that it ended somewhere acceptable.
- **Benchmarks lie at two ends.** SWE-bench scores are contaminated (answer keys appear in training data); GAIA closes ~77-point gaps but still operates in isolation. Neither reflects the real stack of tools, rate limits, and auth complexity in production.
- **The right unit is the trace, not the test case.** Curated datasets age from the moment they freeze. Production traces are the only evaluation data that is guaranteed to match the world you're actually shipping into.
- **LLM-as-judge is powerful but requires calibration.** A judge LLM can score trajectory quality but needs 0.80+ Spearman correlation with human judgment before the scores are trustworthy — most teams ship the judge without verifying it.

## The move

Measure the path, not just the destination. Build a three-layer eval stack that captures the trace, scores the trajectory, and closes the loop back to your test set.

**1. Capture the full execution trace as first-class data.**
Every agent run — in staging and production — should emit a structured trace: tool called, arguments, response, latency, and the LLM reasoning at each step. LangSmith, Phoenix, or Langfuse all support this. Without a trace, you cannot evaluate a trajectory.

**2. Score the trajectory, not just the outcome.**
Define rubric dimensions that span the run:
- **Correctness:** Did the agent complete the task correctly?
- **Efficiency:** Did it use the minimum necessary tool calls and tokens?
- **Safety:** Did it violate any policy constraints (data access, rate limits, auth scopes)?
- **Recovery:** If it made an error, did it detect and correct it?

Each dimension gets a binary or Likert score from an LLM-as-judge, calibrated against a human-annotated gold set. The judge prompt is itself a deliverable — it must be tested.

**3. Run replay harnesses against production traces.**
A replay harness re-executes a captured trace against your current model or policy without hitting live systems. This lets you run regression against the exact scenarios production already encountered. Libraries like `agent-eval-harness` (praveenpke) support golden-dataset → trajectory capture → rule + LLM-as-judge → CI gate.

**4. Build the eval flywheel: production → trace → failure cluster → test case.**
Cluster production failures by root cause. Extract representative traces from each cluster. Add them to your offline eval set. Your offline suite now ages forward, not backward. This is the architectural move that closes the offline-pass-prod-fail gap.

**5. Calibrate your judge before trusting it.**
Run the LLM-as-judge against 50+ human-annotated examples. Measure Spearman correlation. Target 0.80+. If your judge disagrees with humans more than 20% of the time, it is measuring noise. Re-annotate and retrain the rubric before shipping the judge.

**6. Choose benchmarks that match your domain, not your ambition.**
- SWE-bench Verified: coding agents (but verify your model's version — contamination is documented)
- WebArena: browser-based agents (tests real UI interaction)
- GAIA: general assistants (best at predicting real-world task performance; humans score ~92%, best systems under 80% as of early 2026)
- BFCL v4: function-calling reliability
- τ²-Bench: customer service and domain-specific workflows

Use benchmarks to compare models during selection, not to gate production readiness. A benchmark score tells you what a model can do in isolation; it says nothing about what your agent does with your APIs, your auth layer, and your edge cases.

## Evidence

- **HN Ask HN (2025):** A practitioner attempting benchmark-style agent evaluation found that benchmark approaches "failed in ways I didn't expect" — models reach correct answers via wrong methods, and the test harness doesn't catch policy violations that don't produce observable errors. — [HN #47416033](https://news.ycombinator.com/item?id=47416033)

- **Practitioner blog (James M, June 2026):** Detailed walkthrough of trajectory evaluation for production agents: per-step rubrics, replay harnesses, 50–200 real examples with 10+ runs per example, and statistical regression tracking. Key finding: "Endpoint scoring certifies answers, not behaviour" — an agent can reach the right answer through a reckless path and endpoint evals will reward it. — [jamesm.blog](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)

- **LangChain / LangSmith docs (2025–2026):** Official trajectory evaluation guide describing the two-mode approach: Trajectory Match (hard-coded reference path validation) and LLM-as-Judge (qualitative rubric scoring), with installation commands and integration patterns for CI/CD. — [LangChain Trajectory Evals](https://docs.langchain.com/langsmith/trajectory-evals)

- **AgentMarketCap analysis (April 2026):** Cross-benchmark comparison showing SWE-bench contamination is real, GAIA better predicts real-world performance, and composite scoring across GAIA + WebArena + BFCL reveals capability gaps that single-benchmark selection misses. — [agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/11/composite-agentic-benchmark-view-2026)

- **FutureAGI blog (April 2026):** Documents six "drift modes" that age every eval set from the moment it freezes. Argues the correct unit of evaluation is the production trace, not the curated test case, and provides the 4-D rubric approach (correctness, efficiency, safety, recovery). — [futureagi.com](https://futureagi.com/blog/agent-passes-evals-fails-production-2026)

- **GitHub agent-eval-harness (praveenpke, June 2026):** Open-source evaluation toolkit for LangGraph agents implementing the full pipeline: golden datasets → trajectory capture → rule + LLM-as-judge scoring → CI gate. — [github.com/praveenpke/agent-eval-harness](https://github.com/praveenpke/agent-eval-harness)

## Gotchas

- **Outcome-only metrics greenlight dangerous paths.** If you only check "did the agent complete the task," you will ship agents that complete tasks by violating policy, leaking data, or making lucky guesses. Every safety-relevant failure mode is invisible to outcome scoring.
- **LLM-as-judge scores without calibration are noise.** A judge that hasn't been validated against human annotations can score inconsistently, be biased toward longer responses, or fail on cases near the rubric boundary. Calibrate before deploying.
- **Benchmark contamination is real and documented.** SWE-bench answer keys have been found in training data. SWE-bench Verified attempts to address this with new instances, but verify which version your model was evaluated on. Never use a benchmark score as a ship gate.
- **Single-run success ≠ multi-run reliability.** One run succeeding at ~60% means eight runs succeed at only ~25% (Galileo AI, 2026). If your production agent processes 1,000 requests, the math guarantees failures. Run enough iterations to catch the compound failure rate.
- **The eval flywheel stalls without ownership.** Capturing traces is easy. Clustering failures, extracting test cases, and updating the offline suite requires someone to own it. Without a designated owner, the flywheel stops and your offline set ages into irrelevance.
