# S-2456 · The Production Failure Loop Stack — When Your Agent Evals Don't Catch What Production Does

You built a solid eval suite. Your agent passes every test. It ships. It fails in production on cases your eval set never imagined.

## Forces

- **Synthetics vs. reality** — handcrafted prompts in CI cover only what engineers imagined; real users produce a long tail of phrasings and edge cases no one anticipated.
- **Latency of signal** — traditional software gives fast feedback (500 errors); agent failures surface hours or days later through support tickets or downstream pipeline breaks, so you need a way to run new versions without exposing users while you gather data.
- **Non-determinism is irreducible** — research documents up to 15% accuracy variation across runs on the same input; a single eval run is not a verdict.
- **Three things change at once** — agent deployments couple code, prompts, and model weights; changing any one can break production in ways the others don't catch.
- **Trajectory matters more than answer** — a wrong answer that arrived via good reasoning is less worrying than a right answer that arrived by fabricating data; grading only the output misses the mechanism.

## The Move

Build a **continuous loop** where production failures become release gates. The agent's own deployment loop produces the eval data that protects future deployments.

**The loop:**
1. **Capture** — production failure → trace captured automatically via observability tooling (Langfuse, LangSmith, Braintrust, etc.).
2. **Extract** — the trace becomes a test case: input, expected behavior, observed behavior.
3. **Promote** — hardest 5–10% of failing traces promoted into the golden dataset weekly, tagged by version.
4. **Gate** — the golden dataset becomes a CI/CD release gate; no deploy proceeds if eval regresses.
5. **Monitor** — online evals score real production traffic alongside shadow mode runs.

**Eval layers (per InfoQ/Arthurs):**
- **Offline before deploy** — fixed curated dataset, deterministic, fast; gates releases.
- **Regression in CI/CD** — runs on every prompt/model/tool change; catches regressions before they ship.
- **Online in production** — real traffic scored by automated evaluators; catches distribution shift and failures no dataset anticipated.
- **LLM-as-judge** — a separate model scores agent outputs on quality, safety, tone; used at all three layers.
- **Trajectory evaluation** — not just final answer, but whether each step in the reasoning chain was sound. Pinpoints *where* in the reasoning process failure occurred.

**Gradual rollout as eval infrastructure:**
- **Shadow mode** — duplicate production requests to both current and candidate model; candidate's output is withheld from users and compared offline. Zero user risk.
- **Canary** — 1–5% of live traffic on candidate, scored by online evaluators against a control group. Automatic rollback on regression.
- **Progressive ramp** — gradual traffic increase with continuous monitoring.

**Statistical discipline for sampling (per Maxim's guide):**
- ~246 samples per scenario/slice for 95% confidence, 5% margin, expecting 80% pass rate.
- Adjust upward for multi-turn agent simulations, language variants, and high-risk categories.

## Evidence

- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" (Jan 2026) defines the core vocabulary — tasks, trials, graders, transcripts, evaluation harness, evaluation suite — and argues eval value compounds over the agent lifecycle. Evals make behavioral changes visible *before* they affect users. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Industry article:** InfoQ's "Evaluating AI Agents in Practice" (March 2026) documents that classical NLP benchmarks (BLEU, ROUGE) and single-turn accuracy don't capture how agents fail in practice. Recommends hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis) with human judgment. — [URL](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Product blog:** Arthur's "How to Build Regression Test Datasets for AI Agents From Production Failures" (June 2026) articulates the core loop: production failure → trace → test case → golden dataset → CI/CD gate. Notes synthetic prompts cover only anticipated cases; production captures the long tail. — [URL](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Engineering blog:** Tian Pan's "Releasing AI Features Without Breaking Production" (April 2026) documents shadow mode, canary, and A/B testing for LLM deployments. Key insight: a model can return HTTP 200 on every request while producing subtly wrong, off-tone, or hallucinated outputs. — [URL](https://tianpan.co/blog/2026-04-09-llm-gradual-rollout-shadow-canary-ab-testing)
- **Community talk:** Nimrod Busany's "From Guesswork to Greatness: Systematic AI Agent Optimization in Production" (Agents in Production 2025) observes that teams typically test only one configuration out of countless possible combinations. Evaluation tools are built for single-point assessments, not multi-dimensional comparisons across cost, latency, and accuracy simultaneously. — [URL](https://home.mlops.community/public/collections/agents-in-production-2025-2025-07-23)

## Gotchas

- **Eval set drift** — offline scores stay flat while production complaints diversify; the eval set was too easy, too clean, or too synthetic. Fix: sample failing traces weekly and promote the hardest 5–10% into the eval set.
- **Tool-API drift** — CI mocks a tool call, but the real endpoint changes schema or error shape. The agent retries, the retry loop times out, the agent fabricates a reasonable-sounding answer. Fix: use production-realistic integration tests, not mocks.
- **Single-run false confidence** — a single eval pass on a non-deterministic system is noise. Run multiple trials per task; report variance alongside averages.
- **Grader quality** — LLM-as-judge introduces a second model that can be wrong, biased, or inconsistent. Calibrate the grader separately; don't assume it's ground truth.
- **Happy-path skew** — golden datasets tend to over-represent success cases. Real-world failure rates are higher than eval scores suggest. Weight toward hard and failing cases.
