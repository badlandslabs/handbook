# S-2163 · The Trajectory Eval Stack — When Your Agent Succeeds at the Wrong Thing

You run your eval. 91% task completion. Zero regressions. The agent is production-ready. Six weeks later, you find it has been completing the right task through the wrong path — calling external APIs it should have cached, spending $4.70 per transaction on $0.08 of work, and making confident errors that a human would catch by watching the reasoning. Your eval measured the destination. The failure was in the journey.

## Forces

- **Outcome vs trajectory** — final-answer grading is blind to how the agent got there, so correct outputs via broken reasoning look identical to correct outputs via sound reasoning
- **Compounding errors** — a 5% per-step error rate reaches 22.6% overall failure probability across 5 steps; output-only scoring misses this entirely
- **No oracle** — traditional software has a ground truth; LLM systems have no such reference, so every eval is a proxy
- **37% benchmark-to-production gap** — lab benchmarks use clean inputs, predictable tool responses, and controlled environments; production faces ambiguous requests, flaky APIs, and adversarial inputs that synthetic tests never surface
- **Scoring creates blind spots** — optimizing any single metric (task completion, latency, cost) at the others' expense is easy without a multi-dimensional framework

## The Move

The core technique: evaluate agent trajectories, not just outcomes — at five simultaneous dimensions, using trace-first observability as the foundation for grading.

### The Five Dimensions (track all five, always)

1. **Task completion rate** — did the agent finish the job? Define precise completion tiers: done, partial, failed-but-thinks-it-succeeded (the most dangerous category). Use environment-grounded outcome checks, not self-reported completion.
2. **Quality** — surface accuracy + semantic correctness. Surface accuracy checks for formatting and factual claims against a reference. Semantic correctness handles cases where multiple valid answers exist (e.g., SQL query vs API call vs manual lookup — all three can be correct).
3. **Trajectory efficiency** — how many steps, tool calls, and token turns did the agent use? Catch the agent that solves in 40 steps what a well-designed agent solves in 6. Correlates directly with cost-per-task.
4. **Safety / constraint adherence** — did the agent respect system-level rules (no PII leakage, no destructive actions without confirmation, no tool calls outside its scope)? Run per-step checks, not just end-of-run checks.
5. **Hallucination rate** — false claims about external state (balance = $X, record exists, status = active). Cross-reference against ground-truth systems wherever possible.

### Trace-First Infrastructure

Every eval is built on a **transcript**: a complete record of outputs, tool calls, reasoning traces, and intermediate results across the full agent run. Without traces, you cannot diagnose which component failed or whether the path was sound.

- Instrument agents to emit traces from day one — LangSmith, Galileo, Oodle.ai, Lemma, and DeepEval all converge on this as the non-negotiable foundation
- Capture every tool call: which tool, with what arguments, what result, at what latency
- Store reasoning traces separately from outputs — a model can reach a correct answer via broken logic, and that broken logic will fail on the next novel input

### LLM-as-Judge: Calibrated, Not Freeform

LLM-as-judge evolved from "ask GPT-4 if this is good" into a disciplined methodology with three requirements:

1. **Rubric engineering** — write explicit scoring criteria before running the judge. Vague prompts ("is this response good?") produce inconsistent scores. Specific rubrics (e.g., "rate 1-5 on: correctness of API selection, appropriate use of cache, avoidance of redundant calls") produce actionable signals.
2. **Calibration** — validate judge scores against human-labeled samples. Shopify calibrated their LLM judge from Kappa 0.02 to Kappa 0.61 before using it for production scoring. Without calibration, judge scores are noise.
3. **Bias awareness** — position bias (judges favor responses earlier/later in a list), length bias (judges favor longer outputs), and self-preference bias (a model judges its own outputs favorably) are documented failure modes. Use a different model family than the agent under test.

### Production Mirroring Flywheel

Synthetic benchmarks miss the failures that appear only in production traffic. The pattern that closes the benchmark-to-production gap:

1. Route real production traffic through both current and candidate agent versions simultaneously
2. Log divergent outcomes — cases where the two versions took different paths or produced different results
3. Human-review divergent cases, add labeled failures to regression datasets
4. Re-run offline evals against the growing regression set
5. Retrain / fine-tune on failure cases

Shopify closed their benchmark-to-production gap in two weeks using this flywheel. The key insight: **production failures are the training data for production evals**.

### The Compounding Error Pattern

For agents with 5+ steps, insert per-step confidence checks between each major action. Flag and surface low-confidence decisions for human review before the agent commits to a downstream action. This is the only practical way to keep long-running agents reliable — catching errors at step 3 before step 4 amplifies them.

## Evidence

- **Anthropic Engineering:** Demystifying evals for AI agents (Jan 2026) defines the core vocabulary — task, trial, grader, transcript, outcome, harness, eval suite — and establishes trace-first as the foundation. Cross-referenced against "Effective harnesses for long-running agents" (Nov 2025) which describes how Claude Agent SDK instruments agents for step-by-step progress tracking and context management across discrete sessions. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

- **LangChain State of Agent Engineering (1,340 respondents, Jun 2026):** 57% of organizations have agents in production; quality is the #1 production barrier (32%); 52% have adopted evals; organizations running both offline and online evals nearly double the success rate of those running offline-only. Cross-referenced against the "Evaluating agents" framework from LangSmith which details the instrument → benchmark → monitor pipeline. — https://www.langchain.com/state-of-agent-engineering

- **Shopify / ZenML production case study (2025):** 37% benchmark-to-production gap across 1,200 production deployments. Shopify used calibrated LLM judge (Kappa 0.02 → 0.61) + production mirroring flywheel to close the gap in two weeks. 80% quality is reached quickly; pushing past 95% requires the majority of total development time. Cross-referenced against Confident AI's LLM Agent Evaluation Guide (Jun 2026) which independently surfaces the same five-dimension framework and trajectory-vs-outcome distinction. — https://techlogstack.com/explore/shopify-llm-evaluation-production-2025/

- **GitHub Copilot evaluation (Jan 2025):** 4,000+ offline tests, ~100 containerized test repos, 1,000+ technical Q&A questions. Combines automated metrics (acceptability rate, suggestion rate, code quality) with LLM-based evaluation and manual testing across multiple languages and frameworks. "Just because a model is newer doesn't mean it will perform better for your use case." Cross-referenced against the Braintrust "Six Generations of AI Agents" (May 2026) which traces how evaluation strategies evolve alongside agent architectures — each new capability creates failure modes previous-generation evals cannot see. — https://github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot/

- **Zylos Research: LLM-as-Judge Patterns (May 2026):** Documents the evolution of LLM-as-judge from hack to disciplined methodology, cataloging calibration protocols, bias taxonomies (position, length, self-preference), and trajectory-specific scoring. Confirms rubric engineering and cross-model judging as industry consensus practices. — https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns/

- **Jobs by Culture / Future AGI / Goodeye Labs:** Independent sources confirming the 37% benchmark-production gap, the five-dimension evaluation framework, and the breakdown of static benchmarks due to contamination (LiveCodeBench exposed 20-30% score drops on post-training-cutoff problems). — https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026 | https://futureagi.com/blog/agentic-ai-evaluation-2025/ | https://www.goodeyelabs.com/insights/llm-evaluation-2025-review

## Gotchas

- **Output-only scoring misses 20–40% of regressions** — it flags the destination but hides the process; an agent can be failing consistently via acceptable-looking paths
- **Calibrate your judge before trusting it** — an uncalibrated LLM-as-judge produces Kappa 0.02 agreement with humans, which is statistically indistinguishable from random; you cannot skip this step and still trust the results
- **Cost-per-task is a first-class metric, not a later concern** — two agents with 90% task completion can differ 50x in cost per transaction; without tracking trajectory efficiency, you will discover cost problems in your billing, not in your eval suite
- **Benchmarks have a shelf life** — benchmark contamination became critical enough by late 2025 that models showed 20-30% performance drops on novel problem sets; production failure cases are the only evergreen eval dataset
- **"Failed but thinks it succeeded" is the highest-risk category** — agents that confidently produce wrong outputs while reporting completion are undetectable without environment-grounded outcome checks and production sampling
