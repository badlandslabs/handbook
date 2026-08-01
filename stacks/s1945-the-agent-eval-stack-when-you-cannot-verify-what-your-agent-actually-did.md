# S-1945 · The Agent Eval Stack

*When your agent passes every test, ships to production, and then quietly fails on the thing users actually care about.*

You have a test suite. You have BLEU scores. You have a demo where everything works. Then the agent gets into production and starts completing tasks "successfully" by reporting the right answer it got from last year's data, or calling the refund tool it found buried in the docs, or spending $4.80 on a task that should cost $0.12. Your eval suite is green. Your users are not.

## Forces

- **Single-turn metrics vs. multi-turn behavior** — BLEU and ROUGE were built for translation and summarization. Agents plan, use tools, adapt mid-flight, and fail in ways that make the final output look fine while the process was completely wrong.
- **Correct answer, wrong process** — An agent can reach the right output via a flawed trajectory. Standard output-based evals miss this. Google Cloud calls it a "silent failure" and argues trajectory analysis is non-negotiable for agents. — [Google Cloud Blog](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Cost and latency are evaluation targets, not just quality** — Enterprise agents show 50x cost variation ($0.10–$5.00 per task) at similar accuracy levels, and a 37% performance gap between lab tests and production. Accuracy-optimized agents cost 4.4–10.8x more than Pareto-efficient alternatives. These numbers don't show up in accuracy-only evals. — [arXiv 2511.14136](https://arxiv.org/html/2511.14136v1)
- **The demo-to-production eval gap** — Most teams bootstrap evals with toy scenarios. Real production failures come from edge cases that only emerge in real interactions: unexpected API schemas, user phrasing you didn't anticipate, tool error messages that break your parsing. You need production traces feeding back into your test suite.
- **LLM-as-judge has real failure modes** — Position bias (prefers first/last), self-bias (favors same-model outputs), verbosity bias (longer answers score higher), and familiarity bias (known patterns get credit even when wrong). The judge grades plausibility, not correctness, when it can't see the evidence. — [luismori.dev](https://luismori.dev/article/llm-as-a-judge-agent-app-evals-biases-fixes/)

## The Move

Build a layered evaluation system that treats agents as production services, not model outputs.

**1. Golden datasets from production traces, not imagination.** Mine failures from production logs. A good golden `Example` is a triple: `input` (full conversation) + `reference output` + `grader config`. Never write fictional test cases — you will get the scenarios you wrote, not the ones users will hit. Version every dataset change; a changed dataset invalidates historical comparisons. — [CallSphere](https://callsphere.ai/blog/golden-dataset-production-ai-agents-langsmith)

**2. Measure the trajectory, not just the destination.** Instrument `PreToolUse`, `PostToolUse`, and `SubagentStop` lifecycle events (Anthropic SDK hooks). Capture: which tools were called, in what order, with what arguments, and whether the agent recovered from failures. A trace that shows the right answer arrived via a broken path is a failed eval even if the output looks correct. — [TribeAI/claude-evals](https://github.com/TribeAI/claude-evals) · [Google Cloud](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)

**3. Cost and latency as first-class metrics.** Track cost-per-task, token efficiency, and step budgets alongside quality. An agent that scores 95% accuracy at $4.80/task is not better than one scoring 90% at $0.12/task — for most production use cases. GitHub Copilot runs over 4,000 offline tests covering automated code quality, chat capability, and safety before any model change reaches production. — [GitHub Blog](https://github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot/)

**4. Structured LLM-as-judge with strict rubrics, not open-ended opinions.** Ask judges to compare options, score against a rubric, or inspect a trace with evidence. Never ask for vague holistic scores. Layer deterministic checks for objective fields (did the agent call the right tool? with the right args? within the step budget?). Swapping candidate order and averaging eliminates position bias. — [luismori.dev](https://luismori.dev/article/llm-as-judge-agent-app-evals-biases-fixes/)

**5. Human calibration loop on sampled traces.** Sample 5–10% of production traces for human review. Use human verdicts to calibrate the LLM judge, not to replace it. When human and judge disagree, that's the signal — not the noise. A "metric green, user red" gap means your eval is measuring the wrong thing. — [Confident AI](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

**6. Gate CI on eval thresholds.** Integrate evals into your deployment pipeline with pass/fail thresholds. A score drop of 3+ points on critical test cases triggers a pipeline block, not a Slack notification. LangChain's CI/CD example uses `AgentEvals` and `OpenEvals` with LangSmith, running automatically on every PR with threshold-gated production promotion. — [LangChain Docs](https://docs.langchain.com/langsmith/cicd-pipeline-example)

## Evidence

- **GitHub Blog (Jan 2025):** GitHub runs over 4,000 offline tests across automated code quality, chat capability, and safety before deploying any model change to Copilot. They combine automated metrics with LLM-based evaluation and manual testing across multiple languages and frameworks. — [GitHub Blog](https://github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot/)
- **InfoQ (Mar 2026):** Documents that 83% of surveyed agentic AI evaluations focus on capability metrics while only ~30% cover human-centered and economic metrics — a systematic misalignment. Recommends hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis) with human judgment for tone, trust, and contextual appropriateness. — [InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)
- **arXiv 2511.14136 (2025):** Enterprise agent study: 50x cost variation across agents at similar accuracy, 37% performance gap between lab and production, accuracy-optimized agents costing 4.4–10.8x more than Pareto-efficient alternatives. Argues for multi-dimensional evaluation including cost, reliability, security, and operational constraints alongside accuracy. — [arXiv](https://arxiv.org/html/2511.14136v1)
- **TribeAI/claude-evals (Feb 2026):** Production eval framework for Claude Agent SDK with 50-case golden dataset, native SDK lifecycle hooks for trajectory analysis, and one-command model comparison. Targets teams hitting "how do we know if a model upgrade broke something" — [GitHub](https://github.com/TribeAI/claude-evals)
- **LangSmith CI/CD pipeline example:** Automated eval pipeline using LangGraph + LangSmith with threshold-gated production promotion. Triggers on code changes, PromptHub updates, and online evaluation alerts. Fail pipelines when eval scores drop; compare experiments side-by-side across prompts, models, and agent versions. — [LangChain Docs](https://docs.langchain.com/langsmith/cicd-pipeline-example)

## Gotchas

- **Benchmarks optimize for publishing, not production.** SWE-bench, WebArena, and AgentBench are useful for comparing frameworks and base models — they are not proxies for your production success rate. The scenarios that make your agent fail in production are almost never in the benchmark.
- **Your eval suite will drift from production.** Without a continuous pipeline feeding production failures back into the golden dataset, your eval suite becomes a measure of how well the agent handles your old problems while users discover new ones. Update the dataset every sprint, at minimum.
- **LLM-as-judge amplifies your rubric's biases.** If your rubric is vague, the judge's scores will be noisy and the eval will not be reproducible across runs. Write objective, evidence-grounded criteria. "Was the answer helpful?" is not a rubric. "Did the agent call the correct tool with valid arguments within the step budget?" is.
- **Passing evals doesn't mean the agent is ready.** A passing eval means the agent handles the test cases you wrote. The agent is production-ready when you've also done red-team probing, chaos testing on tool failures, and load testing for cost/latency at scale.
