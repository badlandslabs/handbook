# S-899 · The Trajectory Blind Spot — When Your Agent Gets It Right for the Wrong Reasons

Your agent passes every test. It produces correct outputs, hits your accuracy threshold, and your eval suite goes green. Three months later, a 180-step run silently drifts off-course because nobody was watching the path — only the destination. Standard evaluation catches wrong answers. It misses the 17% of multi-step failures that come from process breakdowns: step repetitions, reasoning-action mismatches, and silent intent-execution gaps. Trajectory evaluation is the discipline that closes this gap.

## Forces

- **The output trap.** Output accuracy is easy to measure and easy to trust. Trajectory quality is harder to define, harder to instrument, and nobody asks for it until the incident report lands.
- **Eval inflation.** 89% of teams with agents in production have some form of observability, but only 52% have proper evaluations — and most of those evaluate outcomes, not processes. Most agentic AI projects that fail (Gartner projects 40%+ cancellation by 2027) don't fail because the model was wrong; they fail because nobody caught the drift.
- **LLM-as-critic has a credibility problem.** On HN, engineers repeatedly note they've "never seen empirically validated" results from LLM-as-judge for agentic evaluation. It's convenient, but it's also circular — the same model being evaluated is grading itself.
- **The per-step vs. per-trajectory gap.** Turn-by-turn evaluation misses the most dangerous failure mode: a session that looks fine at each step but fails as a whole. Cekura's team gave the canonical example — a banking agent where the user fails identity verification in step 1 but the agent hallucinates credentials and proceeds anyway. Every individual turn looks correct. The session fails catastrophically.

## The move

Build a three-level evaluation stack that measures trajectory quality, not just task success.

**Level 1 — End-to-end: Did the task succeed?**
- Pass@k: if you run the same task k times, does at least one attempt succeed? (Handles non-determinism.)
- Task completion rate across a golden dataset — not just final output accuracy, but verified against ground truth at each critical state change.
- Cost-aware pass rate: a $50 correct answer is not the same as a $0.05 correct answer.

**Level 2 — Trajectory: Was the path reasonable?**
- Step efficiency: ratio of necessary steps to total steps. Track tool-call counts and retry loops per session.
- Step repetition rate: ~17% of multi-step agent failures are step repetitions (ArXiv 2605.01604, May 2026). Flag sessions where the agent re-executes the same action 2+ times consecutively.
- Reasoning-action alignment: at each step, did the agent's stated reasoning match its action? Instrument with causal logging — not just "tool X was called with output Y," but "at step T, intent Z was stated, action W was executed, deviation detected: [reason]."
- Tool call sequence fidelity: use `superset` mode (agent must call at least the required tools, additional calls OK) for flexibility; use `subset` mode (no extra tools) when efficiency is a requirement. These are not the same threshold.

**Level 3 — Component: Which specific part broke?**
- Tool correctness: did the agent call the right tool? With the right arguments?
- Argument correctness: did the parameters match what the tool expected?
- Plan adherence: did the agent follow its own plan? Deviation from plan mid-execution is an early warning signal.
- Faithfulness: did the agent's reasoning trace actually drive its actions, or did it confabulate a post-hoc justification?

**Instrument traces as the backbone.** Every metric must tie back to a specific trace span. Without causal tracing, a low score tells you something failed — not where or why. Tracing also surfaces new failure modes that your golden dataset didn't anticipate. The elite teams (top 15%) that achieve 2.2× better reliability than average teams all share trace-instrumented evaluation loops.

**Separate deterministic checks from LLM-as-judge.** Deterministic checks (exact-match, schema validation, tool call sequence matching) are reliable for things you can specify precisely. Reserve LLM-as-judge for reasoning quality, plan quality, and faithfulness — things that require judgment. Don't use LLM-as-judge as your primary signal for correctness; calibrate it against human review, especially during the first 30 days of a new eval.

## Evidence

- **HN Ask thread (47301395):** Engineers report that the "dashcam analogy" applies — most tools record what happened (tool X called, output Y) but not why the agent deviated from the plan. The useful question is "at step T, stated intent was Z, executed W — was that model drift, context window issue, or tool failure?" — [HN Ask thread: "How are you monitoring AI agents in production?"](https://news.ycombinator.com/item?id=47301395)
- **arXiv 2605.01604 (Mukund Pandey, May 2026):** Documents that existing benchmarks (HELM, MT-Bench, AgentBench, BIG-bench) are designed for controlled single-session settings and miss production failure modes: compounding decision errors, tool failure cascades, and non-deterministic drift. Proposes a three-layer framework: foundational observability, multi-dimensional benchmarking, automated eval pipeline. Reference implementation at [github.com/mukund1985/llm-eval-toolkit](https://github.com/mukund1985/llm-eval-toolkit)
- **Confident AI (DeepEval):** Documents the 12+ core metrics for LLM agent evaluation: task completion, step efficiency, argument correctness, tool correctness, plan adherence, plan quality, reasoning quality, answer relevancy, faithfulness, safety, latency, and cost. Emphasizes that evaluating end-to-end is necessary but not sufficient — trajectory-level and component-level checks are required to pinpoint regressions. — [LLM Agent Evaluation Metrics 2026 — Confident AI](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **Galileo AI benchmark survey (Feb 2026):** 72% of organizations have deployed agents; only 11% at production scale; 6% fully trusting agents for core processes. Elite teams (top 15%) achieve 2.2× better reliability through systematic eval practices. Teams with formal eval frameworks deploy model upgrades in days vs weeks. — [AI Agent Evaluation: Key Methods & Insights — Galileo](https://galileo.ai/blog/ai-agent-evaluation)
- **HN "600 agent evals" thread (47429739):** Direct empirical result from a real eval run: steering hooks hit 100% accuracy vs 82% with prompts alone — demonstrating that instrumentation-based eval can surface actionable gaps that output-only evaluation misses entirely.
- **Arthur AI HN launch (45804578):** Lead engineer at Arthur AI documents that the transition from "functionally complete" to "reliable" is where most teams stall. Traditional SDLC doesn't work for probabilistic agent systems. Proposes the Agent Development Lifecycle (ADLC) methodology centered on iteration and experimentation against structured eval data. — [HN: The Agent Development Lifecycle — Arthur AI](https://news.ycombinator.com/item?id=45804578)

## Gotchas

- **The output-accuracy illusion.** If you only measure final output correctness, you're blind to the ~31% of multi-step failures that are process failures (17.14% step repetitions + 13.98% reasoning-action mismatches). The agent gets the right answer sometimes, for the wrong reasons — and you won't know which until something breaks silently in production.
- **Turn-level evaluation misses session-level failures.** Every individual turn can look correct while the full session fails (the Cekura banking-agent failure pattern). Evaluate at the session level for conversational agents; evaluate at the trajectory level for autonomous task agents.
- **Golden datasets rot.** If your golden dataset isn't versioned alongside your agent and your eval harness, it silently becomes misaligned. Cases that were hard 6 months ago may be trivially solved now; cases that were easy may have become edge cases. Pin your dataset to your agent version.
- **LLM-as-judge is circular without calibration.** The model being evaluated grading itself is convenient but unreliable. Calibrate against human review, especially for the first 30 days of any new eval category. Treat LLM-as-judge scores as directional signals, not ground truth.
- **No trace, no post-mortem.** Without causal structure in your logs (intent + action + deviation flag at each step), post-mortems become timestamp correlation and guesswork. Instrument intent at each step before you need to debug a 180-step failure.
