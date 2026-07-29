# S-1831 · The Agent Trajectory Evaluation Stack — When Your Agent Passes All Checks and Still Fails in Production

Your agent scores 97% on final-answer accuracy. Your CI pipeline is green. Your LLM-as-judge gives it high marks. Then it ships to production and starts producing subtly wrong data, violating policy on edge cases, and taking 40 steps instead of 4. The problem isn't that you didn't evaluate — it's that you were measuring the wrong unit. Agents aren't prompts with longer outputs. Evaluating only the final answer is like checking if a program compiled and ignoring whether it was correct.

## Forces

- **Agents fail mid-trajectory, not at the endpoint.** The final answer can be right while the agent violated policy, wasted tokens, or corrupted intermediate state. Outcome metrics alone miss this entirely.
- **LLM outputs are non-deterministic.** A task that succeeds once can fail three times in a row due to sampling variance. Evaluating a single run is measuring noise, not capability.
- **Standard benchmarks don't cover your domain.** SWE-bench tests code agents; WebArena tests web agents. Production customer-service, financial, or healthcare agents have no canonical benchmark — you must build your own eval set.
- **LLM-as-judge correlation with human judgment decays.** An 0.80 Spearman correlation sounds good but means the judge disagrees with humans 20% of the time — which compounds across thousands of production runs.
- **Trajectory evaluation is expensive.** Running an LLM judge on every step of every trace multiplies compute costs by 5–20x vs. final-answer-only evaluation.

## The Move

Separate the evaluation layers explicitly. Measure what each layer catches and what it misses.

**1. Outcome evaluation (black-box) — is the final state correct?**
The simplest layer. Does the database have the right reservation? Is the PR created? Did the ticket get routed correctly? Use programmatic ground-truth checks wherever possible — compare against a deterministic reference. For agents that can produce equivalent outputs in different formats, use answer-matching with normalization (strip punctuation, normalize whitespace and units, case-insensitive comparison). This layer is cheap, fast, and catches obvious failures.

**2. Trajectory evaluation (gray-box) — was the reasoning path sound?**
The agent took 15 steps. Was that reasonable? Did it call the right tools in the right order? Did it recover from a bad intermediate result? LangChain's `agentevals` package and Langfuse's trajectory evaluators run an LLM-as-judge over the full trace with a rubric. Key rubric dimensions: tool call correctness, information-seeking efficiency, policy compliance, and graceful degradation. LangSmith supports both trajectory-match (hard-coded reference path) and LLM-as-judge (flexible qualitative assessment).

**3. Step-level evaluation (white-box) — was each individual decision correct?**
Unit-test each decision point. Does the search query it generates actually retrieve relevant results? Are the API parameters correct? Is the tool selection appropriate for the intent? Langfuse calls this "Single Step Evaluation" — it isolates individual reasoning steps and validates them against expected outputs. This catches tool-call hallucinations (selecting a tool that doesn't exist) and parameter errors before they cascade through the full trajectory.

**4. Calibrate LLM-as-judge with human review.**
Run 50–100 samples through both human raters and LLM judges. Compute Spearman correlation. Reject judge prompts scoring below 0.75 correlation — tune the rubric (fewer dimensions, concrete examples, simpler scale). LangSmith supports routing samples to human reviewers for disagreement flagging, which feeds back into rubric refinement. The goal is a judge that agrees with domain experts at 0.80+ correlation — not perfect, but stable enough to catch regressions.

**5. Use domain-specific benchmarks, not generic ones.**
SWE-bench Verified tests code agents (Claude 4.5 Opus hits 91.3% as of 2026). WebArena tests web agents (812 tasks across e-commerce, forum, GitLab, CMS). GAIA tests general assistants (best open-source agents hit 55% overall in 2025). For customer-service: tau-bench (Sierra AI) evaluates policy compliance and task success in retail and airline domains using pass^k — measuring consistency across k repeated runs, not just single-run success. If your domain has no standard benchmark, build a golden dataset of 200–500 task cases with known-good outcomes and human-validated trajectories. AgentV (najeed/ai-agent-eval-harness) provides 5,000+ out-of-the-box scenarios across 50+ industries as a starting point.

**6. Integrate eval into CI/CD, not as a pre-launch gate.**
Teams that evaluate once before production see quality degradation within 30–60 days (Deloitte enterprise AI study, 2025). Trigger evaluations on: every commit (regression check), nightly batch (drift detection), and production traffic sampling (shadow mode — run agent and judge in parallel, log disagreements without blocking). Run statistical significance tests on results before declaring a regression or improvement.

**7. Track the four converging dimensions.**
Per RPABots.world's framework: output quality (correctness, groundedness, relevance), trajectory quality (tool call sequence, order, efficiency), latency and efficiency (p50/p95/p99 latency, token count, cost per task), and safety and guardrails (policy compliance, toxicity, scope adherence). A task isn't passing if it achieves the right answer in 60 seconds when the SLA is 10 seconds — that's still a failure.

## Evidence

- **Anthropic Engineering Blog:** Anthropic's own evaluation framework distinguishes task (test case with defined inputs and success criteria), trial (single attempt), grader (scoring logic), and harness (the infrastructure running everything end-to-end). Key insight: when evaluating "an agent," you're evaluating the harness and the model together — Claude Code and the Agent SDK are harnesses. Claude 3.5 Sonnet (Oct 2024) scored 49% on SWE-bench Verified, which they raised by treating the harness as part of the evaluation scope. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Sierra AI tau-bench:** The benchmark's key innovation is the pass^k metric — measuring an agent's probability of success across k repeated trials, not single-run accuracy. This directly addresses LLM non-determinism. The paper also separates policy compliance from task success: an agent that resolves a request but violates policy still fails. Open-source at [github.com/sierra-research/tau-bench](https://github.com/sierra-research/tau-bench). — [URL](https://sierra.ai/blog/tau-bench-shaping-development-evaluation-agents)
- **Langfuse/Pydantic AI cookbook:** Three evaluation strategies — black-box (final output only), gray-box (trajectory with LLM-as-judge), and white-box (single-step unit testing). Langfuse's cookbook demonstrates all three with code: define evaluators for correctness, groundedness, and tool selection, then run them against a benchmark dataset in CI. Emphasizes that the "loop" (one reasoning-action cycle) is the fundamental unit of analysis for agent observability. — [URL](https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation)
- **LangSmith trajectory evals:** Two approaches: trajectory match (hard-code a reference path, validate step-by-step) for well-defined workflows, and LLM-as-judge (flexible qualitative validation) for assessing efficiency and nuance. LangChain's `agentevals` package supports both patterns with live model calls. Human review routing for disagreement flagging is built into the platform for judge calibration. — [URL](https://docs.langchain.com/langsmith/trajectory-evals)
- **LangChain Agent Development Lifecycle:** Teams that iterate fastest treat production traces as the starting point for LLM evaluation. Production traces feed observability, Insights extracts usage patterns, findings shape datasets, datasets power evaluations. This closed loop is what distinguishes teams that catch regressions before users do. — [URL](https://www.langchain.com/resources/agent-evals)
- **Thoughtworks Australia (2026):** Production eval framework for enterprise agents. Key findings: 95% of AI projects fail not because models are bad but because organizations can't measure if systems work. Traditional testing assumes determinism — it doesn't hold. Framework recommends three eval tiers: unit (individual skills), integration (coordination flow), and end-to-end (production-like scenarios). Continuous evaluation vs. one-time pre-launch reduces production incidents by 67% per Deloitte AI Ops analysis. — [URL](https://www.thoughtworks.com/en-au/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)

## Gotchas

- **Scoreboard inflation from single-trial evaluation.** A model that scores 90% in one run may score 72% on pass^5 (success across 5 trials). Always report pass^k, not single-run accuracy, for production-facing claims.
- **Judge rubric complexity.** More rubric dimensions (7+) sounds more thorough but drops LLM-as-judge reliability. Stick to 3–5 concrete dimensions with at least one worked example per score level.
- **Groundedness vs. correctness confusion.** An agent can be well-grounded (correctly uses retrieved docs) but factually wrong if the docs themselves are wrong. Evaluate both: does it use the right sources, and are the sources right?
- **Scope creep in eval datasets.** Teams add cases that are interesting but don't represent production distribution. The eval set must reflect what users actually ask, not what engineers think they should ask. Use production trace sampling to keep the dataset grounded.
- **Eval harness overhead is invisible until it's blocking deploys.** Trajectory evaluation with an LLM judge adds 5–20x compute vs. final-answer-only. Budget this in CI timeouts and cost models from day one.
