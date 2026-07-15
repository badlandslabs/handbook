# S-1139 · The Evaluation Surface Stack — When Your Agent Looks Good in Tests and Fails in Production

Your agent scores 94% on your test set. It ships. Three days later, users are complaining it gives wrong answers with high confidence, loops on edge cases, and burns through tokens on simple queries. The test set was never the problem. The evaluation surface was. You were measuring a cross-section of agent behavior when you needed to measure the whole terrain.

The shift from single-prompt LLMs to multi-step agents breaks every assumption that makes traditional software testing work. The output is probabilistic, the reasoning path is part of the product, and the "correct" answer often has multiple valid forms. The AgentFail dataset and Braintrust's 2026 evaluation research converge on the same finding: the teams that ship reliable agents aren't the ones with better models — they're the ones with broader, more honest evaluation surfaces.

## Forces

- **Outcome and trajectory are different dimensions.** An agent can reach a correct answer through a terrible reasoning path that would fail under slightly different inputs. Outcome-only metrics miss this class of failure entirely. Braintrust's research calls trajectory scoring "the missing half" of agent evaluation — it catches regressions that outcome scoring simply cannot.
- **Golden datasets are narrow and stale by design.** A curated test set captures known cases. Production traffic generates unknown ones. Teams that only evaluate against golden datasets ship agents that handle the test set well and fail on anything adjacent.
- **Academic benchmarks don't reflect production agents.** UC Berkeley's examination of eight prominent AI agent benchmarks found they failed to isolate the agent from the evaluator, passed reference answers to the agent, and lacked adversarial testing of the evaluation itself. The AgentBench leaderboard covers domains that most production agents never touch.
- **LLM-as-judge has a calibration cliff.** At 500x–5000x lower cost than human evaluation, LLM judges achieve ~80% human agreement in general domains. In expert domains — legal, medical, specialized code review — that drops to 60–70%. The fix is domain-specific rubrics with behavioral anchors, not better prompting.
- **Stochastic systems need continuous measurement.** A one-time eval run before launch is meaningless for a system whose outputs vary across runs. Operating envelopes — cost, latency, step/token budgets — must be tracked alongside quality metrics in production traces.

## The move

Build a multi-layered evaluation surface that covers trajectory, outcome, and operating behavior — and gate it into CI/CD.

- **Use both trajectory scoring and outcome scoring.** Run them together. Trajectory scoring evaluates the path (did the agent call the right tools, in the right order, with the right arguments?). Outcome scoring evaluates the destination (did it accomplish the task?). Braintrust's research confirms: trajectory catches failures that outcome misses. A run can succeed at the final step while taking a route that would break under input variation.
- **Build a golden dataset from real production inputs.** Mine actual user queries and edge cases from production traffic. Annotate them with expected outputs and reasoning traces. Store them versioned alongside your agent config. This is the foundation for reproducible eval. Without production-grounded examples, your test set drifts from reality.
- **Calibrate LLM-as-judge with domain-specific rubrics.** Don't ask "is this a good answer?" Provide a 5-point rubric with concrete behavioral anchors for each score level. Without rubrics, judge agreement on the same content varies by up to 30% across different prompts. In expert domains, validate the judge against human annotations before relying on it at scale.
- **Track operating envelopes in every trace.** Log cost in USD, latency, and token usage per step alongside quality scores. An agent that scores 90% but costs $4 per query and takes 45 seconds is not the same as one that scores 90% at $0.04 and 3 seconds. Operating envelopes make tradeoff visible.
- **Gate CI/CD with eval runs, not just linting.** Treat prompts as source code: version them, eval them on the golden dataset on every PR, and block merges on regression. Prompt changes are behavioral changes. The CI pipeline should run the full eval suite against the golden dataset before any deploy.
- **Monitor production traffic continuously, not just pre-launch.** Route a sample of live requests through your eval pipeline and track quality distributions over time. A production monitoring gap means you learn about regressions from users, not from your dashboard.

## Evidence

- **Research post — Braintrust:** "Trajectory scoring catches regressions that outcome scoring misses because an agent can succeed at the final step while taking a path that would fail under slightly different inputs. Always run both." — [AI Agent Evaluation: A Practical Framework for Testing Multi-Step Agents](https://www.braintrust.dev/articles/ai-agent-evaluation-framework), February 2026
- **Industry survey — RockB / Zylos Research:** LLM-as-judge achieves ~80% agreement with human evaluators at 500x–5000x lower cost, dropping to 60–70% in expert domains (legal, medical, specialized code). Domain-specific rubrics with behavioral anchors are the calibration fix. — [AI Agent Testing Guide 2026](https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026), citing Galileo and Braintrust 2026 evaluation research
- **Production reliability data — Reinventing AI Insights:** Aggregate success rate of 56.6% across 4,492,066 tests on 6,259 production AI agents in 10 geographic regions (March 2026). Academic benchmarks (AgentBench, WebArena) showed inflated scores not replicated in production environments. — [How Production AI Agents Are Being Tested in 2026](https://insights.reinventingai.org/articles/ai-agents-evaluation-production-reliability-2026-04-27)
- **Tooling — DeepEval / Confident AI:** Open-source eval framework (DeepEval) implements trajectory scoring, golden dataset CI integration, and operating envelope tracking as first-class primitives. Reports golden + CI as the standard production eval stack. — [AI Agent Evaluation Guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide), April 2026
- **Tooling — Iris (MCP-native):** Open-source MCP server for agent eval that auto-discovers MCP-compatible agents and logs full execution traces with spans, tool calls, token usage, and cost. 12 built-in eval rules across completeness, relevance, safety, and efficiency categories. — [Show HN: Iris](https://news.ycombinator.com/item?id=47379690), Hacker News

## Gotchas

- **Outcome-only evaluation gives false confidence.** The agent passes every test but takes a broken path on anything not in the test set. Always pair outcome scoring with trajectory scoring.
- **Golden dataset neglect.** A golden dataset built once and never updated from production traffic becomes a museum of past failures, not a sensor for current ones. Annotate production edge cases into the dataset continuously.
- **Skipping production monitoring.** Pre-launch eval is necessary but not sufficient. Operating envelope drift (cost per query climbing, latency spiking) often precedes quality regressions. Monitor both in production.
- **Treating LLM-as-judge as ground truth.** Without rubric calibration and human spot-checks, judge scores can be confidently wrong. Validate the judge before scaling it.
- **Failing to version prompts.** Prompt changes are behavioral changes. Without versioned prompts and paired eval runs, you cannot bisect regressions or roll back to a known-good state.
