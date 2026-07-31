# S-1911 · The Layer-Cake Stack

When you want to ship an agent and actually know if it's getting better — not just whether it looks good on a demo.

## Forces

- **No ground truth exists.** LLM outputs are open-ended: multiple valid summaries, equivalent code solutions, diverse acceptable refusals. Traditional accuracy/F1 metrics break down; you need evaluation strategies that don't require a single reference answer.
- **Single-run eval is a lie.** Agents are stochastic. A 60% pass rate on one run can collapse to 25% across 8 consecutive runs — not because the agent got worse, but because you never measured variance. Each task needs multiple trials.
- **Grading is as hard as the task itself.** Writing a grader that correctly identifies success versus a plausible failure — especially for reasoning chains and tool call sequences — requires the same skill as building the agent. Many teams write loose graders that pass anything, then wonder why production quality diverges from eval scores.
- **Your eval set rots.** Production shifts — user intent, data distributions, tool APIs. An eval suite built in January and never touched in June measures a world that no longer exists. Maintenance is part of the system, not an afterthought.
- **Framework-first thinking hides the architecture.** Teams spend weeks debating DeepEval vs. Ragas vs. LangSmith while ignoring the foundational question: what does your layered evaluation system actually look like?

## The move

Build a layered evaluation architecture. Frameworks are downstream of this architecture — they slot into it, they don't replace it.

### The four-layer stack

1. **Offline regression suite** — curated golden dataset, deterministic and programmatic, runs in CI on every prompt or model change. Designed to catch regressions, not to measure absolute quality.
2. **LLM-as-judge layer** — a grader LLM evaluates open-ended quality dimensions (helpfulness, coherence, safety) against a rubric. Use G-Eval or custom rubrics with explicit scoring criteria. Calibrate the judge against human annotations using Spearman correlation — an uncalibrated judge is noise.
3. **Online shadow evaluation** — run the agent in shadow mode alongside production, scoring real traffic without affecting users. Production reveals failure modes your eval set never anticipated.
4. **Human review queue** — triage flagged cases (harmful outputs, low-confidence decisions, novel failure patterns) for human annotation. Feed human labels back to recalibrate the LLM-as-judge.

### Practical mechanics

- **Define task, trial, grader.** Anthropic's taxonomy: a *task* is one test case with inputs and success criteria; a *trial* is one execution (run each task 5–8 times for variance); a *grader* contains one or more *assertions* against the output.
- **Score both trajectory and outcome.** What the agent said it did and what actually changed in the environment are different things. Check end-state correctness (did the file get written? did the API call succeed?) in addition to reasoning quality.
- **Classify failures into categories.** Anthropic's three-class system: *success* (task complete, no harm), *failure* (task incomplete or incorrect), *harmful failure* (task completed but caused damage — this is what production monitoring should flag first).
- **Instrument tool-level observability.** Latency per tool call, cost per step, error rates per tool. An agent that takes 20 seconds because of sequential tool calls can often be sped up with parallelization or a cheaper model.
- **Start with hundreds of evals, then consolidate.** Early-stage teams add evals aggressively. Mature teams narrow to a smaller set tightly coupled to specific product ambitions and critical user journeys.
- **Calibrate before shipping.** Validate grader agreement with human annotators on a held-out set before using the judge to gate deployments.

## Evidence

- **Anthropic Engineering Blog:** "Demystifying evals for AI agents" (Jan 9, 2026) — establishes the task/trial/grader taxonomy, the three-class failure taxonomy (success/failure/harmful failure), and the principle that evaluating agent trajectories requires matching the complexity of the system being measured. Argues that evals make problems visible before they reach users. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **BigData Boutique Blog:** "LLM Evaluation in Production: Frameworks, Metrics, and the Layered System That Ships" (May 2026) — documents the three-layer taxonomy (offline regression, online/shadow evaluation, human-calibrated anchors), notes that framework selection is downstream of architecture decisions, and catalogs the full metric taxonomy: deterministic (exact match, ROUGE, BLEU), rubric (LLM-as-judge with structured rubrics), and composite (RAGAS faithfulness, answer relevancy, context precision). — https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices
- **Hacker News (128 points, July 2025):** Thread on "Principles for production AI agents" — practitioners report that eval suites repeatedly catch prompt tweaks that passed "vibe checks" but failed under systematic evaluation. Commenter roadside_picnic: "If you don't have evals, you really don't know if you're moving the needle at all." — https://news.ycombinator.com/item?id=44712315
- **GitHub / datasops Blog:** "LLM Evaluation in Production — Evals Frameworks, Golden Datasets, and Regression Testing" (May 2026) — details the offline/online divide, golden dataset construction and versioning, DeepEval's 20+ built-in metrics, LLM-as-judge calibration via Spearman correlation against human annotations, and CI/CD regression testing on every PR. — https://www.datasops.com/blog/llm-evaluation-evals
- **GitHub / TribeAI:** "claude-evals" — production eval framework implementing Anthropic's published eval patterns with native SDK hooks into PreToolUse/PostToolUse lifecycle events, a 50-case golden dataset, and one-command model comparison. Built by an Anthropic partner; explicitly designed to fill the gap between Anthropic's published patterns and an operational eval system. — https://github.com/TribeAI/claude-evals

## Gotchas

- **Choosing a framework before designing the architecture.** DeepEval, Ragas, LangSmith, Braintrust — all are tools that go into the system. Teams that pick a framework first often discover it doesn't fit their evaluation layer (e.g., Ragas is specialized for RAG pipelines, not agent trajectories). Design the four-layer system first, then pick tools that fit each layer.
- **An uncalibrated LLM-as-judge.** A judge that hasn't been validated against human annotations produces confident wrong scores. The fix is simple but often skipped: compute Spearman correlation between judge and human labels on a held-out set before using the judge to gate deployments.
- **Testing the happy path only.** Evals heavily weighted toward expected inputs miss the adversarial and edge cases that production surfaces. Include failure-mode cases: malformed inputs, tool API errors, rate limits, ambiguous intent. "Harmful failure" — task completed but caused damage — is the most important class to detect and the easiest to miss.
- **Measuring once and calling it done.** Eval sets drift as production evolves. The teams that get value from evals treat them as a living system:定期 add production edge cases back into the offline suite, recalibrate judges against new human labels, and retire evals that no longer map to real user goals.
- **Ignoring cost and latency as quality signals.** An agent that achieves 95% accuracy but costs 10x more than necessary, or takes 30 seconds per task, is not a quality product. Eval dashboards should include cost-per-task and latency-per-step alongside accuracy metrics.
