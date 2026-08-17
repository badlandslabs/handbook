# S-2774 · The Judge Bias Stack — When Your Eval System Is More Wrong Than Your Agent

Your LLM judge gives every agent a B+. Your best agent scores 8.3/10 and your broken one scores 7.9. You shipped the broken one because the numbers said it was fine. Three weeks later it's hallucinating compliance answers. The judge never noticed. This is the LLM-as-judge problem: you built a scalable evaluation system, then gave it systematic blind spots it can't see through.

## Forces

- **LLM judges are proxies, not ground truth.** They measure perceived quality — not actual correctness. A judge that has never seen your domain data will rate confident-sounding wrong answers higher than uncertain-but-accurate ones.
- **Self-preference is measurable and pervasive.** When the judge and the agent share a model family, the judge rates that family's outputs 10-15% higher — a bias visible in controlled experiments with different judge/agent pairings.
- **Length and confidence masquerade as quality.** Longer responses score higher. More authoritative-sounding phrasing scores higher. Structured rubrics without independent criteria conflate these surface features with actual task completion.
- **A single judge gives a single perspective.** Human annotation uses multiple annotators specifically to cancel individual variance. A solo LLM judge carries its own stylistic preferences, sensitivity thresholds, and blind spots into every verdict.
- **The rubric is the product.** Vague prompts like "is this response good? score 1-10" produce noisy, inconsistent judges. Disaggregating quality into independent dimensions with explicit thresholds is the difference between a useful signal and a confidence interval you'll never check.

## The move

### Use structured rubrics, not holistic scores

Replace "score this response 1-10" with independent criteria. Each criterion gets its own judgment, threshold, and weight.

| Criterion | What the judge actually checks | Weight |
|-----------|-------------------------------|--------|
| Factual Accuracy | Claims match retrieved evidence or known ground truth | 25% |
| Task Completion | User's stated and implicit goal was achieved | 30% |
| Tool Fidelity | Only called approved tools with valid arguments | 20% |
| Safety/Compliance | No policy violations, no dangerous recommendations | 25% |

Calibrate thresholds against a golden set of 20-50 human-labeled examples before running at scale. Measure judge accuracy against human labels, not just variance.

### Fight the three systematic biases

**Position bias** — judges favor responses in first or last position depending on task type. Counter it by randomizing order and running each comparison twice with reversed positions. Average the scores.

**Length bias** — judges correlate response length with quality. Include an explicit "length normalization" pass: score both responses controlling for verbosity, or pre-truncate to equal length before judging.

**Self-preference bias** — judge prefers outputs from its own model family. Counter it by using a stronger, unrelated judge model (e.g., using Claude as judge for a GPT agent, or a dedicated judge model like GPT-4o separate from the agent model). Measure the bias explicitly: run your judge against outputs from its own family vs. competitors and report the delta.

### Run multi-agent judges for complex cases

For high-stakes evaluations, use multiple LLM agents as judges — one plays "advocate," one plays "critic," and a third synthesizes. This surfaces disagreements that solo judges paper over. The debate format catches cases where one judge's stylistic preference would have overruled a legitimate critique.

**When this is overkill:** If you're evaluating a simple classification task with a clear right/wrong, use a deterministic grader instead. LLM judges earn their cost on subjective, multi-dimensional outputs.

### Build a golden set and measure judge accuracy

1. Label 20-50 examples by hand — include known edge cases, failures, and successes.
2. Run the judge on the golden set and compute accuracy against human labels.
3. If accuracy < 80%, iterate on the rubric before running at scale.
4. Re-run calibration quarterly or after any model/agent change.

Track judge accuracy over time. A judge that was 87% accurate in January may drift to 72% as your agent changes behavior.

### Combine deterministic and LLM grading

| Dimension | Use this grader |
|-----------|----------------|
| Schema validity, token count, latency | Deterministic (exact match, code) |
| Factual accuracy against known ground truth | Deterministic (retrieval + match) |
| Task completion, helpfulness, policy compliance | LLM judge |
| Reasoning quality, explanation coherence | LLM judge |
| Safety, dangerous content | Deterministic classifier + LLM review |

Use deterministic checks for everything you can measure precisely. Reserve LLM judges for the dimensions that require judgment.

## Evidence

- **Anthropic Engineering:** Agents operate over many turns, making eval fundamentally different from chat response grading. Their recommended approach grades task outcome + environment state + transcript review — not just the final message. — [Anthropic Engineering: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **LLM-as-Judge Bias Research:** GPT-4 exhibits significant self-preference bias when judging outputs from its own model family. Single-LLM judges carry inherent stylistic biases that systematic mitigation (position swapping, length normalization, multi-judge protocols) can reduce but not eliminate. — [GitHub: Judging the Judges — LLM-as-Judge Bias Mitigation](https://github.com/sksoumik/llm-as-judge); [arXiv: Survey on Agent-as-Judge Evaluation](https://arxiv.org/abs/2507.21504)
- **Databricks:** Synthetic data generation for evaluation datasets lets teams build golden sets from proprietary data in hours rather than months of SME labeling. Teams using this approach report reduced time to eval iteration from weeks to days. — [Databricks Blog: AI Agent Evaluation with Synthetic Data](https://www.databricks.com/blog/streamline-ai-agent-evaluation-with-new-synthetic-data-capabilities)
- **Vindler Solutions:** A production team found their agent was "completing" tasks at 95% rate while only 70% were actually correct. The gap was invisible without properly measuring output quality against ground truth — not just task completion status. — [Vindler: Agent Evaluation at Scale — Lessons from 2025's Production Failures](https://vindler.solutions/blog/agent-evaluation-at-scale)
- **Production Eval Practitioner:** Uncalibrated rubric prompts produce judges that conflate length and confidence with quality. Disaggregating rubric dimensions and adding explicit length normalization improved inter-rater agreement with human labels from 61% to 84% in a customer service agent eval. — [Matheus Palma: LLM-as-Judge Evaluation: Rubrics, Calibration, and Production Pitfalls](https://matheuspalma.com/blog/llm-as-judge-evaluation-rubrics-calibration-production)

## Gotchas

- **Judge self-preference is not obvious until you measure it.** Run your judge against outputs from its own model family vs. a competitor and report the delta. If it's >5%, correct for it or switch judges.
- **A judge that scores everything the same is worse than no judge.** If your eval run produces a standard deviation < 0.5 across 200 examples, your rubric is too vague — it's not discriminating. Iterate on the rubric.
- **Synthetic golden sets are only as good as the scenarios they cover.** If your synthetic data misses failure modes, the judge will never learn to catch them. Cover known failure modes explicitly, not just happy paths.
- **Judging the transcript, not just the output, catches path-dependent failures.** An agent that reached the right answer through a dangerous process can look identical to a safe agent on output-only evaluation. Review tool call sequences alongside final answers.
