# S-963 · The Agent Evaluation Stack — When You Don't Know If Your Agent Actually Works

An agent that completes tasks at 95% can be correct only 70% of the time. It declares success confidently while producing garbage. The gap between task completion and task correctness is the evaluation problem — and it's why 39% of AI projects in 2024-2025 fell short of expectations. You can't improve what you can't measure, and measuring agents is fundamentally different from measuring language models.

## Forces

- **Task completion ≠ correctness.** An agent can call the right tools in the right order and still produce wrong outputs. "The pipeline returned 200 OK" is not evidence the work is done.
- **Agents are non-deterministic.** The same prompt can produce different execution paths, tool selections, and conclusions. A single eval run tells you almost nothing.
- **Production failures are inter-agent.** Vindler found 67% of multi-agent failures stem from inter-agent interactions, not individual defects — yet most teams only eval single agents.
- **Eval vs. observability confusion.** 89% of organizations have observability; only 52% have evaluation systems. Logging traces is not the same as measuring correctness.
- **Benchmark scores don't transfer.** A model scoring 92% on SWE-bench can swing 30-50 points based on scaffolding alone. The same model with a Cursor wrapper vs. an agentless wrapper can differ by 40 points.

## The Move

Build a three-layer evaluation system: deterministic unit checks for tool-call contracts, LLM-as-judge for open-ended quality, and human review for ambiguous or high-stakes outputs. Treat eval data as test data that you collect, label, and iterate on.

### Concrete approach

- **Ground truth tests first.** Write assertions that check concrete outputs: correct API parameters fired, database state changed as expected, exact string match for structured responses. These run fast, don't hallucinate, and catch regressions.
- **Collect evals from traces.** Every production failure is a new test case. Log the input, the agent trace, and the incorrect output — then label it. This is your eval dataset growing from real production data.
- **LLM-as-judge for quality dimensions.** Use a second LLM to score output quality, coherence, and completeness against a rubric. Validate the judge itself — run it against 20 labeled examples before deploying. Without validation, the judge compounds the problem.
- **Adapt judges with DSPy or correction models.** Rather than over-engineering prompts, use DSPy to optimize the judge prompt, or train a small correction model (LLM-Rubric) to calibrate judge outputs.
- **Use pass@k, not pass@1.** Agent tasks are stochastic. Measure the probability that *any* of k attempts succeeds. This catches nondeterminism that single-run metrics hide.
- **Run eval in CI, not manually.** Automated regression suites on every PR prevent prompt changes from silently degrading production quality. Braintrust, LangSmith, and Langfuse all support native CI integration.
- **Layer benchmarks to match your use case.** GAIA for real-world multi-step reasoning (human baseline: 92%, current best models: ~50%), SWE-bench for code tasks, WebArena for browser agents, Tau-Bench for customer interaction quality. No single benchmark covers the full stack.

## Evidence

- **Blog post + HN discussion:** app.build's "Six Principles for Production AI Agents" sparked an HN thread (128 points) where practitioners emphasized evals as non-negotiable. One commenter: "Evals are a core part of any up to date LLM team. If some team was just winging it without robust eval practices they're not to be trusted." Another: "a tweak to a prompt passed an initial vibe check, but when run against the full eval suite, clearly performed worse." — [HN Discussion](https://news.ycombinator.com/item?id=44712315)
- **Industry analysis:** Vindler Solutions' post-mortem of 2025 production failures found that an agent "completing" tasks at 95% had only 70% actual correctness. Their MAST framework identifies the gap between process metrics (tool calls, latency, cost) and outcome metrics (did the output actually solve the problem). 39% of AI projects fell short; only 2% deployed agentic AI at scale. — [Vindler Blog](https://vindler.solutions/blog/agent-evaluation-at-scale)
- **Benchmarks + practitioner guide:** The GAIA benchmark (Meta/HuggingFace) establishes that humans score 92% vs GPT-4-with-plugins at 15% on real-world multi-step tasks. Anthropic's "Building Effective AI Agents" (June 2025, 543 HN points) recommends starting with simple composable patterns before reaching for frameworks, and explicitly calling out that teams need to instrument for evaluation before optimizing prompts. — [Anthropic](https://www.anthropic.com/engineering/building-effective-agents) and [GAIA arXiv](https://arxiv.org/abs/2311.12983)
- **Tooling comparison:** A 2026 independent comparison of Braintrust, LangSmith, Langfuse, and Arize Phoenix found Braintrust leads on CI integration and eval dataset management, Langfuse excels for self-hosted/OSS teams, LangSmith has the tightest LangChain integration. All four support LLM-as-judge and multi-step trajectory evaluation. — [Paperclipped](https://www.paperclipped.de/en/blog/ai-agent-evaluation-tools-comparison)

## Gotchas

- **LLM-as-judge has positional bias.** Judges favor responses placed first (first-order bias) and prefer longer outputs. Calibrate by running the judge against your own labeled examples before relying on it.
- **Benchmark contamination is real.** MMLU test questions appear verbatim in Common Crawl. HumanEval problems are near-duplicates of LeetCode solutions in pre-training data. OpenAI stopped reporting SWE-bench scores after a leakage incident. Verify benchmarks against your actual task distribution.
- **67% of multi-agent failures are inter-agent.** Eval frameworks that test individual agents in isolation will miss the coordination failures that sink production systems. Multi-agent eval requires testing the communication protocol, not just the components.
- **The "95% completion" metric is dangerous.** If you measure "did the agent stop" instead of "did the agent produce correct output," you will confidently ship broken agents. Separate completion from correctness in your metrics taxonomy.
- **Eval data goes stale.** Model behavior drifts as providers update models silently. Re-run your eval suite quarterly against a golden dataset to catch regressions that your CI won't catch because the prompts haven't changed.
