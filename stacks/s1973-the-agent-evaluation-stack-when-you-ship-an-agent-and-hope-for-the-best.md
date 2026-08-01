# S-1973 · The Agent Evaluation Stack · When You Ship an Agent and Hope for the Best

When your agent works in demos, passes your three test prompts, and then silently degrades 40% over three weeks in production — because nobody was watching whether it actually succeeded.

## Forces

- **Agents are non-deterministic; traditional tests can't catch them** — the same input can produce a correct answer through a broken reasoning path, or an incorrect answer through a valid-looking one. A unit test that passes once tells you nothing about reliability across runs.
- **Output quality is not the same as trajectory quality** — Google Cloud calls these "silent failures": an agent that reports the right number but from last year's data. The result looks right; the execution failed. You can't catch this from final output alone.
- **The eval ecosystem is fragmented and noisy** — LangSmith, Braintrust, DeepEval, PromptLayer, Ragas, τ-bench, custom dashboards, LLM-as-judge — and most teams aren't running any of them. Only 52.4% run offline evals; just 37.3% run online evals (LangChain State of Agent Engineering 2026, n=1,340 teams).
- **Evaluation cost and iteration speed compete directly** — every eval run costs money and slows the sprint. Teams trade coverage for velocity, then wonder why production surprises them.
- **Production drift is invisible until it isn't** — Lemma (YC F25) found that agent performance can drop ~40% within weeks due to input distribution shift and edge cases unseen during development. Most teams only find out when users complain.

## The Move

Build a layered evaluation system that covers trajectory, output, and operational behavior — and run it at multiple cadences.

**The three-layer stack:**

1. **Offline regression suite (pre-deploy)** — a curated golden dataset of task inputs with expected outputs. Run on every PR. Covers: task success rate, answer correctness, tool call sequence accuracy. Use deterministic checks where possible (exact match, regex, JSON schema validation) before reaching for LLM-as-judge.

2. **LLM-as-judge for qualitative dimensions (pre-deploy + CI)** — evaluate tone, reasoning coherence, safety policy adherence, and response structure with a separate LLM call. Chain-of-thought prompting in the judge reduces position bias. Combine with at least two judge models to catch agreement gaps. Run pass@k (succeeds at least once in k attempts) and pass^k (succeeds every time) — an agent with 75% per-trial reliability has only 42% chance of passing three consecutive trials.

3. **Online/shadow evaluation in production (continuous)** — sample a percentage of live traces and run them against automated checkers. Track: task completion rate, tool call success rate, latency per step, cost per task, and silent failure rate (correct output, broken trajectory). Services like Lemma, Lucidic, or LangSmith tracing surface trajectory-level failures that output-only metrics miss.

**CI/CD integration as gate:**
- Block deploys when offline eval drops below threshold
- Alert when online eval metrics drift more than 15% from baseline
- Calibrate thresholds with a human review sample (label 50-100 traces manually first, then trust the judge)

**Golden dataset maintenance:**
- Add every production failure as a new test case immediately
- Partition by task type and difficulty — don't just add hard cases
- Rotate judges and model versions quarterly to catch staleness

## Evidence

- **Survey (LangChain State of Agent Engineering 2026):** Only 52.4% of 1,340 surveyed teams run offline evaluations; only 37.3% run online evals. Yet 82.6% of practitioners with deployed agents prefer the agentic solution over non-agentic alternatives — a gap between adoption confidence and evaluation rigor. — [langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)

- **YC company post (Lemma, Fall 2025):** "AI agents don't learn from their mistakes. In fact, they get worse with use." Lemma's production monitoring found agent performance can drop ~40% within weeks due to input distribution shift and unseen edge cases. — [ycombinator.com/companies/uselemma](https://www.ycombinator.com/companies/uselemma)

- **Engineering post (Google Cloud, Nov 2025):** Introduced the "silent failure" concept — agents that produce correct outputs through incorrect processes. Emphasized trajectory-level evaluation (the sequence of reasoning and tool calls) rather than output-only assessment. — [cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)

- **Research paper (MAP Study, arXiv:2512.04123, ICML 2026 Oral):** First large-scale study of 86 deployed agents across 26 domains. Found that evaluation practices vary dramatically — teams lack standardized metrics, and the gap between "works in dev" and "works in prod" is the primary failure mode. — [arxiv.org/html/2512.04123v1](https://arxiv.org/html/2512.04123v1)

- **Industry guide (InfoQ, March 2026):** "Single-turn accuracy metrics (BLEU, ROUGE) don't capture how agents fail in multi-turn, tool-using scenarios." Recommended hybrid evaluation combining automated scoring with human judgment, and treating latency, cost per task, and token efficiency as first-class quality dimensions. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **HN Launch (Lucidic, YC W25):** Stanford AI Lab researchers building agent observability: "Traditional LLM observability platforms don't capture the complexity of agents — tools, memories, events — not just input/output pairs." — [news.ycombinator.com/item?id=44735843](https://news.ycombinator.com/item?id=44735843)

## Gotchas

- **Evaluating only the final output misses silent failures** — always inspect the trajectory (tool call sequence, reasoning steps) alongside the answer. A correct answer from the wrong source is a failure.
- **LLM-as-judge has known biases** — position bias (prefers first or last option), verbosity bias (longer answers score higher), and self-preference bias (judge prefers outputs similar to its own style). Mitigate by using chain-of-thought prompting in judges and cross-checking with a second model.
- **Golden datasets go stale fast** — if you only add hard or failing cases, your eval suite becomes artificially pessimistic. Maintain a balanced mix of easy, medium, and hard cases. Rotate in fresh production samples monthly.
- **pass@k vs. pass^k confusion** — pass@k measures capability (can it sometimes succeed?); pass^k measures reliability (does it always succeed?). For production agents, reliability (pass^k) is usually the tighter constraint, especially for high-stakes tasks. Don't optimize for pass@1 and call it done.
- **Online eval sampling rate tradeoff** — evaluating 100% of traces is expensive; sampling 1% may miss rare failure modes. Target 5-10% for routine agents, 100% for high-stakes domains, and always evaluate every failure flagged by users.
