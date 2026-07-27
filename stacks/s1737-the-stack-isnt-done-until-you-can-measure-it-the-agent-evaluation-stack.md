# S-1737 · The Stack Isn't Done Until You Can Measure It: The Agent Evaluation Stack

[You've built the agent. It calls tools, loops, returns results. You shipped it. Three weeks in, an on-call engineer gets paged at 2 AM because the agent is confidently making wrong decisions on a class of queries nobody put in the test set. Your eval set passed green. Your users are getting confident nonsense. The agent returned 200 OK every time.]

## Forces

- **A 95%-accurate model over 10 steps gives you ~60% reliability.** Each agent step multiplies failure probability. Traditional software testing — one input, one output — doesn't map to multi-step agents where errors compound silently down a trajectory.
- **Benchmarks lie because they freeze.** Your eval set represents the world as of the day you wrote it. Production inputs drift, user intents evolve, upstream APIs change. A static test set grows stale from the moment you deploy it.
- **Agents are systems, not models.** Evaluating an agent means evaluating behavior — planning, tool calls, recovery, handoffs — not just final output quality. Traditional LLM metrics (BLEU, ROUGE) were never designed for this and consistently fail to predict real-world performance.
- **Automation grades format, not judgment.** An LLM can produce perfect JSON with wrong facts, and an automated eval will score it high. The failure mode is in the semantic layer, where deterministic checks don't reach.
- **Most teams don't have evals at all.** Only 5% of surveyed AI projects have agents live in production; among those that do, fewer than 1 in 3 teams are satisfied with their observability and evaluation tooling.

## The Move

The move is a layered evaluation stack with three diagnostic levels, anchored by a continuously-updated golden dataset built from production traces — not curated from imagination.

### Build a three-level eval stack (Confident AI, 2026)

Evaluate at three depths and use them as a diagnostic funnel:

1. **End-to-end (black box):** Did the agent complete the task successfully? Binary pass/fail on the final outcome. Start here — it's the simplest and most actionable.
2. **Trajectory-level:** Did the agent take an efficient and correct path? Inspect tool calls, reasoning steps, retries, and handoffs. This surfaces *how* it succeeded or failed, not just *whether*.
3. **Component-level:** Which specific sub-system broke? Test individual tools, retrievers, or sub-agents in isolation. This is your debugging layer.

> Use the funnel in order: if end-to-end fails, dig into trajectory; if trajectory shows a pattern, isolate the component. Don't skip to component-level — you'll miss systemic failures.

### Define success criteria before you run, not after

Every eval needs a stated definition of correct behavior established *before* the agent runs. Without this, teams rationalize marginal outputs into the success column. For open-ended tasks, use an LLM-as-judge with a written rubric: the judge should evaluate against explicit criteria (e.g., "acknowledges customer frustration in opening," "references specific order number from ticket"), not vague quality scores.

Source: *[Evals as PRDs — Agent Shortlist](https://agentshortlist.com/articles/evals-as-prds), 2026*

### Anchor your golden dataset to production traces, not intuition

Build the initial eval set from real production traces — actual inputs your agent has handled. Supplement with synthetic generation for edge cases you haven't seen yet, but always review synthetic cases before adding them to the golden set.

> "An unreviewed pile of examples produces scores nobody acts on; a golden dataset produces scores that block or promote releases."

Curate: input + reviewed reference output (or explicit pass criteria for reference-free checks). The "golden" label means someone trusted the label — not that it was auto-generated.

Source: *[Golden Dataset Evaluation — Langfuse](https://langfuse.com/resources/engineering/golden-dataset-evaluation)*

### Make the eval set live: continuous drift detection

Static golden datasets decay. Production inputs drift over weeks and months. The fix is a feedback loop where real-world failures feed back into evaluators.

Practical approach: route uncertain or low-confidence production cases to SMEs for annotation. Use those annotations to improve your evaluator models. Run periodic regression suites comparing current production behavior against historical baselines.

> "Your team shipped to production with confidence, and three weeks later an on-call engineer got paged at 2 AM because the autonomous agent was confidently dispensing wrong answers on a class of queries nobody thought to include in the test set."

Source: *[Beyond Golden Datasets — Galileo Labs, July 2026](https://galileo.ai/blog/beyond-golden-datasets-static-evals-failures)*

### Layer human-in-the-loop at the right checkpoints

Automated evals handle regressions, formatting, and speed. Humans handle ambiguity, ethical tradeoffs, and intent verification. Route to human review when: the agent expresses low confidence, the action has irreversible consequences (writes, deletes, sends), or automated scores disagree with each other.

> "AI output can appear perfect while making the wrong call. Automated evals grade format, not judgment."

Source: *[Human-in-the-Loop Evals — Statsig](https://www.statsig.com/perspectives/humanloopevals-automationlimits)*

### Treat evaluation as a product requirement, not an afterthought

Evals are the new PRD for AI agents. Define the quality bar before writing the agent — the eval is the specification. A good eval is: one input + expected behavior, agent runs, framework checks output against criterion, reports pass/fail. Iterate the agent until the eval passes, then add the next eval case.

Source: *[Evals as PRDs — Agent Shortlist](https://agentshortlist.com/articles/evals-as-prds)*

## Evidence

- **Survey:** Only 5% of AI projects have agents live in production (95 of 1,837 respondents). Among production teams, fewer than 1 in 3 are satisfied with observability/guardrail solutions. 70% of regulated enterprises rebuild their AI stack every 3 months or faster. — *[Cleanlab: AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025), August 2025, n=95 engineering/AI leaders*

- **Engineering post:** "I've been surprised to find that most of the products out there billing themselves as 'AI Agents' are not all that agentic. A lot of them are mostly deterministic code, with LLM steps sprinkled in at just the right points." Teams hitting the 70–80% reliability ceiling with frameworks rebuild from scratch. — *[12-Factor Agents — Dex Horthy / HumanLayer](https://github.com/humanlayer/12-factor-agents), April 2025, 475 HN points, 24.8k GitHub stars*

- **Blog post:** "A model that is 95% accurate on a single step is not 95% reliable over a ten-step task. If errors are independent, ten steps at 95% each lands you near 60% end to end." — *[AI Agent Evaluation Metrics: A 2026 Guide — AI Agent Square](https://aiagentsquare.com/blog/ai-agent-evaluation-metrics)*

- **Blog post:** Golden datasets stay frozen while production traffic drifts. Continuous evals anchored in production traffic close the gap — real-world failures feed back into evaluators that improve with every annotation cycle. — *[Beyond Golden Datasets: Why Static Evals Miss Critical LLM Failures — Galileo Labs](https://galileo.ai/blog/beyond-golden-datasets-static-evals-failures), July 2026*

## Gotchas

- **Don't skip end-to-end evals for component tests.** Individual tool/unit tests give false confidence — the system can fail at the integration layer even when every component passes in isolation.
- **LLM-as-judge introduces judge bias.** The judge model has its own failure modes. Validate the judge against human-reviewed cases before relying on it for pass/fail gates.
- **Coverage isn't coverage if the test set is stale.** A 100% pass rate on a frozen eval set means nothing. Audit and refresh your golden dataset quarterly at minimum, or tie refresh cycles to deployment milestones.
- **Task success rate needs a human baseline to be meaningful.** "62% success" means one thing if humans hit 99% on the same tasks, and another if humans hit 70%. Always report against a human benchmark.
- **Don't automate away judgment calls.** If the agent is making decisions that have business consequences, at least sample those decisions for human review. Automated evals and human oversight are complements, not substitutes.
