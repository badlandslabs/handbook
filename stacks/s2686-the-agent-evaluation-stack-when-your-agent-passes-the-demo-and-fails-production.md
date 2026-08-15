# S-2686 · The Agent Evaluation Stack

When your agent passes every demo, every benchmark, and every manual test — then fails 30% of the time in production and you have no idea why.

## Forces
- **Determinism vs. non-determinism** — standard software tests have one right answer; agents with identical inputs can take 3 tool calls or 12, succeed or fail, and still produce an acceptable result
- **Trajectory vs. outcome** — a final output check misses the real failure: the agent took the wrong reasoning path that happened to land on the right answer
- **Cascade blindness** — an error in step 2 doesn't surface until step 7, so smoke tests that check only the output see nothing
- **Human evaluation doesn't scale** — manually reviewing agent traces is the gold standard but collapses past 100 runs/week
- **Gartner projects 40%+ of agentic AI projects will be cancelled by 2027** — most die not from bad models but from unmeasured, accumulating failures in production

## The Move

Treat agent evaluation as a three-layer system: **trajectory metrics** (did it take the right path), **step-level metrics** (did each tool call succeed), and **outcome metrics** (did the task complete). Run all three.

**1. Instrument before you evaluate.** Wrap every agent loop in structured trace capture: input → reasoning → tool call → observation → output. Langfuse, Braintrust, and Phoenix (Arize) all do this. You cannot evaluate what you cannot see. Without traces, you're flying blind.

**2. Split trajectory from outcome.** Outcome metrics (task completion rate, error rate) tell you if the agent works. Trajectory metrics (reasoning quality, tool call sequence, step efficiency) tell you *why* it sometimes doesn't. Track both. One catches regressions; the other catches drift.

**3. Use LLM-as-judge for what you can't script.** Hard assertions cover happy paths. LLM-as-judge covers the fuzzy middle — "did the agent handle the edge case gracefully?" and "was the reasoning sound?" Calibrate the judge against human-labeled examples before shipping it. Without calibration, you measure the judge's biases, not the agent's quality.

**4. Build a gold dataset before automating.** Collect 50-200 real production traces. Label them manually (human-in-the-loop, even one reviewer). This becomes your evaluation dataset. Without real data, you test your imagination, not your agent.

**5. Gate CI/CD on evaluation runs.** Trigger evals on every significant change: prompt revision, model swap, tool logic change, new tool addition. Use progressive canary deployment — route 5% of traffic to the new version, run eval, expand if metrics hold. Never push a changed agent straight to 100% of traffic.

**6. Monitor trajectory drift in production.** Set alerts on trajectory metrics trending downward even when outcome metrics look stable — this is the leading indicator of a degrading agent before users notice. PagerDuty on task success rate is too late.

## Evidence
- **Braintrust blog (Feb 2026):** Lays out trajectory vs. outcome metric taxonomy, shows that trajectory metrics catch reasoning failures that outcome-only checks miss entirely. Documents LLM-as-judge calibration workflow with statistical validation against human agreement rates. — [braintrust.dev/articles/ai-agent-evaluation-framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- **Galileo AI blog (2026):** Documents the three-tier rubric structure, domain-specific benchmark selection process, and three CI/CD trigger types (prompt change, model change, deployment). Cites Gartner's 40%+ cancellation projection and frames evaluation infrastructure as the antidote. — [galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Lucidic (YC W25, July 2025):** YC-backed agent observability platform from Stanford AI Lab. Founders worked on math olympiad agents (AIME/USAMO) and e-commerce agents — found that every small change (prompt tweak, model switch, tool logic) requires a full 10-minute re-run of the evaluation suite, validating the CI/CD gate pattern. 116 HN points, 39 comments. — [news.ycombinator.com/item?id=44735843](https://news.ycombinator.com/item?id=44735843)
- **Langfuse cookbook (2026):** Three-phase evaluation approach: (1) manual trace inspection during development, (2) thumbs-up/down feedback plus automated online evaluators in early production, (3) offline evaluation pipeline with gold datasets at scale. Documents trace-structured capture as prerequisite. — [langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation](https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation)
- **Noqta blog (Apr 2026):** Documents LLM-as-judge maturity arc from 2024 hack ("ask GPT-4 if this is good") to 2026 discipline with calibration protocols, bias taxonomies, and trajectory-specific scoring. — [noqta.tn/en/blog/ai-agent-evaluation-production-performance-metrics-2026](https://noqta.tn/en/blog/ai-agent-evaluation-production-performance-metrics-2026)

## Gotchas
- **Outcome-only monitoring misses the leading indicator.** By the time task success rate drops, the agent has been producing bad trajectories for days. Trajectory drift precedes outcome drift.
- **LLM-as-judge without calibration measures the judge's model, not your agent.** A judge fine-tuned to agree with itself is useless. Anchor the judge against a human-labeled subset before treating its scores as ground truth.
- **Golden datasets go stale.** Production data distribution shifts; a gold dataset from 6 months ago may not reflect current user behavior. Re-label quarterly or on significant product changes.
- **Evaluation latency kills CI/CD adoption.** If your eval suite takes 20 minutes, engineers will skip it. Target sub-5-minute runs for the critical path; async the comprehensive suite.
- **Flaky tests are the norm, not the exception.** A 15% flakiness rate is common for agent evals. Don't treat every failure as a regression — build in retry-with-threshold logic and track flakiness rate as its own metric.
