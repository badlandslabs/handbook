# S-788 · The Agent Evaluation Gap: Why Teams Ship Blind

[Your AI agent works in the demo. It answers the happy-path question, calls the right tool, and returns a clean response. Then you change the prompt, swap a model, or add a third tool — and something breaks in a way you cannot reproduce. You have no evaluation suite, no regression signal, and no idea it failed until a user files a bug report. This is the default state of AI agent development: teams ship blind and find out in production.]

## Forces

- **Agents are path-variable where traditional software is deterministic.** A unit test with a fixed assertion can verify a function. An agent can reach the same correct answer via exponentially many execution paths — and exponentially many wrong ones. Exact-match metrics are too brittle to capture this.
- **Only 52.4% of teams run offline evaluations, and just 37.3% run online evals.** The majority of agent teams ship without any systematic quality gate. LangChain's 2026 State of AI Agents report quantifies what most engineers already feel: evaluation is the afterthought that bites when you least expect it.
- **Agent behaviors only emerge under real LLM execution.** Which tool the agent decides to call, how it formats responses, whether a prompt modification cascades into an entire execution failure — none of this surfaces in static analysis or mock testing. You need a live model.
- **Human review doesn't scale.** Agents processing thousands of daily interactions cannot be reviewed by humans at scale. Yet without structured evaluation, you have no quality signal at all.
- **The eval you don't run is the one that would have caught the regression.** Once an agent reaches "good enough," the pressure to add evaluation feels like overhead. But the eval debt compounds silently until a bad model swap or prompt change surfaces a production incident.

## The move

Build a layered evaluation system that combines offline test-set grading, LLM-as-judge scoring, and production observability — with gates that block deploys.

**Offline eval: golden dataset + trajectory match**
- Curate a small golden dataset (15–30 examples) that combines real production logs (natural request distribution), edge cases captured from failure incidents, and synthetically generated hard cases for gaps.
- Scope the dataset to a single workflow. Narrow scope → clearer expectations → actionable signal.
- Use deterministic trajectory matching (LangChain's `agentevals` "trajectory match") for well-defined workflows: hard-code the expected step sequence and validate step-by-step. No extra LLM calls, fast feedback, reproducible.
- Supplement with rubric-based LLM grading for nuanced dimensions (relevance, efficiency, safety) where exact matching fails.

**LLM-as-judge: rubric-engineered, bias-calibrated**
- Define a structured rubric with explicit criteria (task completion, reasoning coherence, tool call appropriateness, harmlessness) rather than a vague "is this good?"
- Use a judge model of the same or higher tier than the agent being evaluated. Grading with a weaker model introduces systematic underestimation.
- Calibrate the judge: run the same rubric against known-good and known-bad examples to detect systematic bias before relying on scores.
- Apply reference-free evaluation (compare input→output directly) for production monitoring where no ground truth exists. Use reference-based (compare against golden answer) for pre-deployment test suites.

**Production observability: three-layer monitoring**
- System efficiency layer: completion time and per-step latency (detect planning loops), token usage by phase (detect over-exploration), tool call success rate and count (detect looping).
- Task completion layer: outcome accuracy (did it achieve the goal?), intermediate step accuracy (did each tool call produce the right result?), trajectory efficiency (did it take the shortest viable path?).
- Safety/risk layer: confidence scoring with configurable thresholds (auto-escalate low-confidence outputs), injection detection on inputs, irreversible-action gating with human approval.

**Eval gate in CI/CD**
- No code change ships without running the evaluation suite against the golden dataset.
- Track pass rate trends over time. A 2% drop is a conversation, a 10% drop is a block.
- Alert on production quality drift: when online metrics diverge from offline baseline, trigger a review before the next deploy.

**Human-in-the-loop for high-stakes actions**
- Tier action risk: routine reads (fully autonomous) → moderate writes (async human review queue) → irreversible actions (mandatory sync approval before execution).
- Route by confidence score: outputs below threshold auto-escalate regardless of other signals.
- SLA breach proximity and irreversibility flags trigger mandatory human handoff.

## Evidence

- **Engineering blog — AWS:** Amazon's agentic AI evaluation framework separates agent-specific behaviors (tool selection accuracy, multi-step reasoning coherence, memory retrieval efficiency, task completion success) from standard LLM benchmarks. They identify HITL as critical for multi-agent systems because "automated metrics might fail to capture" emergent coordination failures, inter-agent communication breakdowns, and conflict resolution failures that only surface when agents work together. — [Evaluating AI agents: Real-world lessons from building agentic systems at Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **Technical article — Mastra.ai:** Details the evaluation stack: offline test-set grading catches regressions before deploy; LLM-as-judge with a structured rubric assesses nuanced quality dimensions; production observability with confidence thresholds and escalation routing catches failures that only emerge at scale. Cites the 52.4% offline / 37.3% online eval rate as the industry baseline most teams fall below. — [AI Agent Evaluation: Build Production-Grade Agents](https://mastra.ai/articles/ai-agent-evaluation)
- **Research note — Zylos Research:** Documents the calibration problem with LLM-as-judge: "the gap between a naively-configured judge and a well-calibrated one is wide enough to produce opposite conclusions about agent quality." Recommends running the rubric against known-good and known-bad examples before trusting judge scores, and using trajectory-specific scoring that evaluates each agent step independently rather than scoring only the final output. — [LLM-as-Judge Patterns for Agent Evaluation](https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns/)
- **HN post — Agent-evals Claude Skill:** An engineer with 10 years of AI evaluation experience in finance notes that "building strong, up-to-date evals is much harder in a fast startup, especially when the team does not have a data science background." Offers a structured approach: narrow workflow scope first, gather examples from logs, synthesize edge cases, then build regression suite. — [Show HN: Agent-evals – Claude skill to build your own evals](https://news.mcan.sh/item/48013746)

## Gotchas

- **Narrow eval scope before expanding it.** Teams that try to evaluate all agent behaviors at once end up with a fragile, unmaintainable suite. Start with one well-understood workflow, build the infrastructure, then expand.
- **Trajectory match works for linear workflows, not branching ones.** When your agent has genuinely multiple viable paths to the same goal, a strict trajectory match will false-positive on correct executions. Use LLM-as-judge for flexible path evaluation instead.
- **LLM-as-judge bias is real and direction-specific.** Judges tend to favor verbose outputs and penalize concise ones, prefer responses that mirror the judge's own reasoning style, and are susceptible to position bias (preferring the first candidate in comparisons). Calibrate before trusting.
- **Production eval drift lags real regressions.** If you only run evals on a weekly cadence, you won't catch the regression until days after it impacts users. Budget for real-time or near-real-time scoring on a sample of production interactions.
- **Synthetic golden examples miss the real distribution.** Teams that build evaluation sets entirely from synthetic data find their evals pass while production fails. Always include real production logs — even just 15 examples — to anchor the distribution correctly.
