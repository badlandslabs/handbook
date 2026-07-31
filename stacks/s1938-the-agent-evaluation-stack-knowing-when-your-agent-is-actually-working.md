# S-1938 · The Agent Evaluation Stack

*When you've built an agent that "seems to work" but you have no idea if today's version is better than yesterday's — and the benchmark you trusted told you nothing about what would break in production.*

## Forces

- **Output non-determinism makes assertions meaningless** — a function returning 4 is testable; an agent summarizing a support ticket has a thousand correct answers and a thousand wrong ones. Standard unit tests are "pretty much useless here" (Ashutosh Tripathi, Principal ML Engineer, 2025).
- **The evaluation *suite* is the real control, not the judge** — the most sophisticated grader is worthless if nobody runs it. An eval suite that runs only when someone remembers to triggers it has stopped functioning as an engineering control.
- **Single-run accuracy is a lie for agents** — agents achieve ~60% on a single run but drop to ~25% across 8 runs (Galileo, 2026). Benchmarks that report pass@1 miss this entirely.
- **Most "failures" in agentic systems are software bugs, not LLM mistakes** — broken URLs, missing API keys, calling localhost in cloud environments, real CVEs mislabeled as hallucinations. Practitioners keep surfacing this pattern across threads.
- **LLM-as-judge has moved from eval harness to production infrastructure** — over half of surveyed production agent teams now use judge LLMs at runtime for quality gating and hallucination defense (Zylos Research, 2026).

## The move

Build a layered evaluation architecture with three tiers running at different cadences:

1. **Deterministic guardrails first** — check output schema, required fields present, type correctness. These are fast, cheap, and catch the class of failures that aren't about intelligence at all.

2. **Step-level + trace-level grading as a unit** — grade each individual step on its own AND the full execution trace as a single unit. An agent where every step looks plausible can still end in the wrong state, and a trace with one recovered error can still succeed (Vercel). Use a tool like DeepEval with `assert_test()` to make these feel like regular pytest assertions.

3. **Swiss Cheese Model for the judge layer** — automated LLM-as-judge runs on every commit (cheap, fast), production monitoring catches real-query failures (expensive but ground-truth), and periodic human review calibrates the judge. When the judge and humans disagree, the judge prompt needs revision (Subodh Jena, 2026).

4. **Pass^k, not pass@k, for consistency-critical agents** — pass@k rises toward 100% as k increases (misleading); pass^k falls toward 0% (honest about consistency). Use pass^k for agents where reliability matters more than a lucky single success (Vercel).

5. **CI enforcement is non-negotiable** — if the eval suite doesn't fail the build, it isn't a control. Tag a failing production trace and it becomes a regression test (Braintrust's "traces to datasets" pattern).

6. **Start with ~20 queries, not 200** — Anthropic's recommendation: 20 well-chosen queries with large effect size beats 200 mediocre ones. Early evals show dramatic signal; you don't need statistical volume to act.

## Evidence

- **HN post:** A practitioner tried benchmark-style agent evaluation and found most failures were system-level bugs (broken URLs dropping score to 22, agent calling localhost in cloud, missing API keys as silent failures, Reddit blocking requests). Concluded eval loops should look more like software testing than benchmarking — repeatable suites, clear passes, every run surfaces a real bug. — [What broke when I tried to evaluate an AI agent in production | Hacker News](https://news.ycombinator.com/item?id=47416033)

- **GitHub Copilot engineering post:** GitHub runs over 4,000 offline tests before any production model change — automated code quality assessments plus LLM-based evaluation and manual testing across multiple languages. Key insight: "Just because a model is newer doesn't mean it will perform better for your use case." — [How we evaluate AI models for GitHub Copilot | GitHub Blog](https://github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot/)

- **Vercel production guide:** Found that 70% of developers still evaluate outputs by hand — habit from grading single completions. For agents, the shift is from "does this response look good?" to "did the workflow succeed end to end?" Recommends binary metrics over floating scores (pass/fail demands a fix; a float invites debate) and grading steps AND traces. — [AI Agent Evaluation Frameworks for Production | Vercel](https://vercel.com/i/ai-agent-evaluation-frameworks-production)

- **HN discussion (128 points):** Multiple practitioners with eval-suite ownership confirm evaluations are "vital for improving performance" — without them you can't know if you're moving the needle. A former coding-agent eval suite owner notes thorough eval tasks are slow/expensive/variable, requiring SQL + tables and prod simulation. LLM-as-judge calibration is essential. — [Principles for production AI agents | Hacker News](https://news.ycombinator.com/item?id=44712315)

- **Zylos Research (2026):** Field bifurcated into large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes verification and small distilled judges (3B–8B parameters) delivering 97% cost reduction at 0.88–0.95 accuracy. Six distinct patterns: offline eval, online runtime verifier, self-consistency loops, Reflexion, constitutional AI/RLAIF, and inference-time reward models. — [LLM-as-Judge in Production | Zylos Research](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)

- **LLM judge calibrator:** Open-source tool detecting position bias, verbosity bias, and self-preference in LLM judges via position-swap evaluation and Cohen's Kappa. Most eval frameworks ignore judge biases entirely. — [LLM Judge Calibrator | GitHub](https://github.com/joaquinhuigomez/llm-judge-calibrator)

## Gotchas

- **Don't build the agent before the eval harness** — teams that skip evaluation ship agents they cannot distinguish from regressions. Build the test harness first so you can answer "is today's version better than yesterday's?" (Subodh Jena, 2026).
- **LLM judges have hidden biases** — they favor the first response shown (position bias), prefer longer answers (verbosity bias), and sometimes rate their own outputs higher (self-preference). Run position-swap experiments and Cohen's Kappa to calibrate before trusting judge scores.
- **Standard benchmarks miss reliability challenges** — an agent scoring well on SWE-Bench or Terminal Bench in a single attempt can fail consistently across retries. Pass^k (consistency) tells the real story for production agents.
- **Cost/latency budget must match evaluation tier** — runtime quality gating (every request) has a tight latency budget requiring small/distilled judges; offline eval (post-commit) can afford large proprietary judges with longer compute time.
- **Production traces becoming eval datasets requires the same format** — Braintrust and similar tools surface this pattern: tag a failing production trace, it goes straight into a regression test. Without format parity between production and eval, this loop breaks.
