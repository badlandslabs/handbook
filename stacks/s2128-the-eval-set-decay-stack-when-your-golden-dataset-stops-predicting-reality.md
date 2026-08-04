# S-2128 · The Eval Set Decay Stack — When Your Golden Dataset Stops Predicting Reality

Your eval suite passes at 94%. Your last release cleared CI. Six weeks later, users are hitting the same failure mode repeatedly and your golden dataset never caught a single one. The problem is not the agent. The problem is that your eval set is a snapshot of reality from three months ago, and the world has moved on.

## Forces

- **Eval sets are born accurate and rot over time.** Production input distributions shift: new edge cases emerge, user behavior changes, tooling updates, and prompt changes create new failure modes. A static dataset captures none of this.
- **Coverage inflation is invisible.** Teams add passing cases and rarely remove stale ones. The dataset grows while predictive signal per test case shrinks. You have more tests but less coverage.
- **Stale cases actively mislead.** When an eval case no longer reflects what "good" looks like, the eval gate rewards behavior that has nothing to do with production quality. A model that "passes" your stale eval set may be getting worse on what matters.
- **Dataset maintenance competes with feature work.** Teams know their eval sets decay; they don't budget for the maintenance loop because it has no immediate deliverable.
- **Detection is harder than prevention.** Unlike code tests, there's no natural signal when a test case stops being relevant. You have to actively measure decay.

## The move

The eval set is a living artifact. Treat it like a product — with a maintenance budget, a decay metric, and a refresh cadence.

### The four-stage lifecycle (Microsoft)

Microsoft's agent eval guidance defines four stages across the agent lifecycle:

1. **Build foundational evaluation test sets** — start with 20-50 representative cases covering happy paths and known edge cases, labeled with expected behavior
2. **Establish a baseline and improve** — run against baseline, identify gaps, add targeted cases for failure modes found in experimentation
3. **Implement systematic expansion** — grow to 100-200 cases with coverage tags, categorize by failure mode type, add production-mined cases
4. **Establish continuous quality improvement** — ongoing maintenance loop with staleness scoring and replacement

Source: [Microsoft Learn — Agent Evaluation Checklist](https://learn.microsoft.com/en-us/agents/agent-evaluation/evaluation-checklist)

### Track coverage tags, not just counts

LangChain's eval engineering guidance identifies a key mistake: "missing coverage tags." Each eval case should carry metadata — which agent behavior it targets (tool selection, retrieval, planning, response quality), which user intent it covers, and which production cohort it represents. Without tags, you cannot measure which dimensions of behavior are under-tested as the input space evolves.

LangChain's curation mistakes: dataset changes between runs, only happy-path cases, unclear expected behavior labels, unpinned run conditions, and unstable cases in golden datasets that pass sometimes and fail other times for non-behavioral reasons.

Source: [LangChain Blog — How We Build Evals for Deep Agents](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)

### Mine production failures into the eval set continuously

The highest-value pattern: production failures become test cases. Arthur's regression framework defines the loop:

```
Production Failure → Execution Trace → Test Case → Golden Dataset → CI/CD Gate
```

Every time an agent fails in production, capture the full execution trace (user input, tool calls, intermediate outputs, final output, error state). Route failure traces to human reviewers for labeling — what should the agent have done? — then add to the golden dataset with the correct expected behavior.

This approach finds authentic edge cases no one could have invented synthetically.

Source: [Arthur — AI Agent Regression Testing From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

### Run production sampling to detect drift

Replyant recommends sampling 5-10% of live traffic through a shadow evaluation pipeline. Run each sampled trace against the golden dataset's scoring rubric and compare to the same trace's eval score from 30 and 90 days ago. Flag cases where the eval score changed significantly — not because the agent degraded, but because the input distribution shifted and the expected behavior label no longer matches the production reality.

Source: [Replyant — Agent Evals in CI/CD: From Vibe Checks to Gates](https://replyant.com/lab/agent-evals-cicd/)

### Prune stale and unstable cases

LangChain flags "unstable cases in golden dataset" — test cases that pass on some runs and fail on others not because of agent behavior but because of inherent non-determinism in the case itself (ambiguous inputs, non-reproducible tool outputs, fuzzy expected outputs). These cases add noise to regression gates. Prune them: add deterministic scoring rubrics or remove the case until it's properly specified.

Also prune cases that cover behaviors the agent no longer needs to perform — feature changes render old test cases irrelevant.

## Evidence

- **Blog post (Microsoft Learn):** The four-stage agent evaluation lifecycle from foundational test sets through continuous quality improvement — [URL](https://learn.microsoft.com/en-us/agents/agent-evaluation/evaluation-checklist)
- **Engineering blog (LangChain):** Production eval engineering guidance — covering coverage tagging, deduplication, expected behavior labeling, dataset versioning, and the five typical mistakes in eval set curation — [URL](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- **Engineering post (Arthur):** The production-failure-to-test-case flywheel with full trace capture requirements and CI gate implementation — [URL](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Engineering post (Replyant):** The three-layer eval pipeline (offline regression, CI gate, production sampling) with 5-10% shadow traffic drift detection — [URL](https://replyant.com/lab/agent-evals-cicd/)

## Gotchas

- **A growing eval set is not a healthy eval set.** More cases with no staleness scoring means more noise and slower runs. Prune aggressively.
- **Expected behavior labels rot faster than inputs.** When your product changes, the "correct answer" in your eval case may be wrong. Labels need their own review cycle.
- **Coverage tags are only useful if you review them.** The tagging work is worthless if it sits in a spreadsheet and nobody acts on it when a coverage gap appears.
- **Non-deterministic test cases poison regression gates.** A case that sometimes passes and sometimes fails on the same code creates noise that masks real regressions. Fix or remove it.
- **Golden datasets from the team that built the agent carry creator bias.** Have a separate reviewer label expected behaviors — the builder will unconsciously design cases they know the agent can pass.
