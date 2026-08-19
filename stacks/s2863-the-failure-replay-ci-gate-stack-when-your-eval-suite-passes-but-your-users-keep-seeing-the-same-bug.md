# S-2863 · The Failure-Replay CI Gate Stack — When Your Eval Suite Passes But Your Users Keep Seeing the Same Bug

Your agent has a 94% pass rate on your golden set. Your CI is green. But a production failure that cost you 3 hours of support tickets last week reappears 6 weeks later — the same root cause, a different user. The bug was never added to the golden set. Your eval suite was measuring last month's agent against last month's problems. You need the discipline that closes the loop: convert every production failure into a permanent regression test, and gate every merge on it.

## Forces

- **Golden sets go stale; production never does.** A fixed eval set built during onboarding reflects the agent as it existed then. As prompts evolve, tools change, and user traffic shifts, the eval set silently stops representing what the agent actually handles. Teams report measurable drift within 4–12 weeks of deployment, yet most golden sets are never refreshed.
- **Production failures are unreproducible knowledge.** Every time an agent does something wrong in front of a real user, you receive a test case you could not have invented — a genuine edge case, an authentic input distribution, a concrete definition of what "broken" looks like for your system. Most teams file the incident report and never add the case to CI.
- **Observability catches failures; eval gates prevent them.** 89% of teams monitor agent behavior post-deployment, but only 52.4% run offline evals on pull requests. The gap means you learn about regressions from users, not from CI. This is not a monitoring gap — it is a missing circuit between production and the merge gate.
- **The regression budget forces the binary decision.** When you run 100-case eval suites across multiple agent routes, aggregate pass rate hides localized failures. A 94% pass rate means 6 failures — but if those 6 failures are all on the same high-stakes route, 94% is a lie. Teams need per-route regression budgets that make failure unavoidable to discuss rather than easy to average away.

## The move

The failure-replay loop converts production incidents into permanent CI gates through a disciplined four-bucket golden set and a regression budget framework.

**Build the four-bucket golden set:**
- **Production sample (60%):** Stratified export of real production traces, rotated monthly. Resamples from the actual traffic distribution rather than from memory.
- **Adversarial coverage (15%):** Inputs from jailbreak corpora, red-team scans, and prompt injection libraries. Tests that the agent holds under attack, not just under normal traffic.
- **Edge cases (15%):** Hand-written cases by domain experts — the long tail of inputs that real users produce but that don't yet exist in production logs.
- **Failure replays (10%):** Every production failure becomes a test case. The incident trace is captured, anonymized, and added to the golden set within 48 hours of resolution. This bucket is non-negotiable — if it hits zero, the gate stops gating.

**Gate every merge on the full suite:**
- Run all four buckets against every pull request. Block the merge if any bucket drops below its threshold. A "close enough" pass on production sample cannot compensate for a zero on failure replays.

**Calibrate LLM-as-judge before trusting it:**
- Use structured rubrics (specific scoring criteria, not "does this look good"). Measure judge bias: run a multi-rater experiment and compute Cohen's κ between judges. A judge that systematically prefers longer outputs will give false passes to agents that verbose-hallucinate.
- Run judge evaluation alongside human review on a calibration set (recommend 20–50 cases) to establish baseline accuracy before scaling.

**Track regression budgets per route, not in aggregate:**
- Define per-route thresholds (e.g., the customer-support route must pass 92%, the data-export route 97%). Aggregate pass rates hide localized regressions.
- When a regression fires, the budget forces a binary decision: fix the agent or file an exception. No averaging, no "we'll address it next sprint."

**Version and rotate the golden set:**
- Tag every golden set with a semantic version (MAJOR for schema changes, MINOR for new cases, PATCH for ground-truth corrections). A frozen set ages against a moving answer — benchmark aging is measurable and significant.
- Track the age of every test case. Cases older than 90 days without a production hit on that input class are flagged for review or retirement.

## Evidence

- **Engineering blog (FutureAGI, May 2026):** Four-bucket golden set framework — 60% production sample, 15% adversarial, 15% edge cases, 10% failure replays. Emphasizes that any bucket hitting zero causes the eval gate to stop gating. Includes sizing math per route and calibration discipline with Cohen's κ. — [https://futureagi.com/blog/llm-eval-golden-set-design-2026/](https://futureagi.com/blog/llm-eval-golden-set-design-2026/)
- **Company engineering post (Amazon, February 2026):** Automated 4-step eval workflow: input definition → agent execution → response collection → grading. Proposes holistic framework combining code-based graders (fast, deterministic) and model-graded evaluators (flexible, handles ambiguity). Advocates HITL for audit and reliability alignment. — [https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Industry survey (LangChain, June 2026):** Survey of 1,340 practitioners found 89% monitor agents post-deployment but only 52.4% run offline evals on pull requests — meaning the majority learn about regressions from users rather than from CI gates. — [https://ecorpit.com/ai-agent-evals-ci-cd-silent-failures-2026/](https://ecorpit.com/ai-agent-evals-ci-cd-silent-failures-2026/) (reporting LangChain survey)
- **Engineering blog (Arthur AI, June 2026):** Regression test dataset built from production failures: "The highest-value regression test dataset for an AI agent is not handcrafted. It comes from production failures. Every time an agent does something wrong in front of a real user, it hands you a test case you could not have invented." — [https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Engineering blog (AgentMode AI, May 2026):** Regression-budget framework: per-route thresholds that force binary decisions on failures rather than averaging. Drift detection across three signal classes (semantic drift, tool-call pattern drift, cost-per-task drift). — [https://agentmodeai.com/agent-evaluation-in-production/](https://agentmodeai.com/agent-evaluation-in-production/)
- **GitHub repo (darkrishabh/agent-skills-eval, May 2026):** Open-source test runner that compares agent outputs with/without a skill loaded using a judge model, producing side-by-side measurable evidence. 679 stars. — [https://github.com/darkrishabh/agent-skills-eval](https://github.com/darkrishabh/agent-skills-eval)

## Gotchas

- **Adding cases without removing stale ones.** Golden sets grow but never shrink. Cases that no longer represent the agent's task space inflate pass rates without improving signal. Flag and retire cases that haven't matched production traffic in 90 days.
- **Judging yourself with the same model you shipped.** An LLM-as-judge running the same model family as the agent under test will inherit alignment preferences — it tends to score outputs that resemble its own training distribution higher. Use a different model family for the judge, or at minimum a different size tier.
- **Treating the golden set as documentation rather than infrastructure.** A golden set maintained in a spreadsheet, updated "when someone remembers," produces unreliable signal. It must be CI-native: versioned, auto-run on every PR, and owned by the team whose agent it gates.
- **Ignoring trajectory quality in favor of final-answer scoring.** A self-correction loop that produces a correct answer via 8 hallucinated tool calls and 3 retries is scored the same as a clean 2-step solution. Score not just the output but the path — tool-call correctness, step count, and retry rate are leading indicators of trajectory decay.
