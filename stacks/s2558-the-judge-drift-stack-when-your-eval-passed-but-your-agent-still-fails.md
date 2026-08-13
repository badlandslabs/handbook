# S-2558 · The Judge Drift Stack — When Your Eval Passed But Your Agent Still Fails

{Your eval suite is green. Your judge model says 94% of agent runs succeeded. You ship. Users report a completely different experience. The judge wasn't measuring your agent — it was measuring how well your agent imitated the judge's own output style. LLM-as-judge has become the dominant approach to scaling agent evaluation, but it carries hidden failure modes that can produce confident, consistent, and completely wrong signals. This is the stack for keeping your judge honest.}

## Forces

- **LLM judges self-prefer their own model family.** GPT-4o consistently rates GPT-4o outputs higher; Claude rates Claude outputs higher. Using the same model for agent and judge introduces systematic upward bias that a green dashboard won't show you.
- **Reasoning style gaming is real and documented.** A 2025 AlphaXiv study found that agents using verbose chain-of-thought formatting — regardless of actual correctness — received substantially higher judged success rates from LLM judges. Style alone shifted scores by amounts large enough to reverse pass/fail decisions.
- **Calibration shifts over time without detection.** Judge models are updated (even silently). Prompts change. Agent behavior changes. Each shift moves the scoring baseline. Without recalibration, your eval trend lines are measuring three different things across time.
- **Aggregate scores mask calibration failure.** A judge scoring 85% this week and 87% next week looks like stability. It could mean 85% and 87% on completely different tasks, with the judge calibrated to neither.

## The move

**Treat your judge like production infrastructure: version it, diversify it, and verify it continuously.**

- **Use judge families, not judge instances.** Combine judges from different model families (Claude Sonnet, Nova Pro, Nemotron) for trajectory evaluation. Each judges a distinct dimension (correctness, reasoning, completeness). Diverse weak signals aggregate more reliably than one strong signal — and you catch self-preference bias at the family level.
- **Recalibrate on every material change.** Judge model updates, prompt changes, system-under-test changes, and new tool versions all shift the calibration baseline. Build recalibration into your release process, not your quarterly review cycle.
- **Validate the judge against human-labeled examples before trusting aggregate metrics.** Run 50-100 hand-labeled cases through both human and judge. If they diverge on >15% of cases, the judge is not ready for production use. Target 500+ cases before trusting aggregate trend lines — this is the minimum for stable metric estimates per multiple 2025-2026 evaluation sources.
- **Prefer pairwise comparisons to absolute scoring.** Pairwise comparisons produce more reliable results because the judge makes a relative decision rather than calibrating an absolute standard. Two outputs, one winner. Lower cognitive burden, lower calibration requirement.
- **Use deterministic metrics for tool call correctness.** Binary tool selection accuracy doesn't need an LLM judge — compute it directly from traces and reserve the judge for nuanced quality dimensions (reasoning coherence, response helpfulness, contextual appropriateness).
- **Separate the judge from the agent model family in CI.** Never use the same model for agent and judge in automated CI. This is the single highest-ROI change to prevent false confidence in your eval pipeline.
- **Monitor judge behavior with synthetic drift probes.** Periodically run known-failure cases through the judge. If the failure rate on your synthetic probes changes by more than 5% between judge versions, flag for recalibration before trusting production metrics.

## Evidence

- **Research paper:** "Gaming the Judge: Unfaithful Chain-of-Thought Can Undermine Agent Evaluation" — Found that reasoning style alone (verbose CoT formatting) systematically biased LLM judges to score identical-quality outputs higher. Demonstrated that agents could game evaluations without improving actual task performance. — [https://arxiv.org/abs/2601.14691](https://arxiv.org/abs/2601.14691)
- **Engineering blog:** Anthropic's "Demystifying Evals for AI Agents" — Recommends combining grader types (code-based, model-based, human) and designing graders that evaluate outcomes not paths. Emphasizes starting with 20-50 simple tasks and that value compounds across the agent lifecycle. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Research survey (KDD '25):** "Evaluation and Benchmarking of LLM Agents: A Survey" (SAP Labs) — Two-dimensional taxonomy of evaluation: objectives (what to measure) and process (how to measure). Classifies 60+ benchmarks and notes that trajectory-level evaluation is essential for multi-step agents — [https://arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)
- **Research brief:** Zylos "LLM-as-Judge Patterns for Agent Evaluation" (2026) — Documents that over 57% of production agent teams use judge LLMs at runtime for quality gating. Core finding: the gap between a naively-configured and well-calibrated judge is wide enough to produce opposite conclusions about agent quality. — [https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns](https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns)
- **GitHub:** AWS Labs "Agentic AI-Guided Evaluation Platform" — Multi-judge jury scoring with judges from different model families evaluating distinct response aspects. Documents how combining diverse judge families reduces self-preference bias. — [https://github.com/awslabs/llm-evaluation-system](https://github.com/awslabs/llm-evaluation-system)

## Gotchas

- **Silent judge updates.** Model providers update judges behind the scenes. Your pass rate can shift 3-8% from a silent update you didn't know happened. Pin judge versions explicitly.
- **Judging the output, not the trajectory.** Agents that take 40 steps to reach a simple answer still look good if the final output is correct. Score the path — tool selection accuracy, step efficiency, and intermediate reasoning quality are where agents fail before the final answer looks reasonable.
- **Over-reliance on a single judge score.** A 92% pass rate tells you nothing about which 8% failed, why, or whether those failures cluster around specific tools, user intents, or error types. Break scores down by failure category from day one.
