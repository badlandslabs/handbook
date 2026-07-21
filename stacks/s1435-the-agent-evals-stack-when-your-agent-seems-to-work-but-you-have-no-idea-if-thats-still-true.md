# S-1435 · The Agent Evals Stack — When Your Agent "Seems to Work" But You Have No Idea If That's Still True

Your agent passed every test in staging. It answered the demo queries correctly, called the right tools, and finished tasks on time. Three months later, after two model updates and a system prompt change, it's making $40/hr API calls it shouldn't, occasionally skipping a critical verification step, and returning subtly wrong answers your users are too polite to report. You have no regression suite. You found out the model "drifted" because someone on the team noticed. Agent evaluation — measuring whether your agent actually works, and whether it still works — is the hardest unsolved problem in production AI. This entry covers the stack that actually gets teams from hope to evidence.

## Forces

- **Agents fail non-deterministically, but you still need deterministic signals.** Unlike traditional software where a regression is a clear regression, an agent that succeeds 80% of the time and fails 20% might still pass a small test set by luck. You need enough coverage to separate signal from variance.
- **The output is not the point — the trajectory is.** For a coding agent, the correct answer and the path to the answer both matter. A trajectory with three unnecessary API calls and a wrong final answer "passes" exact-match but is a product failure.
- **Model updates break agents silently.** OpenAI and Anthropic model updates — even minor ones — change token distributions, instruction-following behavior, and tool-calling patterns. Without a regression suite, you discover breakage from user complaints.
- **Golden datasets rot.** Test cases that accurately captured real user behavior three months ago may not reflect the current distribution of queries. Eval datasets need the same maintenance discipline as production code.

## The Move

The practical agent eval stack operates across three layers: **deterministic metrics** for structured outputs, **LLM-as-judge** for open-ended generation, and **trajectory metrics** for multi-step behavior. Golden datasets — versioned, annotated test case collections — sit at the center as the source of truth.

### The three scoring layers

- **Deterministic scorers** for tasks with verifiable ground truth. Use `exactMatch` for classification, slot-filling, and extraction tasks. Use `fuzzyMatch` (Levenshtein distance) for tasks where minor formatting variance is acceptable. Use `tokenOverlap` (BLEU/ROUGE-family) for paraphrase-tolerant scoring. These are fast, reproducible, and CI-friendly — they return a binary pass/fail with no judge bias.
- **LLM-as-judge** for open-ended outputs. A separate LLM (typically GPT-4o or Claude Sonnet) receives the input, the agent's output, and a scoring rubric, then returns a structured verdict (numeric score + justification). Run in three modes: **pointwise scoring** (1-5) for CI gating and trend tracking, **pairwise comparison** for A/B testing model or prompt variants, and **reference-guided scoring** for datasets with known-good answers. Even "noisy" judge models produce useful relative rankings — the value is statistical across a test set, not per-example precision.
- **Trajectory metrics** for multi-step agents. Track: task completion rate (did the agent finish?), step efficiency (did it use the minimum necessary tools?), and critical path adherence (did it hit the required verification steps?). A successful final answer via a 12-step detour when 4 steps were sufficient is a trajectory failure. Log every tool call, intermediate result, and branching decision as structured trace data.

### The golden dataset contract

A golden dataset is not a folder of examples — it is a **versioned contract** with explicit fields per test case:

```
{
  "id": "case-042",
  "input": "Cancel my subscription and send confirmation to user@co.com",
  "expected_tools": ["cancel_subscription", "send_email"],
  "forbidden_tools": ["delete_user_data"],
  "acceptable_outputs": ["Subscription cancelled. Confirmation sent."],
  "critical_path": ["authenticate", "cancel", "confirm"],
  "category": "account_lifecycle"
}
```

Version the dataset in git alongside your agent code. Each entry is a test case *plus a scoring contract*. A new entry requires: real production inputs (sampled from logs, not invented), annotated ground truth, and a defined scoring method (deterministic or judge rubric).

### CI/CD gate discipline

Treat eval failure as a build failure. The minimum viable pipeline: on every commit, run the full golden dataset against the current agent and fail the build if any critical-path case drops below threshold. DeepEval (Confident AI's open-source framework) reports running over 600K evaluations daily in CI/CD pipelines at BCG, AstraZeneca, AXA, and Capgemini — all enterprise deployments where eval is not optional. An agent-eval-arena approach returns explicit `pass`/`fail` exit codes from CI, enabling standard promotion gates for model version upgrades.

### Trajectory tracing as first-class observability

Instrument your agent once — with `@observe` decorators or framework integrations (LangChain, CrewAI, OpenAI Agents SDK) — so every run emits a structured trace. Each span represents a component: LLM call, tool invocation, retriever query, sub-agent turn. Attach metrics at the span level for end-to-end eval and component-level eval simultaneously. This is the difference between knowing "the agent failed" and knowing "the retriever returned stale data in step 3 of 7."

### Ongoing eval maintenance

- **Rotate test cases quarterly.** Remove cases that all models now pass trivially (they no longer discriminate). Add cases from production failures and edge cases discovered in the wild.
- **Monitor drift, not just failure.** Track whether your agent's average score on the golden dataset is declining over time — even while staying above the CI threshold. A gradual 5% drop across 8 weeks is more actionable than a threshold breach.
- **Calibrate judge prompts against human ratings.** Run a subset of your golden dataset through human annotators quarterly and compare judge scores. Judges drift too.

## Evidence

- **GitHub repo / Launch HN:** Confident AI's DeepEval open-source framework (YC W25) runs over 600K evaluations daily in CI/CD pipelines at enterprise customers including BCG, AstraZeneca, AXA, and Capgemini. The platform implements the three-layer eval model with native integrations for LangChain, OpenAI, Anthropic, CrewAI, LlamaIndex, and DSPy. — [github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval); [news.ycombinator.com/item?id=43116633](https://news.ycombinator.com/item?id=43116633)
- **HN Show HN:** Zalor AI launched an agent testing platform focused specifically on the problem that "agents often break when you tweak system prompts" — surfacing that golden dataset maintenance and eval regression are the primary operational pain point for teams shipping agents iteratively. — [news.ycombinator.com/item?id=47270208](https://news.ycombinator.com/item?id=47270208)
- **Thoughtworks / Engineering post:** "Evaluating AI Agents in Production: A Practical Framework" (Akshay Anand, June 2026) formalizes the distinction between RAG-evaluatable systems (retrieval relevance, context coverage, faithfulness, hallucination rates) and pure prompt-based agents (instruction adherence, task completion, reasoning quality, output consistency) — and the need for different evaluation taxonomies for each. — [thoughtworks.com/en-in/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production](https://www.thoughtworks.com/en-in/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)
- **GitHub repo:** agent-eval-arena provides a production-grade eval service with versioned datasets, multi-scorer execution, regression detection across model versions, cost-quality leaderboards, and CI gates returning pass/fail. Built with Node.js/TypeScript, Express, Zod — demonstrates that eval infrastructure is real engineering, not a Jupyter notebook. — [github.com/mizcausevic-dev/agent-eval-arena](https://github.com/mizcausevic-dev/agent-eval-arena)
- **Research:** arXiv 2507.21504 (KDD 2025) — "Evaluation and Benchmarking of LLM Agents: A Survey" from SAP Labs presents a two-dimensional taxonomy organizing existing work across task performance and behavioral robustness axes. — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)

## Gotchas

- **A passing eval is not a safe agent.** Golden datasets cover known cases. Your agent will encounter novel inputs. Eval measures whether the agent still does what you know it should — not whether it will do the right thing on cases you haven't imagined. Complement evals with adversarial testing and production monitoring.
- **LLM-as-judge has known biases** — position bias (preferring first or last responses in pairwise), verbosity bias (rewarding longer outputs), and self-preference bias (a model judging its own outputs). Mitigate by using a judge model *weaker* than the agent model, running pairwise over pointwise when possible, and calibrating against human ratings periodically.
- **Trajectory metrics require instrumentation upfront.** You cannot reconstruct step-by-step traces from final-output logs. If you didn't instrument your agent with tracing before it went to production, you have no trajectory data for regression. Plan for tracing at agent architecture time, not after.
- **Golden datasets drift faster than you think.** Real user query distributions shift — new product features, seasonal patterns, new failure modes. A golden dataset built in January may not reflect June traffic. Treat it as a living artifact with a maintenance owner and a rotation schedule.
- **CI gating thresholds set too high kill deployment velocity.** Set thresholds at the level where you have *actual evidence* of user harm — not aspirational "we want 95% accuracy." Teams that set 90% thresholds and then spend months trying to close the last 10 points are not shipping agents; they're running an ML research project.
