# S-1682 · The Agent Evaluation Stack — When Your Agent Loop Runs But Nobody Knows If It's Right

_You shipped the agent. It runs. But no one can tell you whether it's actually working, degrading, or quietly failing in ways that don't surface as errors._

## Forces

- **Agents break differently than software** — individual LLM calls look reasonable; it's the composition that fails. Traditional unit tests pass while end-to-end quality degrades.
- **Probabilistic outputs make assertions fragile** — the same input produces different outputs by design, so exact-match testing is a lie.
- **The gap nobody talks about** — production agents achieve ~60% single-run success, dropping to ~25% across eight runs. Your monitoring shows green because the agent completes the task; it doesn't tell you if the result is wrong.
- **Evaluation is treated as a checklist, not a practice** — teams evaluate thoroughly before launch and stop monitoring post-launch, then watch quality degrade silently for 30–60 days.
- **Academic benchmarks measure base model intelligence, not system behavior** — MMLU, GSM8K, and HumanEval are static snapshots irrelevant to dynamic agent pipelines.

## The Move

Build a layered evaluation infrastructure that treats evaluation as an operational feedback loop, not a pre-launch gate.

### 1. Capture golden datasets from production failures, not synthetic prompts

The highest-value regression test cases are not handcrafted by engineers imagining what might go wrong. They come from actual production failures. Every agent error in front of a real user is a test case you could not have invented: a real input distribution, an authentic edge case, a concrete definition of "broken for this system." The flywheel: **production failure → trace capture → test case → golden dataset → CI/CD release gate**. One team reports that implementing a 50-case golden set with CI regression testing prevented 94% of tool-routing regression incidents within 48 hours.

### 2. Distinguish trajectory metrics from outcome metrics

These two dimensions are decoupled and both matter. **Outcome metrics** measure whether the final result is correct — task completion, output accuracy, error rate. **Trajectory metrics** measure whether the agent's reasoning path was sound — did it use the right tools, in the right order, without excessive backtracking or token waste? An agent can produce a correct answer via a broken reasoning chain, and next time it won't. Track both. Single-run success rate (~60%) is not the same as reliability across runs (~25% over 8 runs).

### 3. Calibrate LLM-as-judge to ≥0.80 Spearman correlation with human judgment

LLM-as-judge gives you scalable automated quality assessment — critical for production volumes. But judges drift. Build domain-specific rubrics (not generic prompts) that align judge outputs with human expert evaluation. Target a Spearman correlation of 0.80+ before trusting judge scores as deployment gates. Use human rubrics on a sampled subset of traces to detect "metric green, user red" situations — where judge scores pass but real users complain.

### 4. Wire evals into CI/CD as deployment gates

Run the full eval suite on every prompt change, model swap, and tool modification. Block deployment if scores drop below baseline. The same infrastructure that evaluates before launch monitors after launch — no separation. Teams without CI gates face weeks of ad-hoc testing when new models arrive; teams with evals determine model fit, tune prompts, and upgrade in days.

### 5. Continuously sample production traffic for ongoing scoring

Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring rather than model capability gaps. Pre-launch evaluation is necessary but insufficient. Sample real production interactions, score them against the same rubric, and alert on score drift. Deloitte found that continuous evaluation reduces production incidents by 67% compared to periodic evaluation.

### 6. Cover the four evaluation levels in parallel

| Level | What it tests | When to run |
|---|---|---|
| **Unit** | Individual LLM calls, tool outputs, prompt templates | During development |
| **Integration** | Agent + tool chains, memory reads/writes, handoffs | Pre-deployment |
| **End-to-end** | Full task completion from user input to final output | Staging and canary |
| **Production** | Real user interactions, sampled and scored | Continuously |

## Evidence

- **Engineering survey (Cleanlab, 2025):** Only 5% of surveyed organizations (1,837 respondents) have AI agents live in production. Among those that do, most remain early in capability, control, and automation maturity. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)

- **Enterprise research (Deloitte, 2025):** Teams that evaluate continuously post-launch experience 67% fewer production incidents than teams relying on periodic pre-launch evaluation. — [thinking.inc/ai-agent-evaluation-production](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)

- **Engineering blog (Arthur, June 2026):** Production failures → Traces → Test Cases → Golden Dataset → Release Gate in CI/CD. The highest-value regression test dataset comes from production failures, not synthetic prompts. A 50-case golden set with CI regression testing prevented 94% of tool-routing regression incidents within 48 hours. — [arthur.ai/regression-test-datasets](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

- **Industry analysis (Gartner, cited 2026):** Over 40% of agentic AI projects will be canceled by end of 2027; a significant share of those failures trace to inadequate evaluation infrastructure, not model capability gaps. — [galileo.ai/agent-evaluation-framework](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

- **Developer tool (Zalor, HN Show, 2025):** Automated agent testing platform targeting the specific failure mode where prompt changes or model swaps silently degrade quality on edge cases. — [news.ycombinator.com/item?id=47270208](https://news.ycombinator.com/item?id=47270208)

- **Open-source framework (agent-skills-eval, HN Show, 2025, 79 points):** Compares with-skill vs. without-skill agent runs. Tool-call assertions identified as the most objective measurable signal for detecting whether agent skills actually improve outputs. — [github.com/darkrishabh/agent-skills-eval](https://github.com/darkrishabh/agent-skills-eval)

## Gotchas

- **Treating evaluation as a one-time pre-launch checklist.** Agents degrade silently — quality drift within 30–60 days post-launch is the norm, not the exception. Eval must be continuous.

- **Running only outcome metrics.** If trajectory degrades but outcomes stay passable for a while, you'll miss the warning. An agent can produce correct outputs via increasingly broken reasoning chains — until it doesn't.

- **Using academic benchmarks as proxy for production behavior.** MMLU, GSM8K, and HumanEval measure base model knowledge, not tool-use reliability, memory consistency, or multi-step planning under real input distributions.

- **Golden datasets that never update.** A static golden set from January reflects the input distribution of January. Production inputs drift, adversarial users discover new edge cases, and your regression suite becomes a false sense of security if it isn't fed from production failures.
