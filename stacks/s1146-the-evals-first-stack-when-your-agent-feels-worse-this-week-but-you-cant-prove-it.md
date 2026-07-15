# S-146 · The Evals-First Stack — When Your Agent "Feels Worse This Week" But You Can't Prove It

When you shipped an agent, it worked great in the demo, then silently degraded in production — and your only signal is "users are complaining more."

## Forces

- **Agents break the eval model** — single-turn LLM evals are clean (prompt in, response out, grader scores it). Agent evals involve multi-turn trajectories, tool use, state mutation, and compounding errors. A bad intermediate step can still produce a correct final answer (lucky) or vice versa (catastrophic).
- **Vibe checks are the trap** — manually chatting with the agent feels like testing but is subjective, unscalable, and vulnerable to confirmation bias. It works until it doesn't, and by then you've shipped weeks of regressions.
- **LLM-as-judge has hidden failure modes** — LLMs grading other LLMs sounds cheap and fast, but judges show low confidence near decision boundaries and can be systematically biased. Without calibration, you're measuring the judge's opinion, not your agent's quality.
- **Cost of comprehensive evals vs. cost of bad evals** — running 10,000 RAG traces per day costs ~$200–600/month in judge tokens. But catching a regression before it hits users is orders of magnitude cheaper than the blast radius.

## The Move

Build a layered eval system before you need it — not after the first production incident.

**The eval vocabulary (Anthropic's framing):**
- **Task** = a single test case with inputs and a success definition
- **Trial** = one attempt at a task (run multiple times because outputs are non-deterministic)
- **Suite** = a collection of tasks (representative of a capability)
- **Verdict** = pass/fail from the grader
- **Sampler** = how tasks are selected from the suite for each run

**The three evaluation layers that actually ship:**
1. **Offline regression suite** — pytest-style test cases run in CI before every deploy. Covers known failure cases, critical paths, and regression gates. Fast feedback, small sample.
2. **Online/shadow evaluation** — run the new agent version in parallel with production. Compare outputs side-by-side without affecting real users. Catch drift before it matters.
3. **Human calibration anchors** — small, expensive, high-quality labeled dataset that establishes ground truth. Used to calibrate and sanity-check LLM judges. Without this, you don't know if your automated scores are measuring anything real.

**The three-tool stack (most mature teams use all three):**
- **Promptfoo** — red-teaming and security probing. YAML config, 40+ adversarial plugins (jailbreak, PII leakage, prompt injection). Use for CI security gates and multi-model comparison before shipping.
- **DeepEval** — pytest-native quality metric gates. Covers hallucination, answer relevancy, context precision/recall, toxicity, bias. Best for Python-native teams wanting app-level assertions in CI.
- **RAGAS** — retrieval-layer metrics. Use when answers are wrong and you don't know if the fault is chunking, retrieval, or generation.

**The feedback loop:**
Production traces → eval data → surface regressions → fix → re-deploy. LangFuse and similar tools make this trace-to-improvement cycle systematic rather than accidental.

**Sampling strategy for LLM-as-judge:**
- Route outputs where judges show low confidence (scores near decision boundaries) to human reviewers — focus human effort on genuinely ambiguous cases.
- Use diversity sampling to ensure evaluation datasets don't cluster around obvious cases.
- Calibrate judges against your human anchor dataset; measure and track inter-rater reliability.

## Evidence

- **HN thread (128 pts):** Practitioners consistently report evaluations as "vital" for improving production agents, with skepticism about LLM-as-judge working without empirical evidence. One cited internal experiment found LLM critics produced a false confidence problem. — [Hacker News Discussion](https://news.ycombinator.com/item?id=44712315)
- **Anthropic engineering post:** Claude Code agent development uses formal task/trial/suite/verdict/sampler vocabulary. Key insight: "Mistakes propagate, side effects compound, and even when the trajectory looks ugly the final outcome can still be correct (or vice versa)." — [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Google Cloud blog:** LLM outputs are probabilistic — a prompt at 99% today can drop to 92% tomorrow from model weight shifts or temperature changes. Introduces the Discovery vs. Defense mode split: innovation mode (1–10 inputs, human vibe check) vs. defense mode (50–10,000 inputs, automated evaluation). — [Google Cloud: From Vibe Checks to Continuous Evaluation](https://cloud.google.com/blog/topics/developers-practitioners/from-vibe-checks-to-continuous-evaluation-engineering-reliable-ai-agents)
- **KDD 2025 tutorial:** Two-dimensional taxonomy for LLM agent evaluation: evaluation objectives (what to measure — behavior, capabilities, reliability, safety) vs. evaluation process (how to measure — interaction modes, datasets, metric computation, tooling). — [KDD 2025: Evaluation & Benchmarking of LLM Agents](https://sap-samples.github.io/llm-agents-eval-tutorial)
- **arXiv 2512.12791:** Four-pillar eval framework — LLM Pillar (instruction following, safety/alignment), Memory Pillar (context retention, retrieval quality), Tools Pillar (tool selection accuracy, execution correctness), Environment Pillar (state mutation, side effects). — [arXiv: Beyond Task Completion — Assessment Framework for Agentic AI Systems](https://arxiv.org/html/2512.12791v1)
- **LangFuse 7-stage feedback loop:** Production traces → dataset curation → LLM-as-judge scoring → regression detection → fix → re-deploy → monitor. Cost reference: ~$200–600/month for 10,000 RAG traces/day using judge models. — [LangFuse: Evaluating Agents in Production](https://pub.towardsai.net/langfuse-evaluating-agents-in-production-llm-as-a-judge-datasets-and-the-feedback-loop-3a4d0e8441f4)
- **DeepEval/RAGAS/Promptfoo comparison (2026):** Metric coverage matrix — Promptfoo leads on red-teaming (40+ plugins, jailbreak, PII leakage), DeepEval leads on pytest integration and agent trajectory metrics, RAGAS leads on RAG-specific retrieval metrics with academic methodology. Most mature teams run all three in complementary roles. — [QASkills.sh: DeepEval vs RAGAS vs Promptfoo](https://qaskills.sh/blog/deepeval-vs-ragas-vs-promptfoo-2026)

## Gotchas

- **Don't ship without human calibration anchors** — LLM judges need ground truth to calibrate against. Without this, you're measuring the judge's biases, not your agent's quality.
- **Determinism must be engineered, not assumed** — even with sampling disabled, floating-point arithmetic, kernel scheduling, and MoE routing introduce run-to-run variance. Pin the API version, lock the exact model checkpoint, and version your prompts explicitly.
- **Test design is the hard part, not tool selection** — tools test what you tell them to test. Knowing *what to test*, creating adversarial cases, and building audit-grade eval datasets requires experience beyond running libraries.
- **Cost compounds fast** — comprehensive eval coverage at scale is expensive. Using GPT-4o-mini or Claude 3.5 Haiku as judges cuts costs 60–80% with acceptable trade-offs for non-critical paths.
- **The four pillars are interdependent** — a failing agent can have a good LLM but bad tool selection, or good tools but degraded memory. Evaluations must cover all four pillars (LLM, Memory, Tools, Environment) to catch the real failure mode.
