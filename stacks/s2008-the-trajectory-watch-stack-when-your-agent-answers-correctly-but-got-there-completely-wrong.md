# S-2008 · The Trajectory-Watch Stack — When Your Agent Answers Correctly but Got There Completely Wrong

Your agent returns the right answer. Your metrics say 94% success. Then you pull the trace and find it took 47 tool calls, called the wrong API twice, retrieved the same document three times, and got lucky. Trajectory evaluation — scoring *how* an agent solves a problem, not just the final output — is the practice that separates robust agents from lucky ones.

## Forces

- **Output quality hides path quality.** A correct answer via a terrible route is a ticking clock. Next time the same path breaks, you won't know why.
- **Multi-step failure compounds silently.** A 20-step agent with 95% per-step reliability completes end-to-end only 36% of the time (UC Berkeley MAST study). Your 5% per-step failure rate is invisible until it isn't.
- **Production agents face implicit constraints benchmarks don't test.** Research benchmarks (SWE-bench, WebArena) curate tasks retrospectively with well-specified requirements. Production tasks arrive as loosely worded business descriptions with undeclared domain expertise and domain-expert–subjective success criteria.
- **Scaffold matters as much as model.** AlphaEval found that the scaffold (how you wire tools, prompts, and orchestration) contributes as much to agent performance as the underlying model itself. Changing your prompt library can matter more than swapping the LLM.
- **Six failure modes are invisible to coding-centric benchmarks.** AlphaEval's production-grounded evaluation of 94 real-world tasks across six O*NET domains identified failure patterns that standard benchmarks entirely miss.

## The Move

Evaluate agents on four dimensions, not one. A single aggregate score tells you an agent got worse; a per-dimension score tells you *where*.

### The Four Evaluation Dimensions

| Dimension | What It Answers | What to Measure |
|---|---|---|
| **Trajectory** | Did the agent take a sensible path? | Step count, unnecessary tool calls, loops/retries, required steps present, correct ordering |
| **Tool Use** | Did it call the right tools correctly? | Correct tool selected, argument validity, no hallucinated tool calls |
| **Task Completion** | Did the user's goal actually get met? | End-to-end success rate, partial completion rate, error types |
| **Multi-turn Quality** | Does quality hold across conversation? | Consistency, context retention, graceful degradation with history length |

### Score Trajectories, Not Just Answers

- **Trajectory-level scoring** (LangFuse, Phoenix/arize-ai): instrument each agent step. Track step count, tool call sequences, branching decisions, and loop detection. A trajectory with 20 tool calls for a 3-step task is a signal even if the final answer is right.
- **Token-to-action ratio**: tokens consumed per meaningful action. Ratios below 0.3 (where 0.3 means 1 meaningful action per ~3 tokens of reasoning/calling) indicate wasted deliberation or looping.
- **Golden traces + CI regression**: maintain a dataset of reference trajectories for critical paths. Every change to prompt, model, or scaffold re-runs the full dataset. Models are stochastic — flaky pass/fail on critical scenarios means re-running, not trusting one result.

### Instrument the Failure Modes Production Creates

AlphaEval (GAIR-NLP, April 2026) evaluated 94 production tasks sourced from seven companies across six O*NET domains (HR, Finance, Procurement, Software Engineering, Healthcare, Technology Research). Best overall score: 64.41/100 (Claude Code + Opus 4.6). The paper identifies six production-specific failure modes invisible to coding benchmarks:

1. **Cascade dependency** — early-step errors compound downstream; the agent doesn't realize step 3 built on a wrong assumption from step 1
2. **Subjective judgment collapse** — agent produces a confident, well-formed answer that a domain expert would reject as wrong
3. **Information retrieval failures** — agent retrieves wrong or stale documents, or fails to retrieve when needed, with no signal from the final output
4. **Cross-section logical inconsistency** — agent contradicts itself across sections or turns; internally inconsistent reasoning dressed up in confident prose
5. **Constraint misinterpretation** — agent ignores an implicit requirement (compliance rule, format constraint, jurisdiction) never stated explicitly in the prompt
6. **Format compliance failures** — output technically correct but fails the actual required schema, template, or regulatory format

### Build the Offline → Online Eval Loop

**Offline eval** (before shipping): run agent on curated datasets that include your known failure cases. Use deterministic code checks for anything decidable (schema validity, format compliance), LLM-as-judge for semantic quality, and rubric-based assessment for subjective dimensions. Covers: does this change break what worked before?

**Online eval** (production traffic): sample live traces and score a percentage automatically. Flag trajectories that hit known failure patterns (loop detection, excessive tool calls, context collapse). Route human review to flagged traces — don't try to human-review everything.

**The agent improvement loop**: early test datasets are small and synthetic. As production behavior accumulates, real-world failure examples get added to the eval dataset. Coverage grows organically to match the complexity of actual interactions.

### Monitor Operating Envelopes, Not Just Quality

Track cost-per-task and latency alongside quality scores. Agents can "succeed" by burning 10× the expected token budget. Define SLOs for:
- Tokens per task (alert on >3× baseline)
- P99 latency (dominated by retries, tool calls, reasoning loops — not base model speed)
- Step count ceiling (hard limit with escalation or timeout)
- Tool call success rate per tool (detect degraded endpoints before they cascade)

### Human Calibration for LLM-as-Judge

LLM judges are fast and scalable but drift. Calibrate by running human rubrics on a 5–10% sample of traces, comparing human scores to judge scores. If the judge is consistently "metric green, user red," retune the rubric. Human review and automated scoring are complementary — not substitutes.

## Evidence

- **AlphaEval (arXiv:2604.12162, April 2026):** Production-grounded benchmark of 94 tasks from 7 companies, 6 O*NET domains. Best agent scores 64.41/100. Key finding: scaffold matters as much as model, and six production-specific failure modes are invisible to research benchmarks. — [https://arxiv.org/abs/2604.12162](https://arxiv.org/abs/2604.12162)
- **LangFuse engineering guide:** Four-dimension eval framework (trajectory, tool use, task completion, multi-turn). Offline evals catch regressions before shipping; online evals on production traffic catch failures offline evals miss. — [https://langfuse.com/resources/engineering/ai-agent-evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)
- **Confident AI (DeepEval) guide:** Token-to-action ratio < 0.3 indicates looping; operating envelopes (cost, latency, step budgets) must be tracked in the same traces as quality scores; human rubrics on sampled traces calibrate LLM-as-judge. — [https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

## Gotchas

- **Don't trust final-answer pass rate alone.** A 90% end-to-end success rate can mask that 40% of tasks took 5× longer than baseline and 15% produced internally inconsistent reasoning. Break out trajectory and tool-use dimensions separately.
- **Benchmarks measure task completion, not trajectory quality.** AlphaEval showed that best-in-class agents on SWE-bench score 64.41/100 on production tasks — a 35-point gap. Your benchmark score is a ceiling estimate for production, not a floor.
- **LLM-as-judge needs calibration, not trust.** Judges are useful for scale but will systematize their own biases. Run human review on a sample to catch "metric green, user red" cases before they become accepted as ground truth.
- **Changing scaffold can matter more than changing model.** AlphaEval's finding that scaffold contributes as much as model means your prompt engineering and tool-wiring work deserves the same eval rigor as your model selection.
