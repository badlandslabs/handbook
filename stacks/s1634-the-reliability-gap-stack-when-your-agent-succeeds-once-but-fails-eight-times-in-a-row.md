# S-1634 · The Reliability Gap Stack — When Your Agent Succeeds Once but Fails Eight Times in a Row

Your agent scores 60% on its first run. Impressive. You run it again. Then a third time. By the eighth attempt it's at 25%. Your single-run benchmark told you the agent was production-ready; the multi-run reality tells a different story. The gap between single-run task success and consistent multi-run performance is where agents quietly fail in production — and where most evaluation frameworks never look.

This is the reliability gap: the difference between whether an agent can solve a task and whether it will solve it reliably, every time, under the stochastic conditions of a live system.

## Forces

- **Single-run benchmarks are survivorship fiction.** Most published benchmarks test one attempt per task. An agent that gets lucky once counts the same as one that gets it right consistently.
- **LLM stochasticity hides reliability.** A prompt that works 99% of the time today works 92% tomorrow due to model weight drift or token sampling changes — invisible to endpoint metrics alone.
- **Vibe checks have no statistical power.** Manually testing an agent and concluding it "feels right" is subjective, non-repeatable, and susceptible to confirmation bias. It cannot detect regressions across diverse inputs.
- **Outcome metrics lie about correctness.** An agent can reach the right final state through a policy-violating path (see S-1632) or by lucky guessing. Endpoint scoring marks both as success.
- **Fixing one failure creates others.** Without an eval suite, teams catch regressions only in production, then over-correct, triggering cascading failures.

## The move

Measure consistency, not just completion. Build an evaluation architecture that captures the reliability gap before it becomes a production problem.

**1. Run trials, not tasks.** Each task gets multiple attempts. Report pass-at-K (P@K): what fraction of tasks pass within K attempts. P@1 reveals ceiling; P@8 reveals floor. If P@1 minus P@8 exceeds your threshold, reliability is your problem, not capability.

**2. Tier your evaluation dimensions.** Separate what you're measuring:
   - **Outcome metrics** — Did the agent reach the correct final state? (binary or rubric)
   - **Trajectory metrics** — Did the agent take a safe, efficient, policy-compliant path? (see S-1632)
   - **Consistency metrics** — Does it produce the same result across N runs with identical inputs?
   - **Behavioral metrics** — Did the agent call the right tools, hallucinate citations, violate guardrails?

**3. Use LLM-as-judge with a calibrated rubric.** Don't rely on single-judge scoring. Target 0.80+ Spearman correlation with human judgment by:
   - Providing the judge with a structured rubric (criteria, not just "is this good?")
   - Using chain-of-thought prompting so the judge explains its reasoning
   - Running the judge against a human-labeled golden set to establish baseline correlation
   - Combining multiple weak signals from diverse criteria rather than one strong signal

**4. Integrate evaluation into CI/CD.** Treat agent quality like code quality:
   - **Commit-triggered**: Run eval suite on every prompt or tool change, block deployment on regression
   - **Scheduled**: Daily or weekly runs detect drift from model updates you don't control
   - **Event-driven**: Run on production anomalies (user escalation, elevated error rate)

**5. Distinguish discovery from defense modes.** Discovery mode asks "can the agent do this at all?" — it tolerates failure, needs diverse inputs, and uses open-ended evaluation. Defense mode asks "did this change break something?" — it needs a stable baseline, reproducibility, and pass/fail thresholds. Run both, separately, and don't let discovery mode's relaxed standards leak into your defense pipeline.

**6. Budget human review strategically.** Human evaluation is the gold standard but doesn't scale. Use it to:
   - Label golden sets for judge calibration (50-200 samples is often enough)
   - Adjudicate edge cases where automated judges disagree
   - Validate that your rubric matches real-world quality standards

## Evidence

- **Anthropic Engineering Blog:** Defines the eval structure (task / trial / grader / assertion) and argues that evals compound in value over an agent's lifecycle — teams with eval suites adopt new models in days vs. weeks. Also notes that the capabilities making agents useful (autonomy, flexibility) make them harder to evaluate. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Galileo AI:** Documents the empirical reliability gap: agents achieve 60% single-run success but only 25% across eight runs. Notes that over 40% of agentic AI projects will be canceled by end of 2027, and that standard benchmarks miss the reliability challenges that emerge in production. Proposes a 3-tier rubric framework (7 dimensions → 25 sub-dimensions → 130 items). — [URL](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

- **Google Cloud Blog:** Describes the "vibe check trap" — prompts that work 99% of the time today degrade to 92% tomorrow from model drift, invisible to manual testing. Proposes continuous evaluation combining production monitoring, automated LLM-as-judge scoring, and human feedback. Distinguishes discovery mode (raise the ceiling, tolerate failure) from defense mode (protect the floor, block regressions). — [URL](https://cloud.google.com/blog/topics/developers-practitioners/from-vibe-checks-to-continuous-evaluation-engineering-reliable-ai-agents)

- **GitHub Blog (Copilot team):** Runs over 4,000 offline tests before deploying any model change to production, combining automated code quality assessments, chat capability evaluations, LLM-based scoring, and manual testing across multiple languages and frameworks. States explicitly: "Just because a model is newer doesn't mean it will perform better for your use case." — [URL](https://github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot/)

## Gotchas

- **Golden set contamination.** If your LLM-as-judge was trained or fine-tuned on data overlapping with your test set, its scores will be artificially inflated. Check for preference leakage between your judge and your evaluation data.
- **Judge self-preference bias.** A judge from the same family as the model being evaluated tends to score it higher. Use a different model family for the judge role, or use ensemble judging with diverse judge families.
- **Multi-trial inflation.** Running N trials and reporting only the best result makes P@K look great but tells you nothing about reliability. Always report P@1 alongside P@K, and don't cherry-pick which K to report.
- **The rubric drift problem.** As your product evolves, your eval rubric can become misaligned with what users actually care about. Schedule quarterly rubric reviews with product and domain experts, not just engineers.
