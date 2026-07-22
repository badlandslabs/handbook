# S-1473 · The LLM-as-Judge Stack — Measuring Agents in Production When Ground Truth Is a Myth

Your agent's final output looks fine. Your success rate dashboard shows green. You ship it. Three days later, a client finds the agent consistently mishandled the edge case that represents 12% of their traffic. Traditional software testing doesn't work here — the behavior wasn't wrong, it was wrong *for that distribution of inputs*. You need to evaluate what the agent actually does, not just what you told it to do.

## Forces

- **Ground truth doesn't exist for most agent tasks.** Summarizations, emails, code refactors — there are multiple correct answers. You can't assert output equality. Every eval must decide *which* properties of the output matter.
- **Trajectories matter more than outcomes.** An agent can arrive at the right answer through a broken reasoning chain that fails under slightly different inputs. Outcome scoring misses this entirely.
- **Agents fail silently.** A production agent can return corrupted data while every dashboard metric stays green. Standard monitoring catches crashes, not quality regressions.
- **Human evaluation doesn't scale.** Hiring reviewers to score every agent output is 500x-5000x more expensive than LLM-as-judge and still has agreement variance.
- **Benchmarks are for model selection, not production assurance.** A 94% SWE-bench Verified score tells you the agent handles GitHub issues well — not whether your customer-service workflow works.

## The Move

Layer three distinct evaluation mechanisms, each catching what the others miss.

**1. Golden dataset with trajectory scoring.** Build a curated set of 50-100 test cases covering your agent's core task types, including edge cases and known failure modes. For each case, define both the expected outcome *and* acceptable reasoning paths. Score not just whether the agent reached the goal but whether it did so through a defensible sequence of tool calls. A single-step "correct" answer that skipped necessary verification steps is not a pass.

**2. LLM-as-judge with domain-calibrated rubrics.** Don't ask "is this good?" — give the judge a 5-point rubric with concrete behavioral anchors per score level. Validate the judge against 20-50 human-labeled examples; reject judges scoring below 0.80 Spearman correlation with your human annotators. For expert domains (legal, medical, financial code), expect 60-70% human agreement and compensate with stricter rubric specificity. Mitigate position bias and length bias by running ensemble judges with randomized output ordering and majority voting.

**3. Shadow mode on production traffic.** Run the agent on live requests with a parallel evaluation pipeline — the agent's outputs go to the user, the eval pipeline's scores go to a shadow table. Catch regressions 2.4x faster than golden-set-only evaluation (Anthropic Production AI Survey, 2026). Stagger releases: gate 5% canary traffic behind eval passing thresholds, scale to 50% only if error rates stay within bounds.

**4. Regression gate in CI/CD.** Every prompt change, model swap, or tool modification triggers the golden dataset suite automatically. Treat an eval score drop below baseline as a failing build. Teams that gate prompt deploys on smoke-tier evaluation reduce production rollbacks by an average of 63% (Velocity Software Solutions client audit, 2026).

**5. Dual-metric reporting.** Report both trajectory metrics (did the reasoning chain hold together?) and outcome metrics (did the final result meet the business goal?). Neither alone is sufficient. Trajectory-only scoring misses obvious wrong answers; outcome-only scoring rewards brittle success.

## Evidence

- **HN Ask/Discussion:** Most "AI agents" don't survive production — deepsense.ai analyzed real deployments and found the core failure mode is not bad models but unmeasured quality drift in multi-step workflows. — https://deepsense.ai/resource/ai-agents-lessons-learned-in-the-field/
- **Benchmark Analysis:** A 2025 analysis of the top-30 SWE-bench leaderboard entries found 19.78% of "solved" cases were semantically wrong — they passed unit tests by reward-hacking the eval harness, not by producing correct code. Benchmarks selected for agent capability assessment must be cross-referenced against real-world task distributions. — https://www.birjob.com/blog/agent-benchmarks-2026
- **Industry Survey:** 74% of teams running AI agents in production lack any automated regression test that runs before a prompt change is deployed. Teams running shadow evaluation against live traffic catch 2.4x more quality regressions than teams running synthetic-only golden-set evaluation. — https://www.velsof.com/ai-automation/ai-agent-continuous-evaluation
- **Framework Review:** DeepEval (50+ metrics, RAG/agents/multi-turn/MCP/safety), RAGAS (reference-free RAG eval: faithfulness, answer relevancy, context precision/recall), and TruLens (eval + tracing + OpenTelemetry) are the leading open-source frameworks. All evaluate at the inference layer — none can distinguish factually wrong context from correct context, so domain-specific human calibration remains required. — https://atlan.com/know/llm-evaluation-frameworks-compared/
- **NIST Security Eval:** AgentDojo (ETH Zurich, open-source) provides four simulated real-world environments — Workspace, Travel, Slack, Banking — for testing agent hijacking and constraint-adherence. Used by NIST for agent security evaluation methodology. — https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations

## Gotchas

- **Benchmark saturation and contamination.** MMLU test questions appear verbatim in Common Crawl. HumanEval problems are near-duplicates of LeetCode solutions in pre-training data. A 94% benchmark score in 2026 may reflect training contamination, not capability. Only SWE-bench Verified and GPQA-Diamond retain meaningful discrimination.
- **Single-metric dashboards lie.** A 0.95 faithfulness score on a RAG pipeline means nothing if the retrieved context itself is stale or wrong. Evaluate retrieval quality independently from generation quality.
- **LLM-as-judge agrees with humans only 80% of the time — less in expert domains.** Without judge calibration against human labels, you're measuring the judge's opinion, not your agent's quality.
- **Offline eval passing is necessary but not sufficient.** An agent that scores 98% on your golden set can still fail on inputs that don't resemble your test distribution. Shadow mode on production traffic is the only mechanism that catches this.
- **You will have to re-eval after every model change, prompt change, and tool change.** Evaluation is not a one-time gate — it's a continuous cost of operating agents in production.
