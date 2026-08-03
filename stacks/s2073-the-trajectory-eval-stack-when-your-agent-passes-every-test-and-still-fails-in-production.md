# S-2073 · The Trajectory Eval Stack — When Your Agent Passes Every Test and Still Fails in Production

You have a suite of evals. The scores are green. You ship a new model or change a prompt, the scores go up, and then production breaks in a way nobody predicted.

## Forces

- **Agents are systems, not functions.** Evaluating them as stateless input→output pairs misses the actual failure modes: wrong tool selected, correct answer reached through wrong reasoning, context lost mid-session.
- **LLM-as-judge is load-bearing but unreliable.** 57%+ of production agent teams now use judge LLMs for quality gating (Zylos Research, 2026), yet empirical testing shows systematic positional bias, labeling effects, and prompt sensitivity — even frontier models prefer "Response B" over "Response A" at measurable rates (CIP, May 2025).
- **Output correctness ≠ trajectory correctness.** An agent can extract the right inventory number from the wrong year's report. A pass/fail on output is blind to process.
- **Golden datasets feel slow but are irreplaceable.** Synthetic data and production traces are necessary at scale, but without a core of hand-curated ground-truth cases, you have no regression baseline.
- **Eval quality is not visible from eval scores.** A high LLM-as-judge score tells you the judge approved — not whether the judge is reliable.

## The Move

**1. Evaluate trajectories, not just outputs.**
Instrument the full execution trace — tool call sequence, intermediate results, decision points — not just the final answer. Catch the silent failure mode where the agent reaches a correct conclusion through a broken process. This requires SDK-level hooks into PreToolUse, PostToolUse, and SubagentStop events (TribeAI's claude-evals pattern).

**2. Layer three eval types in a stack — don't pick one.**
- *Deterministic graders* on golden datasets: slow to build, but no false positives, no circular reasoning. Use for regression gates on contract review, data extraction, classification. Ground-truth labels per case.
- *LLM-as-judge*: fast and scalable for subjective quality, tone, and reasoning coherence. Use with explicit bias probes — swap A/B positions, flip labels, run the same pair twice to measure variance. The judge itself must be evaluated.
- *Human spot-checks*: irreplaceable for edge cases, new failure modes, and calibrating the LLM judge. Target the top 5% of uncertain cases.

**3. Build the golden dataset with a feedback loop.**
Google Cloud's dueling-LLM technique (one LLM as user, one as agent) synthesizes diverse multi-turn conversations at scale. Supplement with anonymized real production traces. Route production failures back into the eval dataset. The dataset is never finished.

**4. Use a systematic improvement loop.**
Run eval → analyze failures (trajectory-level, not score-level) → implement fix → re-run → deploy. Track cost-per-task and latency alongside accuracy — a 2% quality improvement at 4× cost is often a regression.

**5. Calibrate the judge itself.**
Swap the order of responses being judged as a direct probe for position bias. If the verdict flips, the judge is reacting to position, not content. Run judge verdicts against a held-out set with known ground truth before trusting them on unknown cases.

## Evidence

- **HN thread (128 points, July 2025):** A practitioner who worked with a respected AI researcher reports internal experiments found LLMs are not good critics. Counterpoint from Aurornis: eval practices are now standard at scale, but the tension over LLM-as-judge reliability is live and unresolved — [Hacker News #44712315](https://news.ycombinator.com/item?id=44712315)

- **Empirical bias study (CIP, May 2025):** Systematic testing across multiple frontier models found measurable preference for Response B over Response A, plus labeling effects and prompt sensitivity. LLM judges behave more like humans with cognitive biases than deterministic programs — [The Collective Intelligence Project](https://www.cip.org/blog/llm-judges-are-unreliable)

- **Production eval framework (TribeAI claude-evals, 2025):** Implements Anthropic's published eval patterns with native SDK hooks into lifecycle events (not just final output), ships 50-case golden dataset for contract review across 5 categories, supports deterministic grader + LLM-as-judge + human review queue — [GitHub /TribeAI/claude-evals](https://github.com/TribeAI/claude-evals)

- **LLM-as-judge in production survey (Zylos Research, 2026):** 57%+ of surveyed production agent teams use judge LLMs at runtime. Field bifurcated into large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes verification and small distilled judges (Galileo Luna-2 3B–8B, Prometheus 2 7B) for high-throughput inline checking — 97% cost reduction at 0.88–0.95 accuracy. Six distinct patterns identified: offline eval, runtime verifier, self-consistency loops, Reflexion, constitutional AI/RLAIF, inference-time reward models — [Zylos Research](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)

- **Synthetic data with circularity risk (IBM EvalAssist, EMNLP 2025):** IBM researchers identified a key pitfall: criteria derived by model A being judged by model A creates circular validation. Their EvalAssist tool uses user studies with AI practitioners to inform synthetic data generation that avoids this — [IBM Research / ACL Anthology](https://aclanthology.org/2025.emnlp-demos.1)

- **InfoQ article (March 2026):** "Agents are systems, not models — evaluate them accordingly." BLEU and ROUGE are irrelevant to multi-step agentic behavior. Hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis, load testing) with human judgment is non-negotiable. Operational constraints (latency, cost, tool failure recovery) are first-class evaluation targets — [InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

## Gotchas

- **Green eval scores ≠ good agent.** If you're only grading the final output, you miss trajectory failures. A correct answer from the wrong data source is still a failure.
- **LLM judges are confidently wrong.** Position bias, length bias, and self-preference (judging outputs from the same model family more favorably) are documented. Without bias probing, a 90% score may be meaningless.
- **Golden datasets rot.** As your agent's capabilities evolve, old test cases become either too easy (no signal) or stale (context changed). They need maintenance alongside the agent.
- **Synthetic data can encode its own biases.** Duelling-LLM generation tends toward common paths; edge cases and adversarial inputs require targeted manual construction or adversarial LLM probing.
- **Eval cost compounds fast.** Running a full LLM-as-judge eval on 1,000 traces with a frontier judge at $0.01/query adds up. Distilled judges (3B–8B) trade some accuracy for 97% cost reduction — acceptable for inline checking, risky for final gates on high-stakes outputs.
