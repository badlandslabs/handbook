# S-2879 · The Eval Infrastructure Stack — How Teams Measure Whether Their Agent Is Actually Working

Your agent handles 10,000 conversations a day. Your monitoring dashboard is green. Your benchmark scores look good. Then a customer screenshots a confidently wrong answer and posts it on Twitter. The gap between "the model answered" and "the agent worked" is where eval infrastructure lives — and most teams have none of it.

## Forces

- **Agents are systems, not models.** Evaluating at the model level (BLEU, MMLU, exact-match) misses every multi-turn failure mode: wrong tool selected, state drift, compounding errors, graceful recovery, tool reliability. Single-output benchmarks tell you nothing about whether the agent got there correctly.
- **The perception gap is real and dangerous.** 72% of AI teams believe comprehensive testing drives reliability, yet only 15% achieve 90%+ behavior coverage (Galileo, 2025). The majority are shipping on vibes.
- **Offline suites decay instantly.** An eval set is a snapshot of production traffic when it was written. Production traffic shifts daily. Keeping offline suites current is described by YC agent builders as "an impossible task" — ~90% report evals under-deliver for this reason. None of the major frameworks evaluate per-turn while the agent runs.
- **Step-level correctness ≠ trajectory correctness.** A 95% per-step success rate compounds multiplicatively: 5 steps × 95% = ~77% trajectory accuracy. Your step evals pass. Your agent fails end-to-end. (Anthropic, "Demystifying evals for AI agents," Jan 2026)
- **Human review doesn't scale.** Production deployments generate thousands of traces per day. Manual QA catches 1% of failures and is too slow to catch regressions before they ship.

## The move

Build a layered eval infrastructure that operates across three scopes, runs at multiple cadences, and feeds production traces back into the test suite.

**1. Measure across three scopes simultaneously**
- **Step/skill level** — Did the agent call the right tool with the right arguments? (deterministic code checks)
- **Trajectory level** — Did the agent take a sound path from input to output across the full sequence of reasoning → tool calls → state changes? (LLM-as-judge scoring the execution path)
- **Session level** — Did the agent complete the user's task correctly, end-to-end, with appropriate tone and safety? (outcome + quality judgment)

Braintrust codifies this as: **data + task + scorers**. The scorers cover both deterministic code checks (tool call shape, JSON schema, PII presence) and LLM-as-judge (reasoning quality, contextual appropriateness). Anthropic's terminology: **task** (the test case), **trial** (each attempt), and **grader** (the scoring logic — deterministic code, LLM-as-judge, or human).

**2. Run evals at two distinct cadences**
- **Offline / pre-deploy** — On every PR, run trajectory evals against a curated golden dataset. Catch regressions before they reach users. This is your regression suite.
- **Online / production** — Sample a percentage of live traces, score them with LLM-as-judge, and track quality drift over time. Braintrust calls this "production traces become test cases." Maxim AI and Galileo recommend online scoring on sampled traces with alerting on quality regressions.

**3. Use LLM-as-judge as your primary grader for trajectory quality**
Traditional token-overlap metrics (BLEU, ROUGE) measure whether the output looks like the reference — not whether the agent's reasoning was sound. An LLM judge scores trajectory quality across rubric-defined dimensions: reasoning coherence, tool selection appropriateness, groundedness in retrieved context, and recovery behavior.

Calibrate the judge: Anthropic recommends running multiple trials per task and comparing judge scores across model versions. The bias taxonomy to watch for (Zylos Research, 2026): position bias (judge favors first/last options), verbosity bias (judge favors longer outputs), self-preference bias (judge favors its own writing style). Mitigations include chain-of-thought judging, diverse judge ensembles, and explicit rubric constraints.

**4. Extend to Agent-as-a-Judge for adversarial evaluation**
Zhuge et al. (ICML 2025, Meta AI / LMU / NEC Labs) introduced the Agent-as-a-Judge framework — using multi-agent judge systems where different agents play roles (critic, defender, domain expert) and debate intermediate steps. This more closely emulates human panel evaluation and dramatically outperforms single LLM-as-judge in code-generating agent benchmarks. The agent-as-judge can provide intermediate feedback mid-trajectory, not just a post-hoc score.

**5. Make the eval loop close itself**
LangChain's eval framework and DeepEval both emphasize: production traces → golden datasets → offline evals → regression guard. Every production failure that slips through becomes a new test case. The eval suite grows organically from live failure patterns rather than from a priori guesswork.

**6. Track operational metrics alongside quality**
Task completion rate, cost per task, token efficiency, tool reliability, and policy compliance are first-class signals (InfoQ, March 2026). A 95% quality score on 10% of tasks that time out is not a 95% quality system.

## Evidence

- **Engineering post:** Anthropic's "Demystifying evals for AI agents" defines the three-scope framework (step, trajectory, session), the task/trial/grader vocabulary, and the compounding error problem — 95% per-step × 5 steps = ~77% trajectory accuracy. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Industry survey:** Galileo's State of Eval Engineering Report found 72% of AI teams believe comprehensive testing drives reliability but only 15% achieve elite (90%+) behavior coverage — a 57-point belief-execution gap. — [https://galileo.ai/blog/ai-agent-metrics](https://galileo.ai/blog/ai-agent-metrics)
- **Research paper:** Zhuge et al. (ICML 2025) — Agent-as-a-Judge: multi-agent evaluation frameworks where judge agents play adversarial roles, benchmarked against code-generating agents. — [https://proceedings.mlr.press/v267/zhuge25a.html](https://proceedings.mlr.press/v267/zhuge25a.html)
- **Framework docs:** Braintrust's eval pattern — data + task + scorers, production traces → test cases, code-based + LLM-as-judge dual scorers. — [https://www.braintrust.dev/articles/how-to-eval](https://www.braintrust.dev/articles/how-to-eval)
- **Framework docs:** DeepEval's trajectory-based evaluation — scores ordered step sequences, not just final outputs, across reasoning, tool selection, and task completion dimensions. — [https://deepeval.com/guides/guides-ai-agent-evaluation](https://deepeval.com/guides/guides-ai-agent-evaluation)
- **Industry analysis:** ~90% of YC agent builders report evals under-deliver because keeping offline suites current is "impossible." No major framework evaluates per-turn at production runtime. — [https://www.morphllm.com/ai-agent-evaluation-frameworks](https://www.morphllm.com/ai-agent-evaluation-frameworks)

## Gotchas

- **Writing a good rubric is harder than it looks.** LLM-as-judge scores are only as good as the rubric. Vague rubrics produce noisy, inconsistent scores. Invest in rubric engineering — define what "good tool selection" means in 3-5 specific behavioral criteria before you judge.
- **Judge bias poisons the measurement.** Position bias, verbosity bias, and self-preference are systematic. Use judge ensembles and compare judge scores across model versions to catch drift. A judge that always scores high is not evaluating.
- **Coverage != quality.** 90% test coverage of your agent's behaviors doesn't mean those tests catch real failures. The critical failure modes are the ones that never appeared in your golden dataset — which is why production sampling and auto-regression from failure traces is more valuable than expanding offline coverage.
- **Offline pass ≠ production safety.** An eval suite that runs only pre-deploy will miss regression introduced by data drift, model version changes, and tool API changes that happen post-deploy. Online production scoring is not optional for high-stakes agents.
- **You will underinvest in this until you have a public failure.** Like security, eval infrastructure is the thing every team deprioritizes until the first incident. Start with trajectory-level outcome tests and add online sampling before you have 10,000 daily users.
