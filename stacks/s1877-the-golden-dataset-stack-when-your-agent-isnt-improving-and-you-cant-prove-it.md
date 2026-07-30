# S-1877 · The Golden-Dataset Stack: When Your Agent Isn't Improving and You Can't Prove It

You shipped the agent. It works fine in demos. But you can't tell if it's actually getting better between releases, you don't know when it degrades, and "it feels off" isn't a pull-request blocker. You need a real evaluation practice.

## Forces

- **Agents have infinite input space** — unlike traditional software, users express the same intent in countless variations. You cannot fully predict how your agent will be used until real users touch it.
- **Output is non-deterministic** — the same input can produce different outputs between runs. Traditional software testing is insufficient.
- **Two evaluation worlds collide** — offline evals (controlled, reproducible) and online evals (live production traffic, realistic). Teams optimize one and neglect the other.
- **LLM-as-judge is powerful but brittle** — using a model to grade your model is fast and scalable, but the judge can be wrong, biased, or gaming the metric.
- **Success is hard to define** — task completion, tool selection, coherence, faithfulness, latency, and cost all compete. Getting them wrong means shipping blindly.

## The Move

Build a layered evaluation practice that runs across the development lifecycle: offline before deploy, continuous during production, and evolving as you learn.

**Offline evaluation (before deploy):**

- Curate a **golden dataset** of 20–50 real production scenarios representing diverse failure modes and happy paths. Label them with expected outputs and success criteria.
- Run the agent against the golden dataset on every code change. Use **deterministic assertions** for measurable outcomes (tool called, correct parameter, exact output format) and **LLM-as-judge** for qualitative assessments (answer faithfulness, reasoning quality).
- Track the three failure layers Anthropic identifies: **capability** (can it do this at all?), ** robustness** (does it handle edge cases?), and **correctness** (does it do it right?).
- Build **synthetic data harnesses** to fill coverage gaps. Use production traces where you have them; generate synthetic examples for rare edge cases you don't. The key is staying on the manifold of plausible domain data.

**Online evaluation (production):**

- Sample 10–20% of live production traces and run evaluators automatically against them. Configure which traces to evaluate (all, sampled, filtered subsets) and set alert thresholds.
- Detect **drift** — when the agent's quality degrades due to model updates, upstream API changes, or shifting user input distributions. A golden dataset that passed last month is not guaranteed to pass next month.

**Regression and iteration:**

- Every production failure that slips through becomes a new golden dataset entry. This closes the loop: production incidents feed the eval set, which blocks future regressions.
- Track **multi-metric dashboards**: task success rate, tool selection accuracy (>92% binary, >85% with 5+ tools), hallucination rate (<2%, or <0.5% in regulated domains), cost per query, P99 latency.

## Evidence

- **Engineering blog (Anthropic):** "Demystifying evals for AI agents" — defines the core eval vocabulary: tasks, trials, graders, transcripts, outcomes. Distinguishes coding agents (unit tests + LLM rubric), research agents (factuality, thoroughness), and conversational agents (goal completion, recovery, safety). Recommends tracking transcript metrics (n_turns, n_toolcalls, tokens) alongside outcome quality. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Engineering blog (Databricks, Sep 2025):** "The key to production AI agents: Evaluations" — 85% of organizations are using GenAI, 73% call it critical to strategic goals, but most agents hit a wall before reaching production. Emphasizes domain-specific agents paired with continuous evaluation as the differentiator. — [databricks.com/blog/key-production-ai-agents-evaluations](https://www.databricks.com/blog/key-production-ai-agents-evaluations)
- **GitHub repo (Microsoft, Apr 2025):** "ai-agent-evals" — open-source GitHub Action for evaluating AI agent applications using model-as-judge, content safety, and mathematical metrics. 96 stars. Shows the industry is standardizing on GitHub-native eval pipelines. — [github.com/microsoft/ai-agent-evals](https://github.com/microsoft/ai-agent-evals)
- **GitHub repo (fr3kchy/MCP Intelligence):** "agent-eval-harness-demo" — golden-dataset-driven evaluation harness demonstrating 25 Q&A pairs, drift detection, and reproducible eval runs against LangSmith. Covers answer correctness, relevance, and hallucination detection. — [github.com/fr3kchy/agent-eval-harness-demo](https://github.com/fr3kchy/agent-eval-harness-demo)
- **Engineering blog (LangChain):** "Agent Observability: How to Monitor and Evaluate LLM Agents in Production" — online eval patterns: sample production traffic, set alert thresholds, track quality over time, tag topics for product analytics. Observability connects production monitoring back to the eval dataset for continuous improvement. — [langchain.com/blog/production-monitoring](https://www.langchain.com/blog/production-monitoring)
- **Blog post (MachineLearningMastery, Feb 2026):** "Agent Evaluation: How to Test and Measure Agentic AI Performance" — golden dataset of 20–50 curated examples is the foundation. Start with simple task completion metrics, add sophistication only after understanding failure modes. Evaluates agents differently from LLMs because agents take actions, invoke tools with specific parameters, make sequential decisions, and must recover from failures. — [machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance](https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance)
- **Blog post (Saulius, Apr 2026):** "A Synthetic Data Generation Harness" — production traces are the best source but often unavailable under NDA or compliance restrictions. Synthetic data must stay on the manifold of plausible domain data to avoid generating unrealistic cases. Use LLM feedback to iteratively expand coverage of failure modes. — [saulius.io/blog/synthetic-data-generation-harness-ai-agents](https://saulius.io/blog/synthetic-data-generation-harness-ai-agents)

## Gotchas

- **No golden dataset, no progress** — iterating on "it feels better" is not engineering. Without a fixed, versioned eval set, you cannot distinguish real improvement from variance.
- **LLM-as-judge can be wrong and can be gamed** — a judge model can be overly harsh on some outputs and overly lenient on others. Pair with deterministic assertions for measurable dimensions; use the judge for qualitative dimensions where it's the only scalable option.
- **Multi-turn coherence is easily missed** — a trace can look fine step-by-step but accumulate error across turns. Track n_turns, n_toolcalls, and reasoning chain coherence, not just final output correctness.
- **Silent failures are the worst failures** — agents that confidently produce wrong answers look identical in logs to correct ones. Hallucination detection (grounding output to retrieved context) must be a first-class metric.
- **Eval set staleness is invisible** — model updates, upstream API changes, and user behavior drift all silently invalidate previously-passing eval sets. Re-run golden datasets monthly at minimum.
