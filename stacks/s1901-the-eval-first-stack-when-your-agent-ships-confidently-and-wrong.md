# S-1901 · The Eval-First Stack — When Your Agent Ships Confidently and Wrong

You ran the agent against five test cases. All passed. You shipped. Three weeks later a customer reports it sent a 50% discount nobody approved — and your dashboards showed green the whole time. Your agent isn't failing loudly. It's succeeding at the wrong thing, and you have no eval suite to catch it. This is the eval-first failure: evaluating last instead of first, and paying for it in production.

## Forces

- **Classical NLP metrics don't apply.** BLEU and ROUGE score static text; agents produce trajectories — sequences of tool calls, intermediate states, and reasoning steps. A perfect final-answer score means nothing if the path to get there burned tokens on wrong detours.
- **Aggregate scores hide catastrophic cases.** A judge averaging 8/10 across 200 runs looks healthy while silently failing on 15% of requests that matter most. "Thinking fast and failing slow" is the dominant failure mode.
- **Synthetics don't match production distribution.** Prompt-generated test cases cover the developer's imagination, not the user's. Real production traces are the only reliable source for the eval set that actually predicts what breaks.
- **Evals without golden sets are uncalibrated.** An LLM-as-judge without a human-annotated holdout is a confidence-building fiction — it scores relative to itself, not to correctness.
- **Agent evaluation compounds accuracy failure.** Every step in a trajectory can introduce error. A 95% accurate tool call followed by a 95% accurate synthesis means ~90% end-to-end reliability — worse than either number suggests in isolation.

## The move

**Write evals before you write the agent. Let failing evals drive development. Never ship without a regression suite.**

### 1. Build the golden dataset first

The single highest-leverage investment in an evaluation program is a curated set of 200–500 examples drawn from real production traffic, annotated by domain experts. No eval harness beats a bad golden set. Guidelines from BigDataBoutique, LangSmith docs, and InfoQ all converge:

- Sample the first 500 rows directly from production traces (via Langfuse, Phoenix, or LangSmith export)
- Annotate with correct outputs by a human domain expert — not the LLM
- Use LLM-generated synthetic examples for **coverage of rare edge cases and adversarial inputs** only; swap them out as real examples accumulate
- Maintain the set as a living artifact: add every production failure as a new test case

```
# Typical export from Langfuse production traces
from langfuse import Langfuse
client = Langfuse(public_key=..., secret_key=...)
traces = client.generations.list(
    from_date=datetime.utcnow() - timedelta(days=7),
    tags=["production"]
)
# Filter for failures, annotate, add to eval dataset
```

### 2. Run a three-tier eval architecture

Multiple sources describe this layered model independently:

- **Tier 1 — Heuristics on every span** (zero-cost, always-on): Format checks, token-count guards, response-schema validators. Catches syntax and obvious policy violations instantly.
- **Tier 2 — Distilled judges on a sample** (medium cost): LLM-as-judge running rubric decomposition (3–5 binary checks) against a 5–10% sample of production traffic. Produces trajectory quality scores without scoring every span.
- **Tier 3 — Humans on the gold-set** (expensive, periodic): Human-calibrated judges on the 200–500 annotated examples. Used to **calibrate the Tier 2 judges**, not to score production directly.

From FutureAGI (2025): *"heuristics on every span, distilled judges on a sample, humans on the gold-set. Three-tier stack that scales."*

### 3. Use rubric decomposition, not absolute scores

The pattern that appears across LangSmith, BigDataBoutique, and InfoQ: decompose the judgment into 3–5 independent binary checks rather than a single 1–10 scale.

Instead of: *"Rate the agent's response quality 1–10"*

Do: Each check separately → `[✓] Used correct tool` · `[✓] Tool arguments well-formed` · `[✗] Recovered from error appropriately` · `[✓] Final answer matches task intent`

This decomposition is what distinguishes "wrong answer for the right tool" from "right answer for the wrong evidence" — different failures requiring different fixes.

### 4. Mitigate judge bias explicitly

LLM-as-judge has documented systematic biases. The mitigations, cross-referenced across multiple sources:

- **Position bias**: Run pairwise comparisons twice with positions swapped; discard ties
- **Length bias**: Verbose outputs score higher than concise correct ones — normalize or penalize length
- **Self-preference bias**: Use a different model family than the generator for the judge
- **Calibration drift**: Run the judge against the human-annotated gold-set monthly; discard if correlation drops below 0.8

### 5. Block deploys on eval regressions

Evaluation-Driven Development (EDD) — write the suite first, block merges on score drops. The AgentMarketCap (2026) analysis found this pattern now operational at enterprise scale using Braintrust, LangSmith, or Arize Phoenix in CI:

- Every PR runs the full eval suite against the golden dataset
- Score drop > 2% on any rubric dimension blocks merge
- Failing production traces auto-annotate and join the dataset

## Evidence

- **LangSmith docs (LangChain):** Eval workflow: create dataset → run offline evals before shipping → add failing production traces to dataset → validate fixes → redeploy. Describes the feedback loop as the core eval primitive. — [docs.langchain.com/langsmith/evaluation](https://docs.langchain.com/langsmith/evaluation)
- **BigDataBoutique blog:** Documents "Thinking Fast and Failing Slow" — aggregate judge scores look fine while critical cases fail. Mitigation: rubric decomposition into 3–5 binary checks, pairwise comparisons with position swap, human holdout calibration. — [bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **InfoQ (March 2026):** "Agents are systems, not models." Five eval components: tasks → trials → trajectory → outcome → graders. Three grader families: human, code-based, model-based. Agents compound accuracy failure end-to-end. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **FutureAGI blog (2025):** Three-tier eval architecture: "heuristics on every span, distilled judges on a sample, humans on the gold-set." — [futureagi.com/blog/llm-as-judge-best-practices-2026](https://futureagi.com/blog/llm-as-judge-best-practices-2026)
- **AgentMarketCap (2026):** EDD pattern: "write your evaluation suite first. Run it on every pull request. Block the merge if scores drop." — [agentmarketcap.ai/blog/2026/04/07/agent-evals-cicd-braintrust-langsmith-arize-phoenix](https://agentmarketcap.ai/blog/2026/04/07/agent-evals-cicd-braintrust-langsmith-arize-phoenix)
- **HN discussion on "Principles for Production AI Agents" (app.build, July 2025):** Commenter: "Over, and over again my experience building production AI tools has been that evaluations are vital for improving performance. A tweak to a prompt passed an initial vibe check, but when run against the full eval suite, clearly performed worse." — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **Arize Phoenix / Langfuse docs:** Agent eval metrics: outcome (task success, final-answer correctness) + process (tool-call accuracy, trajectory quality, groundedness) + operational (latency, cost per task, safety/policy adherence).

## Gotchas

- **A passing eval suite does not mean the agent is safe to ship.** A 95% pass rate hides the 5% that might be your highest-stakes cases. Run targeted evals on your PII-handling, financial, and safety-critical paths separately.
- **Golden datasets go stale.** User behavior shifts, products change, model updates alter tokenization and output distribution. A dataset curated 6 months ago may not reflect current production distribution. Re-annotate quarterly.
- **Judging the trajectory is harder than judging the output.** A trajectory might call the wrong tool, then recover cleverly and still produce the right answer. Binary outcome checks miss this; you need process-level rubric checks to catch it.
- **LLM-as-judge on your own output is circular.** Using the same model family for both generator and judge introduces family-bias that systematically over-rewards the output. Use a different model for the judge.
- **Cost and latency are first-class eval dimensions.** Teams that only eval quality will ship agents that are correct, slow, and expensive. Include operational metrics in every eval run, not just quality metrics.
