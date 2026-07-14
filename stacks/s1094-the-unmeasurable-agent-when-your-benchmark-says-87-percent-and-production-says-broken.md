# S-1094 · The Unmeasurable Agent — When Your Benchmark Says 87% and Production Says Broken

Your test suite passes. Your benchmark reports 87%. You shipped on Friday. By Monday, your agent is hallucinating tool calls, retrying failed APIs in infinite loops, and burning 50x your per-task budget estimate. The benchmark score was real. The production failure was also real. The problem is that you were measuring the wrong thing.

This is the agent evaluation problem: the methods inherited from LLM evaluation — single-turn scoring, accuracy on curated datasets, leaderboard rankings — don't capture what matters when an autonomous system makes multi-step decisions in the real world. Evaluating an agent is not evaluating a model.

## Forces

- **Agents are trajectories, not outputs.** A single agent task spans 5–20 tool calls, each branching the execution path. Evaluating only the final output misses where the agent went wrong along the way — and whether it got there by accident or skill.
- **Benchmarks measure the wrong thing.** AlphaEval (Lu et al., arXiv:2604.12162) evaluated agents on 94 real production tasks from 7 companies across 6 O*NET occupational domains. The best-performing agent scored 64.41/100 on actual production requirements. Standard benchmarks (WebArena, GAIA, AgentBench) were designed for controlled lab settings with retrospectively curated tasks — not the implicit constraints and expert-judged deliverables of real deployment.
- **Scaffold choice matters as much as model choice.** The AlphaEval finding — that scaffold architecture (how the agent chains tools, manages state, and handles errors) affects score almost as much as the underlying model — means you can't fully evaluate an agent by swapping models. You have to evaluate the whole system.
- **Standard metrics are blind to production failure modes.** A May 2026 paper (Pandey, arXiv:2605.01604) on billion-event-scale deployments identifies seven production-specific failure modes that ROUGE, BERTScore, and accuracy metrics systematically miss: compounding decision errors, tool failure cascades, non-deterministic output drift, and more.
- **LLM-as-judge is necessary but not sufficient.** Rubric-based LLM scoring scales evaluation but introduces bias and positional effects. Teams need to calibrate judges to 0.80+ Spearman correlation with human judgment — a bar most teams never formally target.

## The Move

**Measure trajectories, not just outcomes — and build a rubric hierarchy your whole team agrees on.**

- **Separate trajectory metrics from outcome metrics.** Trajectory metrics assess the agent's reasoning and decision process (did it call the right tool? in the right order? recover appropriately from failure?). Outcome metrics assess the final result (did it accomplish the task?). Track both; they can diverge.
- **Build a 3-tier evaluation rubric.** Per Galileo AI's evaluation framework: 7 top-level dimensions → 25 sub-dimensions → ~130 specific items. This gives evaluators clear anchors and makes scoring consistent across trials and reviewers.
- **Calibrate LLM-as-judge against human judgment, then lock the rubric.** Run 20–30 sample evaluations with human judges first. Compute Spearman correlation. Iterate the rubric until the judge hits 0.80+ correlation. Only then run automated scoring at scale. Re-calibrate periodically — judge quality drifts.
- **Build regression evals into CI/CD.** Trigger evaluation on commit, on schedule, and on business events (model upgrade, tool schema change, prompt revision). The goal is to catch behavioral regressions before they reach users, not after. Amazon's agent deployment lessons note that teams who skipped CI-triggered evals spent 3–5x more time on production incidents.
- **For multi-agent systems, add structured human-in-the-loop (HITL) evaluation.** Amazon's production guidance: automated metrics fail to capture emergent coordination failures between agents — where two agents produce logically consistent individual outputs but a contradictory collective recommendation. HITL is essential for validating inter-agent communication, conflict resolution, and collective goal alignment.
- **Distinguish production-grounded tasks from curated benchmark tasks.** Production-grounded evals use real inputs, expert-judged success criteria, and implicit constraints from actual systems. Curated benchmarks are useful for regression but will systematically overestimate production capability. Use both as gates, not alternatives.

## Evidence

- **Research paper (AlphaEval, arXiv:2604.12162):** Production-grounded benchmark of 94 tasks across 6 O*NET domains — best agent scores 64.41/100. Key finding: scaffold choice affects performance nearly as much as model choice, and lab benchmarks systematically overestimate production capability. — [arXiv:2604.12162](https://arxiv.org/abs/2604.12162)
- **Research paper (Pandey, arXiv:2605.01604):** Taxonomy of 7 production failure modes for agentic AI systems operating at billion-event scale. Documents that standard metrics (ROUGE, BERTScore, accuracy) fail to detect failure modes unique to production: compounding errors, tool failure cascades, and output drift. — [arXiv:2605.01604](https://arxiv.org/abs/2605.01604)
- **Engineering blog (Anthropic, Jan 2026):** Demystifying Evals for AI Agents — distinguishes tasks, trials, and graders; defines trajectory evaluation (assessing the full sequence of decisions) vs. outcome evaluation; recommends building eval harnesses that match the complexity of the system measured. — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Engineering blog (AWS/Amazon, Feb 2026):** Real-world lessons from thousands of agent deployments since 2025. Documents why black-box final-output evaluation fails for agents; emphasizes full-lifecycle visibility, HITL for multi-agent coordination, and regression pipelines as standard practice. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **GitHub (LangChain agentevals):** Open-source trajectory evaluation package supporting two modes: trajectory match (hard-coded reference path comparison) for well-defined workflows, and LLM-as-judge (rubric-based flexibility) for assessing decision quality without strict ordering. — [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals)
- **Open-source framework (DeepEval):** Reports 100M+ daily evals run by 150K+ developers, >50% Fortune 500 adoption. Pytest-native unit testing for LLMs and agents with trajectory evaluation support and G-Eval metric. — [confident-ai/deepeval](https://github.com/confident-ai/deepeval)
- **Community discussion (HN Ask, ~2025):** Practitioners report rolling their own orchestration rather than using frameworks — existing frameworks deemed insufficient for production control. Common theme: evaluation tooling is the missing piece everyone is building internally. — [HN Ask HN: Multi-agent orchestration](https://news.ycombinator.com/item?id=47660705)

## Gotchas

- **Don't benchmark once and ship.** Agent behavior degrades non-linearly as context accumulates, tools change, and upstream data sources drift. Evaluation is continuous, not one-time.
- **Don't trust a benchmark score without understanding what it measures.** An 87% on a curated benchmark may reflect performance on well-specified tasks that production never presents. The gap to 64.41/100 on production-grounded tasks is your real performance range.
- **LLM-as-judge introduces its own failure modes.** Positional bias (the judge favors responses in certain positions), verbosity bias (longer answers score higher), and self-preference bias (a judge of the same model family favors its own outputs) are well-documented. Calibrate before scaling.
- **Trajectory match is brittle for flexible agents.** If your agent has genuine latitude in how it accomplishes tasks, hard-coded trajectory comparison will produce false negatives. Reserve it for well-defined workflows; use LLM-as-judge for open-ended tasks.
