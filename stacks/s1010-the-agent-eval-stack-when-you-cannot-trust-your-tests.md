# S-1010 · The Agent Eval Stack — When You Cannot Trust Your Tests

Your eval suite passes. You shipped the prompt change. Users started complaining within a week. The eval score went up — but the agent got worse on the cases that actually matter. This is the most common failure mode in production AI teams right now: a bad dataset producing confident lies, and nobody caught it because the pipeline was green.

## Forces

- **Agents are non-deterministic, traditional tests are not.** Unlike deterministic code where input X always produces output Y, agents plan, branch, and adapt across multiple steps. A single eval run is one sample from a distribution. You cannot trust one run.
- **72% of AI teams believe comprehensive testing drives reliability, yet only 15% achieve elite eval coverage.** That 57-percentage-point belief-execution gap is not laziness — it is genuinely hard. Traditional ML metrics (accuracy, precision) don't capture agentic workflows where success depends on multi-step reasoning, tool selection, and context management. — [Galileo AI, State of Eval Engineering Report, Jul 2026](https://galileo.ai/blog/ai-agent-metrics)
- **Up to 40% of organizations deploying LLM-powered applications encounter significant quality regressions within 90 days of production.** Root cause: absence of systematic evaluation, not bad models. — [AI Workflow Lab, Feb 2026](https://aiworkflowlab.dev/article/llm-evaluation-production-automated-testing-pipelines-catch-failures)
- **Evals are a core driver of performance improvements.** This is not optional overhead — it is the development loop. — [HN user roadside_picnic, HN discussion on production AI agents, 2025](https://news.ycombinator.com/item?id=44712315)

## The move

Build a layered evaluation pipeline that measures both trajectory (how the agent got there) and outcome (what the agent produced), grounded in a curated golden dataset, with automated scoring in CI and human review gating high-stakes releases.

### The three-level metric stack

Track metrics at three levels simultaneously. Missing any level creates blind spots.

- **Outcome-level:** Task completion rate (did the agent finish the job?), answer correctness, output format compliance, latency, cost per task. These validate whether business goals are met.
- **Trajectory-level:** Intermediate step quality, tool call sequence correctness, plan adherence, retry loops, context management. These enable debugging by showing *how* the agent failed, not just *that* it failed. — [Galileo AI, Agent Evaluation Framework, Jul 2026](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Component-level:** Individual tool call correctness, argument validity, RAG retrieval faithfulness, reasoning chain coherence. Use these to isolate failure to a specific span, tied back to a trace. — [Confident AI, LLM Agent Evaluation Guide, 2026](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)

### Golden dataset construction

A golden dataset is a curated, versioned collection of prompts, inputs, contexts, and expected outcomes with rich metadata. It is the source of truth for measuring quality across the AI lifecycle.

- **Source from production, not imagination.** Pull real failure cases from live logs. Synthesize edge cases with agent simulations (silver datasets), then promote to gold with human review. — [Maxim AI, Golden Dataset Guide, Nov 2025](https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide)
- **A bad dataset produces confident lies.** Twenty examples someone wrote in an afternoon mixed with support tickets is not a golden dataset. Size matters less than quality and coverage of failure modes. — [TeachYou Academy, Golden Dataset for LLM Eval, Jun 2026](https://www.teachyou.ai/blog/building-golden-dataset-llm-eval)
- **Version your dataset.** Track which eval version corresponded to which prompt or model change. If scores improve after a change, you need to prove the dataset didn't drift.

### LLM-as-judge: use it, but carefully

LLM-as-judge uses a capable frontier model to score outputs from other AI systems. It changes the economics of evaluation — thousands of outputs per hour at a fraction of human annotation cost. — [QuarkAndCode, LLM Evaluation in 2025, Oct 2025](https://medium.com/@QuarkAndCode/llm-evaluation-in-2025-metrics-rag-llm-as-judge-best-practices-ad2872cfa7cb)

- **Ditch the 1–10 scale.** Binary pass/fail or pairwise comparison are more reliable than numeric ratings, which LLM judges inflate. Ask: "Was this output correct? Yes or no." — [Reddit r/LangChain, Best LLM-as-Judge Practices from 2025](https://www.reddit.com/r/LangChain/comments/1q59at8/best_llmasajudge_practices_from_2025/)
- **Go beyond final outputs.** Agent-as-a-judge evaluates intermediate steps — whether code compiled at a given stage, whether each sub-requirement was met, how many tool calls were used. Agent-as-a-judge dramatically outperformed standard LLM-as-judge that only saw final outputs, achieving parity with human evaluators on code tasks. — [arXiv 2508.02994, When AIs Judge AIs, Aug 2025](https://arxiv.org/html/2508.02994v1)
- **Calibrate against human judgment.** Run a subset of evals with human reviewers and compare to judge scores. If they diverge significantly, the judge prompt needs tuning — not your agent.
- **Use chain-of-thought prompting in the judge.** Ask the judge to explain its reasoning before giving a score. This reduces grade inflation and makes failure analysis actionable. — [TeachYou Academy, LLM-as-Judge guide, Jun 2026](https://www.teachyou.ai/blog/building-golden-dataset-llm-eval)

### Integrate into CI/CD, not just pre-release

- Run the eval suite on every prompt or model change. Treat it like a unit test suite: fast, deterministic, blocking. — [AI Workflow Lab, LLM Evaluation Pipelines, Feb 2026](https://aiworkflowlab.dev/article/llm-evaluation-production-automated-testing-pipelines-catch-failures)
- DeepEval provides a Pytest-like interface for LLM evaluation with trajectory-level metrics, G-Eval, and integrations for OpenAI Agents, LangChain, LangGraph, and CrewAI. — [GitHub confident-ai/deepeval](https://github.com/saal-core/deepeval)
- Use LangSmith or Langfuse for distributed tracing across agent steps, so a low score can be traced back to the exact span that caused it. — [RockB, AI Agent Testing Guide 2026, May 2026](https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026)
- Flag task completion, step efficiency, tool correctness, argument validity, plan adherence, and safety in every run. If you only track one number, track task completion rate — it is the bluntest signal but the hardest to argue with. — [Confident AI, LLM Agent Evaluation Guide, 2026](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)

## Evidence

- **Gartner via Multimodal.dev:** 79% of organizations have adopted AI agents; 57% have agents in production. Yet over 40% of agentic AI projects are at risk of cancellation by 2027 due to inadequate governance, observability, and ROI clarity. — [RockB, AI Agent Testing Guide 2026, May 2026](https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026)
- **arXiv research:** Agent-as-a-judge (evaluating intermediate steps and sub-requirements) achieved parity with human evaluators on code tasks while preserving the cost-effectiveness of LLM-based evaluation. Standard LLM-as-judge on final outputs only performed significantly worse. — [arXiv 2508.02994, Aug 2025](https://arxiv.org/html/2508.02994v1)
- **HN practitioner report:** Evals are a core driver of performance improvements in production AI systems. Without them, claims cannot be verified and regressions go undetected until users complain. — [HN comment by roadside_picnic, discussion on production AI agents, 2025](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **Eval inflation.** A score that consistently trends upward without corresponding business metric improvement means the eval is capturing something different from what matters. Re-examine your golden dataset.
- **Non-determinism masking real failures.** A single eval run is one sample. Run statistical significance tests on your eval results. If 3 out of 5 runs pass, your agent is not reliable.
- **Measuring the wrong thing.** Tracking tool call counts and latency without trajectory correctness lets an agent "pass" while producing subtly wrong outputs. Tie every metric to a trace.
- **LLM-as-judge overconfidence.** Frontier models have a tendency to rate outputs as acceptable even when they are not. Calibrate against human judgment, especially on safety-critical or edge-case inputs.
- **Silver dataset promotion without human review.** Synthesized data from agent simulations is useful for scale, but promotes systematic blind spots if not spot-checked by humans before promotion to gold.
