# S-1483 · The Metric That Lies About Your Agent — When Pass@k Is Not Your Success Rate

Your agent succeeds 97% of the time on your test suite. You ship it. Two weeks later, customers are complaining about wrong outputs and nobody can reproduce it. The test suite wasn't measuring what you thought it was measuring. The numbers looked like confidence. They were hiding the real failure mode: your agent is non-deterministic, and you've been measuring the wrong thing entirely.

## Forces

- **Pass@k hides variance.** Pass@k = "at least one success in k attempts" is optimistic by design. A 70% per-trial success rate gives you pass@3 ≈ 97% — which looks production-ready. But pass^3 (success on ALL 3 attempts) = 34%. You're shipping on the number that flatters you.
- **Task completion ≠ correctness.** An agent can complete 95% of tasks while only 70% are actually correct. Completing the workflow and completing it correctly are different outcomes, and most eval suites only measure the first.
- **Offline testing and online monitoring are disconnected.** Most teams run structured tests before deploy and monitoring after, with no feedback loop. Failures in production never become regression tests, so the same failure recurs.
- **Synthetic test cases miss the tail.** What engineers imagine users will ask is a narrow distribution. Production users produce malformed inputs, ambiguous phrasings, and tool sequences nobody designed for.

## The move

Measure what production actually punishes: consistency and correctness, not peak performance. Build the loop that turns every failure into a permanent test.

### The right metric stack

- **Primary reliability metric: pass^k** — the probability the agent succeeds on ALL k runs of the same task. This is what matters for production deployment. For a 70%-per-trial agent, pass^3 ≈ 34%. That's the number that should gate your release, not pass@3.
- **Composite metric: completion rate × correctness rate.** Track both separately. If your agent completes 95% of tasks but only 70% are correct, the completion number is noise without the correctness filter.
- **Per-step quality metrics.** Break multi-step agents into: tool selection accuracy, reasoning step validity, final output correctness. A bad tool call that gets "recovered" is still a bad tool call worth measuring.
- **Golden dataset from production failures.** Treat every production failure as a test case in waiting. Flow: production failure → trace capture → failure classification → golden dataset → CI regression gate. This is the highest-signal eval source you have — it captures what users actually do, not what you imagined.
- **Online evaluators on live traces.** The same evaluators that run offline should run continuously on production traces. Catch failures before customers report them. Arize AX and Microsoft Foundry both support this unified eval loop; LangSmith supports it natively for LangChain apps.
- **Latency and cost as first-class metrics.** Agents that work but take 45 seconds or cost $2 per query are production failures by another name. Track p50/p95 latency per task type and cost-per-completion.

### The eval architecture

```
[Dev] Dataset (golden cases) → Offline eval → Pass^k gate → Deploy
                                                    ↓
[Prod] Live traces → Online eval → Failure capture → Golden dataset update → CI
```

## Evidence

- **Engineering blog — Phil Schmid:** Pass@k vs pass^k analysis with concrete numbers — 70% per-trial → pass@3 ≈ 97% (optimistic) vs pass^3 ≈ 34% (reality). Makes the case that consistency metrics are what gates production deployment. — [philschmid.de](https://www.philschmid.de/agents-pass-at-k-pass-power-k)
- **Hacker News thread (47301395):** Discussion of production monitoring gaps triggered by DataTalks Claude Code database wipe and Replit agent deleting data during code freeze. Commenters identified: no step-by-step visibility, surprise token bills, risky outputs undetected, no audit trail. Tools mentioned: AgentShield, LangSmith, Langfuse, Lava gateway for spend tracking, OpenTelemetry traces. — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **Y Combinator company — Lemma (F25):** "Lemma catches the silent, semantic failures your observability tools miss, where your agent looks like it worked but didn't. We scan every trace to surface issues before users complain." Productizes the pattern of scanning production traces for semantic failures that traditional observability misses. — [ycombinator.com/companies/uselemma](https://www.ycombinator.com/companies/uselemma)
- **Industry guide — Ashutosh Tripathi (Principal ML Engineer):** Documents that "agents that technically complete tasks don't necessarily complete them correctly — in one case, an agent completed 95% of tasks but only 70% were actually correct." Makes the case that standard unit tests fail for agents and that multi-axis evaluation is required. — [ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide)
- **GitHub repo — codeninja2022-create/production-grade-ai-agent:** Production-ready LangGraph agent with explicit golden dataset evaluation directory (`data/golden/`), LangSmith observability integration, guardrails, HITL, and pytest test suite. Shows the concrete scaffold teams use: `agent/` + `evaluation/` + `guardrails/` + `observability/` + `tests/`. — [github.com/codeninja2022-create/production-grade-ai-agent](https://github.com/codeninja2022-create/production-grade-ai-agent)
- **Survey — Cao & Yu (ACM 2025):** "Survey of Emerging Trends in LLM Agent Benchmarking" finds static benchmarks don't reflect practical performance in interactive environments and calls for open collaborative ecosystems (e.g., AgentBench Alliance) for auditable evaluation. — [dl.acm.org/doi/10.1145/3784013.3784018](https://dl.acm.org/doi/10.1145/3784013.3784018)

## Gotchas

- **Measuring pass@k alone is self-deception.** If you only report pass@3 and your agent has 30% per-trial failure, you have a 66% chance of shipping a broken release on any given 3-run average. Report pass^k as your primary metric.
- **Completion rate and correctness rate diverge.** If you don't separate them, high completion numbers will mask low correctness. Slice both by task type — some task categories may have 95% completion but 55% correctness.
- **Golden datasets decay.** User behavior shifts. What worked in Q1 is not a sufficient eval for Q3. Schedule quarterly refreshes of your golden dataset using production trace sampling, not just synthetic augmentation.
- **LLM-as-judge evaluators have bias.** Using one LLM to evaluate another introduces systematic preference for verbose outputs and certain answer formats. Validate LLM judges against human ground truth before trusting them at scale.
- **Single-task-eval pass rates don't generalize.** Running pass^k on 20 curated tasks tells you about those 20 tasks. Production task distribution is broader and messier. Always pair benchmark eval with production trace sampling.
