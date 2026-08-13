# S-2599 · The Agent Evaluation Stack — How Teams Know When Their Agent Is Actually Broken

Your agent passes every test. MMLU is strong. HumanEval is 90%. You ship it. Two weeks later a user files a ticket: the agent sent a refund request to the wrong customer and never noticed. No crash. No error log. Every API call returned 200. The agent just did the wrong thing subtly and completely. You had no test that could have caught it — because your tests measured text quality, not task completion.

This is the agent evaluation problem: most teams have no systematic way to know whether their agent actually works in production, only whether it looks good on sample prompts.

## Forces

- **Academic benchmarks don't predict production failures.** MMLU, HumanEval, and GSM8K measure single-turn generation quality — not tool-use trajectories, not recovery behavior, not multi-step task completion. A model scoring 95% on HumanEval can fail at booking a meeting room because it loops on a rate-limit response.
- **The ground truth is expensive to label.** Golden datasets require domain experts who understand both the task and the edge cases. Synthetic data fills gaps but must be human-reviewed — unreviewed synthetic items dilute the trust that makes a dataset golden.
- **LLM-as-judge needs calibration.** Treating the judge as ground truth masks its own failures. Without measuring agreement between judge and human labelers, you may be shipping based on a confident wrong answer.
- **Evaluation without CI integration is theatre.** An eval suite that runs manually is not a safety net — it's documentation of what you wish you'd tested.
- **Traditional software testing assumptions break for agents.** Software assumes deterministic outputs, bounded execution, and observable failures. Agents produce probabilistic outputs, run multi-step trajectories, and fail silently.

## The move

Build a **four-layer evaluation stack** that covers pre-deployment capability, regression gates, production monitoring, and human oversight. The critical insight: layer on the output side (final answer), not just the model side (benchmarks).

### Layer 1 — Capability Benchmarks (Pre-Deployment)
- Run standardized agent benchmarks (WebArena, SWE-bench, tau-bench, GAIA) as a model/architecture selection signal. Treat as necessary but not sufficient.
- WebArena scores went from ~14% to ~60% in 2 years — use these to track whether your stack is competitive, not whether it's safe.
- SWE-bench for software engineering agents; tau-bench for policy-compliant tool use; GAIA for multi-step reasoning under real-world constraints.

### Layer 2 — Golden Dataset Regression (CI/CD Gate)
- Build a custom golden set of 50-200 cases representing your actual domain — real inputs your agent encounters, with correct outputs labeled by domain experts.
- Run golden set on every PR merge. Block deploy if regression exceeds threshold (e.g., >2% task-completion regression).
- Supplement with synthetic variations of known-hard cases: paraphrases, adversarial phrasings, edge cases for recently launched features. Review every synthetic item with the same rigor as real data.
- Tool: `ashishlandiwal/agent-eval-harness` provides a traced agent + eval suite + LLM-as-judge calibration (Cohen's kappa) + CI regression gate, runs offline. Evalanche (Snowflake Labs) orchestrates LLM evals in Snowflake. RAGs on evaluation for offline harness-style testing.

### Layer 3 — Shadow Traffic and Online Sampling (Production Monitoring)
- Route 5-10% of production traffic through the eval pipeline in shadow mode — agent acts normally, but the eval captures trajectory for later scoring.
- Score trajectories using LLM-as-judge with calibrated thresholds. Compare judge scores against human spot-checks monthly to detect drift.
- Track behavioral metrics beyond accuracy: task-completion rate, step efficiency (did it take 3 steps or 30?), recovery success (did it handle the error or silently give up?), and cost per task.
- Key observability tools: LangFuse, Arize Phoenix, OpenLIT for traces; agent-eval-harness for offline evaluation.

### Layer 4 — Human Review and Escalation (Quality Floor)
- Sample 1-2% of completed tasks for human review — focus on high-stakes actions (refunds, deletions, external API calls) and low-confidence decisions.
- Create an escalation queue: tasks that fail validation repeatedly or trigger uncertainty signals route to a human supervisor agent, not back to the main agent loop.
- Review cycles should feed back into Layer 2 — human findings become new golden dataset entries.

## Evidence

- **Blog post:** "LLM Evaluation in Production: Agent Benchmarks That Actually Predict Failure" (Vatsal Shah, June 2026) — documents that academic benchmarks fail to predict production incidents; 50-case golden set + CI block prevented ~94% of tool-routing regression incidents in one team. — [shahvatsal.com](https://shahvatsal.com/blog/llm-evaluation-production-agent-benchmarks-2026)
- **HN discussion:** "Ask HN: How are people doing AI evals these days?" (March 2026, 43 comments) — consensus that most teams use no evals or only integration tests; growing adoption of LangFuse, Arize Phoenix, and custom CI gates; "vast majority of AI companies evaluate mostly based on vibes." — [news.ycombinator.com/item?id=47319587](https://news.ycombinator.com/item?id=47319587)
- **HN discussion:** "Principles for production AI agents" (July 2025, 128 points) — practitioner recommending fewer, spec-driven evals over hundreds of generic ones; eval suite owner noting LLM-as-judge agreement needs explicit measurement, not assumption. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **Research synthesis:** "AI Agent Self-Healing and Failure Recovery" (Zylos Research, May 2026) — Galileo 2025 analysis of multi-agent failures: specification failures 42%, coordination breakdowns 37%, verification gaps 21%; Microsoft 2025 failure taxonomy: tool misuse, context loss, goal drift, retry loops, cascading errors, silent quality degradation. — [zylos.ai](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/)
- **GitHub:** `ashishlandiwal/agent-eval-harness` — open-source eval + observability harness with Cohen's kappa-calibrated LLM-as-judge, drift monitoring, and CI regression gate. — [github.com/ashishlandiwal/agent-eval-harness](https://github.com/ashishlandiwal/agent-eval-harness)

## Gotchas

- **Golden sets go stale.** Your agent's task distribution shifts when product features change. A golden set built in January is measuring January's agent, not June's. Re-label quarterly or tie re-labeling to feature launches.
- **LLM-as-judge has bias patterns.** Judges prefer verbose, well-formatted outputs over concise ones; they prefer outputs that restate the question. Calibrate with Cohen's kappa against human labels before trusting judge scores for any high-stakes decision.
- **Task completion ≠ output quality.** A golden set that only checks whether the agent reached the correct final state misses silent quality degradations — wrong data written correctly, correct action on wrong entity. Track trajectory-level correctness, not just endpoint correctness.
- **No eval catches goal-specification mismatch.** If the human wrote the spec wrong, every eval that passes will be confidently wrong. The most dangerous failures are the ones where the agent does exactly what you asked for, not what you meant.
