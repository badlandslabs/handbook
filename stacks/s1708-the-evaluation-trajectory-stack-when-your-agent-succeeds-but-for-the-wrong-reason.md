# S-1708 · The Evaluation Trajectory Stack — When Your Agent Succeeds But for the Wrong Reason

Your agent passes every test. The output is correct. You ship it. Three weeks later it starts failing in production — not because the answer changed, but because the reasoning path shifted. The model found a cheaper shortcut that works most of the time but breaks on edge cases. Your eval suite never caught it because you were grading the output, not the trajectory. Standard LLM evaluation (prompt in, answer out, pass/fail) cannot catch errors that live inside the agent's decision chain — and those are the errors that cost the most in production.

Agent evaluation is fundamentally different from LLM evaluation. Agents produce trajectories — sequences of tool calls, state changes, memory operations, and reasoning steps — not single outputs. A mistake in step 3 corrupts everything that follows. The eval must account for the path, not just the destination.

## Forces

- **Trajectory vs. output** — an agent can reach a correct answer via a flawed or lucky reasoning chain; grading only the final output misses it
- **Multi-dimensional quality** — accuracy alone ignores the 50x cost variation ($0.10–$5.00/task) for comparable accuracy; optimizing accuracy alone yields agents 4.4–10.8x more expensive than necessary
- **Consistency under repetition** — single-run pass rates for agentic tasks drop from ~60% to ~25% when run 8 times; one trial is not enough
- **Path vs. outcome divergence** — the model may find a correct-but-wrong-path that breaks in edge cases (Anthropic's Claude 4.5 booked a flight by exploiting a policy loophole; it "failed" the eval but solved the real problem better)
- **Golden dataset maintenance debt** — test cases grow stale as the world changes; without versioning, passing evals become false confidence

## The Move

Build a structured evaluation pipeline that grades both the trajectory and the outcome, runs multiple trials, and lives in CI. The stack has five layers:

- **Golden dataset (ground truth cases)** — 5–10 manually curated examples per critical workflow, versioned alongside code. Start narrow. LangChain's own team recommends starting with "5-10 examples per workflow" and growing the dataset as new failure patterns emerge. Each case needs: input, expected trajectory shape, expected outcome, and edge case flags.
- **Tracer (instrument once, use everywhere)** — add tracing at the agent architecture level (DeepEval's `@observe` decorator, LangChain/LangGraph integrations, Claude SDK hooks). One instrumentation pass emits traces for every run — spans covering LLM calls, tool invocations, retriever hits, sub-agent delegations. Reuse traces for both component-level and end-to-end evaluation.
- **Grader (test the trajectory, not just the answer)** — for deterministic workflows use code-based sequence matching (faster, reproducible). For open-ended or ambiguous tasks use LLM-as-judge for semantic evaluation. The grader must check: tool selection correctness, step ordering, intermediate state changes, final output, and cost-per-step. Braintrust recommends checking both outcome AND path — "the difference between a prototype and a production-ready system comes down to structured evaluation."
- **Multi-trial consistency check** — run each task at least 3–5 times to surface inconsistency. A single passing trial is not a passing agent. Track the pass@3 or pass@5 rate, not pass@1. Anthropic's engineering guide explicitly separates Task (test case), Trial (single attempt), Grader (scoring logic), and Transcript (complete trace) — multiple trials per task is a first-class concern.
- **CI gate with regression tracking** — hook eval runs into the deployment pipeline. Track pass rates over time per workflow. Any regression in pass rate, consistency, or cost-per-task should block deploys. DeepEval supports pytest-style assertions for CI gating. AWS Labs' agent-evaluation framework (369 GitHub stars, 276 commits) is built explicitly around CI/CD integration with configurable evaluators and production monitoring hooks.

**The multi-dimensional frame.** The CLEAR framework (Cost, Latency, Efficacy, Assurance, Reliability) from enterprise agent research surfaces what accuracy-only evaluation misses: agents optimized purely for accuracy often achieve it through excessive tool-calling and re-planning loops. Track all five dimensions. Set cost and latency budgets alongside accuracy thresholds.

## Evidence

- **GitHub Engineering:** Runs over 4,000 offline tests — automated code quality assessments, chat capability evaluations, and safety checks — before any model change reaches production. Combines automated metrics, LLM-based evaluation, and manual testing across multiple languages and frameworks. — [GitHub AI Model Evaluation Blog](https://github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot/)
- **Anthropic Engineering:** Claude 4.5 "failed" a τ²-bench evaluation on flight booking by discovering and exploiting a policy loophole — the eval was static and couldn't account for a creative correct solution. This illustrates why eval design matters: a poorly written grader can penalize a better solution. — [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **arXiv 2511.14136:** Enterprise agent study found accuracy-only optimization yields agents 4.4–10.8x more expensive than cost-aware alternatives with comparable performance. Consistency drops from ~60% (single run) to ~25% across 8 runs. 50x cost variation ($0.10–$5.00/task) for similar accuracy goes unmeasured by most benchmarks. — [Beyond Accuracy: A Multi-Dimensional Framework for Enterprise Agentic AI](https://arxiv.org/html/2511.14136v1)
- **Braintrust:** "An AI agent that performs well in demos could hallucinate instructions, call the wrong APIs, repeat the same actions in loops, and produce outputs that miss the original request entirely." Multi-step agent eval must examine both outcome and the path taken. — [AI Agent Evaluation: A Practical Framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- **DeepEval (Confident AI):** Tracing-based eval: `@observe` decorator instruments once, traces cover every component (LLM calls, tools, retrievers). Metrics attach at trace-level for end-to-end and span-level for components. Supports pytest assertions for CI gates. — [DeepEval: AI Agent Evaluation Quickstart](https://deepeval.com/docs/getting-started-agents)
- **LangChain / Zylos Research:** 57% of organizations have agents in production (2026 State of AI Agents), but 32% cite quality as the biggest barrier. 37% gap between lab benchmark scores and real-world performance. — [Zylos Research: AI Agent Testing Strategies](https://zylos.ai/research/2026-04-20-ai-agent-testing-strategies-simulation-regression)

## Gotchas

- **One trial is not a pass** — single-run pass rates for agentic tasks are systematically optimistic; run 3–5 trials and track pass@N, not pass@1
- **Output-only grading misses wrong-path correctness** — a correct answer reached via a flawed or looping trajectory will pass a simple output check; grade the trajectory
- **Golden datasets go stale** — treat test cases like code: version them, add to them on every production failure, review them quarterly
- **Accuracy-only budgets burn money** — the CLEAR research shows teams routinely over-spend on agents 4–10x what a cost-aware alternative would need; set cost-per-task budgets alongside accuracy thresholds
- **Static evals can't judge creative solutions** — Anthropic's Claude 4.5 case proves it: an eval that only recognizes expected paths will penalize agents that find better ones; build grading rubrics that reward correct outcomes, not expected trajectories
