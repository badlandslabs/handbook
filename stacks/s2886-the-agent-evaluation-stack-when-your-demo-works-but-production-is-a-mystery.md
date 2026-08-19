# S-2886 · The Agent Evaluation Stack — When Your Demo Works but Production Is a Mystery

Agents are systems, not models. A model benchmark tells you how well a language model performs on a curated test set. It tells you nothing about whether your agent actually completes the tasks your users care about. Teams that skip evaluation infrastructure spend their first months in production discovering failure modes reactively — usually from users. The teams that survive build evaluation before deployment, not after.

## Forces

- **Standard software metrics break down.** Traditional unit tests can't verify non-deterministic, multi-step decisions that modify real state. "Did function X return Y?" has no answer when X is a 12-step reasoning chain with 4 API calls.
- **Task success and safety are independent dimensions.** An agent that achieves correct outcomes through unsafe means is worse than one that fails safely. Evaluating only outcomes misses this gap entirely.
- **The multi-run reliability cliff.** Enterprise AI deployments show 60% single-run success dropping to 25% across eight runs. Your benchmark success rate is a lie told once.
- **Trajectory metrics vs. outcome metrics.** You can have a right answer via a wrong path (lucky failure) or a wrong answer via a right path (correctable). Both require different interventions.
- **40% of agentic AI projects will be cancelled by 2027** (Gartner, 2025) — primarily due to evaluation and reliability gaps, not model quality.

## The Move

Measure agent quality across four independent dimensions, using automated evaluation for speed and human review for trust. Treat evaluation as a first-class production system, not a pre-launch checklist.

**Define success criteria before writing prompts.** Write the evaluation first: what does "done" look like, what constitutes partial credit, and what safety invariants must never break. Every metric flows from this definition.

**Track four primary metrics continuously in production:**

| Metric | What it measures | Production target |
|--------|-----------------|-------------------|
| Task Completion Rate | % of tasks fully completed without human intervention | > 85% |
| First-Pass Accuracy | % of deliverables accepted without revision | > 70% |
| Cost per Task | Total token + API + infrastructure cost per completed task | application-specific |
| Safety Violation Rate | % of runs violating defined safety constraints | 0% (hard floor) |

**Distinguish trajectory metrics from outcome metrics.** Trajectory metrics evaluate the agent's reasoning process: did it use the right tools in the right order? Did it recover from errors? Outcome metrics evaluate only the final result. A correct outcome via a lucky failure is as dangerous as a wrong answer — the agent was unreliable, not competent.

**Use LLM-as-judge for trace analysis at scale.** Tools like DeepEval's `TaskCompletionMetric` analyze full agent traces to determine task success, outputting a reasoning trace alongside the score. This enables automated evaluation of subjective or complex tasks without human review for every run.

**Build a golden dataset from production failures.** When a task fails, document it: input, agent trace, failure mode, root cause. This becomes your regression test suite. Teams at GrowthX who extracted Output.ai from 500+ production agents used this approach to build evaluation datasets that actually reflect real-world distribution, not synthetic benchmarks.

**Evaluate safety independently from task success.** Define hard constraints (no data exfiltration, no destructive operations without confirmation, no tool calls outside the allowlist) as separate pass/fail gates. A safety violation is a blocking failure regardless of task outcome.

**Run synthetic evaluation in dev, stakeholder-validated personas in UAT, real-world monitoring in production.** The evaluation framework must evolve across the development lifecycle — rapid automated checks for iteration speed, human judgment for acceptance, continuous monitoring for drift.

## Evidence

- **Engineering blog (Amit Kumar Padhy, InfoQ, March 2026):** "Agents are systems, not models — Evaluate them accordingly. AI agents plan, call tools, maintain state, and adapt across multiple turns. Single-turn accuracy metrics (BLEU, ROUGE) don't capture how agents fail in practice." Recommends hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis) with human judgment for tone and contextual appropriateness. — [URL](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)
- **Engineering post (Ashutosh Tripathi, Principal ML Engineer, Dec 2025):** Reports enterprise deployments showing 60% single-run success dropping to 25% across eight sequential runs. Argues for defining task success rate, cost per task, and error rate as the four core production metrics. — [URL](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide/)
- **GitHub repo (FuturOneAI/ai-agent-evaluation-framework, 2026):** Open-source enterprise evaluation framework with YAML-defined test suites covering task completion rate, precision/recall on bug-finding agents, citation accuracy for research agents, and real-time dashboards for P50/P95/P99 latency and cost tracking. — [URL](https://github.com/FuturOneAI/ai-agent-evaluation-framework)
- **HN Show (Output.ai, 2026):** Framework extracted from 500+ production agents at GrowthX. Non-deterministic testing identified as a core challenge — "testing AI code is inherently challenging." Built dataset-building tooling from production failure data rather than synthetic benchmarks. — [URL](https://news.ycombinator.com/item?id=47676157)
- **Microsoft documentation (Azure AI Foundry):** Built-in evaluation framework with provider-agnostic evaluators, zero-code basic scenarios scaling to programmatic advanced configurations, and cloud-based production-grade assessment alongside fast local dev checks. — [URL](https://learn.microsoft.com/en-us/agent-framework/agents/evaluation)

## Gotchas

- **Benchmark scores and production performance are uncorrelated.** SWE-bench and MMLU don't predict whether your customer-service agent completes a refund without escalating. Build application-specific evaluations, not model-level ones.
- **You need more than pass/fail.** A binary correct/incorrect metric hides the failure mode. A task can be 80% complete with the agent stuck on a minor formatting detail. Use graded rubrics that capture partial progress.
- **Sampling bias in golden datasets.** If your evaluation set only contains easy cases, it will be useless for catching real-world failures. Include edge cases, adversarial inputs, and failure examples from production.
- **Evaluation cost can exceed agent cost.** Running LLM-as-judge on every production request is expensive. Use sampling strategies: evaluate every Nth run, evaluate all failures, evaluate any flagged anomaly.
- **Drift detection is often missing.** A model update, API change, or data distribution shift can degrade agent performance silently. Schedule periodic re-evaluation against the golden dataset, not just continuous production metrics.
- **Human-in-the-loop creates a false ceiling.** If humans review every agent output "to be safe," you never learn the agent's true failure rate. Define clear escalation triggers rather than blanket human review.
