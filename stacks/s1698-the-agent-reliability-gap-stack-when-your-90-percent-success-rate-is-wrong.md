# S-1698 · The Agent Reliability Gap Stack — When Your 90% Success Rate Is Wrong

Your agent passes 9 out of 10 test cases. You ship it. Over the next week it fails on the same task 3 times in a row for a single user, and quietly produces wrong output the other 2 times nobody notices. Your "90% success rate" was measuring the wrong thing: single-trial pass rate on a demo set, not reliability under production conditions. This is the agent reliability gap — the difference between benchmark optimism and operational reality — and it is the primary reason agent projects get cancelled after deployment.

## Forces

- **Single-run pass rates lie.** An agent with 90% pass^1 has only 65% chance of passing 3 consecutive trials (0.9³) and 35% after 10. Teams that test once and call it done are measuring luck, not reliability. This distinction matters most when agents handle high-stakes or high-volume tasks.
- **Reliability is the top production challenge.** A 2025 survey of 306 AI agent practitioners across 26 domains found reliability (consistent correct behavior over time) ranked as the #1 development challenge, cited by 37.9% of respondents — ahead of cost, latency, and accuracy. Yet most evaluation frameworks still report only first-attempt success rates.
- **Production agents are deliberately constrained.** The same survey found 68% of deployed agents execute 10 or fewer steps before human intervention, and 74% depend primarily on human evaluation. Teams are not building unreliable agents by accident — they are building narrow, constrained agents and still struggling with reliability.
- **What "correct" means is ambiguous.** For a coding agent, correctness is verifiable (tests pass). For a customer service agent, correctness involves tone, policy compliance, and whether the user actually got what they needed — none of which are easy to grade at scale.

## The Move

Measure reliability, not just success. The key shift is from "does it work on this input?" to "does it work consistently across repeated executions, perturbed inputs, and infrastructure failures?"

- **Track pass^k instead of pass^1.** Run each test case k times (k=5 or k=10) and report the fraction where the agent succeeds at least once. τ-bench (Sierra, 2024) popularized this: even GPT-4o achieves <50% pass^1 and <25% pass^8 on retail-domain tasks. If your agent handles 50 customer requests per day, a 75% pass^1 compounds into significant daily failures.
- **Stress-test three failure dimensions.** ReliabilityBench (Gupta, 2025) defines reliability across three axes: consistency (pass^k under repeated runs), robustness (pass rate under semantically equivalent input perturbations), and fault tolerance (pass rate when tools or APIs fail). Each dimension surfaces different failure modes a single-run benchmark misses.
- **Instrument four production signals together.** Amazon's AgentCore framework codifies this as: operational metrics (is the system healthy?), application logs (what did the agent do at step N?), distributed traces (why did it take this path?), and quality evaluations (was the output correct?). Treating any one as sufficient is the common mistake.
- **Build a golden dataset from production failures.** When the agent fails in production — quietly or loudly — add that input to the eval suite immediately. This is the fastest way to close the gap between test conditions and real conditions. S-1695 covers this pattern in detail.
- **Calibrate LLM-as-judge with human review on a sample.** Automated scoring at scale requires a judge, but the judge itself is unreliable. Run human rubrics on a 50–100 trace sample to calibrate the judge before trusting it on the full dataset. S-1696 covers this in depth.
- **Gate releases on reliability thresholds, not feature flags alone.** A CI/CD pipeline that tests prompt changes against the golden dataset and fails if pass^k drops below threshold catches regressions before they reach users. This is distinct from traditional code CI because a prompt change is a code change with probabilistic output.

## Evidence

- **MAP Survey (Pan et al., 2025, arXiv:2512.04123):** First large-scale study of agents in production — 306 practitioners, 20 case studies, 26 domains. Found 74% depend primarily on human evaluation, 68% execute ≤10 steps before human intervention, and reliability is the #1 challenge (37.9%). Accepted as oral at ICML 2026. — [arXiv:2512.04123](https://arxiv.org/abs/2512.04123)
- **τ-bench (Sierra Research, 2024):** Introduced pass^k reliability metric and dynamic user simulation for agent benchmarking. Found GPT-4o achieves <50% pass^1 and <25% pass^8 on retail domain tasks. Established that first-attempt success rates dramatically overstate real-world reliability. — [arXiv:2406.12045](https://arxiv.org/abs/2406.12045) | [taubench.com](http://taubench.com/)
- **ReliabilityBench (Gupta, 2025):** Benchmarks agents across consistency (pass^k), robustness (ε-perturbations), and fault tolerance (λ-failures). Key finding: simpler ReAct agents outperform complex Reflexion architectures under stress conditions; GPT-4o costs 82× more than Gemini 2.0 Flash with comparable reliability. — [arXiv:2601.06112](https://arxiv.org/html/2601.06112)
- **Amazon Bedrock AgentCore Production Guide (Konishi, 2026):** Codifies four-signal observability model (metrics + logs + traces + quality evals) as minimum production posture. Notes that non-determinism makes root-cause analysis impossible without distributed tracing. — [hidekazu-konishi.com](https://hidekazu-konishi.com/entry/amazon_bedrock_agentcore_production_guide.html)

## Gotchas

- **Golden datasets go stale.** Production data shifts — APIs change, user behavior evolves, policy updates. An eval suite that isn't refreshed quarterly measures your agent against a world that no longer exists. Build a pipeline that ingests production failure cases automatically.
- **pass^k is expensive.** Running 10 trials per test case means 10× token cost per eval run. Teams compromise by running full pass^k only on a subset of critical test cases and pass^1 on the full suite.
- **Operational metrics can mislead.** Latency green and error rate zero still permit agents that return subtly wrong answers. Traditional APM does not catch "the agent did the wrong thing perfectly."
- **Human review doesn't scale, but skipping it costs more.** The MAP study found 74% of teams rely primarily on human evaluation — but those teams are also the ones stuck with eval pipelines that can't run overnight. The answer is not to eliminate human review but to use it calibrating automated judges, not as the primary scoring mechanism.
