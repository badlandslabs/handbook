# S-1397 · The Agent Evaluation Stack — When Your Agent Ships and Nobody Knows If It Worked

You have an agent running in production. You have observability — traces, logs, cost dashboards. But you have no idea whether it's actually doing the right thing, whether it's getting better, or whether it silently failed on 30% of tasks last Tuesday. This is the evaluation gap.

## Forces

- **Agents fail silently.** Unlike traditional software, agent failures manifest as trajectory deviations, not crashes. The agent loops, picks the wrong tool, or silently produces wrong output — and your dashboard shows green.
- **Observability ≠ evaluation.** 89% of teams have agent observability, but only 52% have evaluation frameworks. You can see what happened; you still can't tell if it was right.
- **LLM outputs resist deterministic checks.** The same input produces different outputs across runs. Rule-based assertions catch only a fraction of real failures.
- **Evaluation is expensive and slow.** LLM-as-judge costs money. Human review costs more. Teams skip it under deadline pressure, then ship regressions.
- **Trajectory vs. outcome tension.** Outcome metrics tell you if the agent finished. Trajectory metrics tell you why it failed. Most teams only track the former.

## The Move

Build a layered evaluation system with three tiers that escalate in cost and accuracy:

**Tier 1 — Deterministic checks (free, fast, always run first)**
- Structural validation: is the output valid JSON? Did the agent call the right tool? Are required fields present?
- Mock external tools. Feed the agent known inputs. Assert on tool call sequences and parameter values. This is fast, deterministic, and covers the "did it pick the right tool with the right arguments" failure mode.
- Coverage target: every tool gets ≥5 test cases — 3 happy path, 1 error case, 1 edge case.
- Run in CI on every PR; takes seconds.

**Tier 2 — Trajectory evaluation (moderate cost, catches path-level failures)**
- Did the agent take a reasonable path, not just arrive at a plausible answer?
- Use execution traces — LangSmith, Phoenix, or custom. Compare the agent's actual decision tree against an expected trajectory.
- LLM-as-judge with caveats: use a *different* model than the one under test to avoid self-evaluation bias. Calibrate with examples. Watch for position bias (judges prefer longer outputs) and verbosity inflation (agents that over-explain score higher).
- Evaluate on 3 dimensions: task completion, reasoning quality, tool use accuracy.

**Tier 3 — Human review (expensive, only for high-risk paths)**
- Human review for customer-facing agents or any agent that makes commitments (financial, medical, legal).
- Tiered approval gates: Tier 1 drafts → human approves. Tier 3 commits autonomously with tighter pre-flight checks.
- Quantify residual risk by failure class so leadership can make an explicit risk acceptance decision.

**Continuous monitoring post-deploy**
- Track drift: model updates and tool changes break agents silently. Re-run eval suites monthly or after any model/infra change.
- Task completion rate, cost per task, and MTTR (mean time to recovery) are the three production metrics that matter most to stakeholders.
- Alert on regression: if pass rate drops below threshold on the eval suite, block deploy.

## Evidence

- **Blog post (RaftLabs):** 89% of teams have observability vs. 52% with evaluation frameworks — a 37-point gap. GAIA benchmark shows even top agents fail 39% of difficult tasks. GPT-4 hallucinates at 28.6% on systematic review tasks vs. GPT-3.5's 39.6%. — [https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide](https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide)

- **ACM Paper (AIMLSystems '25, TCS Research):** Proposed QA methodology for multi-agent systems integrating system performance monitoring (cost, LLM calls, duration) with individual agent correctness and inter-agent communication validation. — [https://dl.acm.org/doi/full/10.1145/3703412.3703439](https://dl.acm.org/doi/full/10.1145/3703412.3703439)

- **HN Discussion (128 pts):** Practitioners report prompt tweaks that "felt better" consistently scored worse on full eval suites. Critique of LLM-as-judge: same-model evaluation has self-evaluation bias; judges prefer longer, more verbose outputs; position bias on multiple-choice-style comparisons. — [https://news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)

- **GitHub (darshjme/verdict):** Production-grade agent evaluation framework with 3-dimensional scoring (task completion, reasoning quality, tool use accuracy), integrated with CI via `assert_test()` and paired with sentinel (runtime guards: MaxStepsGuard, CostCeilingGuard, LoopDetectionGuard) and herald (structured alerting to dashboards/Slack/PagerDuty). — [https://github.com/darshjme/verdict](https://github.com/darshjme/verdict)

## Gotchas

- **Don't use the same model as judge and subject.** Self-evaluation bias inflates scores. Use Claude to evaluate GPT outputs, or GPT-4o to evaluate GPT-4 outputs.
- **LLM judges prefer verbose outputs.** A more detailed (but not more accurate) answer will score higher. Calibrate with human-ground-truthed examples, not just synthetic ones.
- **Observability dashboards won't save you.** You can watch your agent run 10,000 tasks and still not know if 30% failed silently. You need structured eval runs against a representative dataset, not passive trace collection.
- **Eval datasets rot.** Production inputs shift. If you never update your eval dataset, your eval suite becomes a false positive machine — it passes while production degrades. Version and refresh your dataset with real production queries.
