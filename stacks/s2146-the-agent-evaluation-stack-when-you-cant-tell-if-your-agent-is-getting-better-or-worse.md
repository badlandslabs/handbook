# S-2146 · The Agent Evaluation Stack — When You Can't Tell If Your Agent Is Getting Better or Worse

Your agent works. You shipped it. But you have no idea whether it is improving or degrading over time, whether the new model swap made it better or just more confident, or whether the flaky test that passed is actually reliable. The agent produces outputs — but you have no measurement system. This is the evaluation debt trap, and it is the reason fewer than 15% of enterprise AI pilots reach production scale.

Agent evaluation is not model evaluation. Models produce text; agents produce trajectories — sequences of decisions, tool calls, state changes, and final answers. Scoring the last message tells you nothing about whether the path was correct, efficient, safe, or reproducible. You need to evaluate the entire execution.

## Forces

- **Trajectories are invisible to final-answer scoring.** An agent can reach a correct answer via a broken path — hallucinated tool parameters, policy violations, unnecessary loops — and score green on a pass/fail. You ship the regression without knowing it.
- **Offline evals are necessary but not sufficient.** Curated test sets catch regressions and known failure patterns. They cannot anticipate real user behavior, drift under model version changes, or detect distribution collapse in production.
- **LLM-as-a-judge is powerful but biased.** Studies show 70–85% agreement with human reviewers on well-defined rubrics — roughly equal to inter-human agreement (~80–85%). But judges are systematically biased toward verbose outputs, prefer their own reasoning style, and show position effects on ranked options.
- **Measuring quality is different from observing behavior.** Traces tell you what the agent did; evals tell you whether what it did was right. Teams conflate the two and end up with beautiful dashboards over nothing measurable.
- **78% of enterprises have agent pilots; <15% reach production scale.** The primary blocker is evaluation infrastructure that hasn't kept pace with deployment. Pilots succeed on curated cases; production fails on real distribution.

## The move

Build a three-layer evaluation architecture that scores trajectories end-to-end, not just final answers.

### Layer 1 — Offline regression suite (pre-deploy gate)

Run curated golden datasets against every significant change. Use deterministic code-based assertions for measurable dimensions (exact match, format validation, schema compliance). Use LLM-as-a-judge for open-ended quality dimensions (helpfulness, clarity, tone). Block merges on regression. Re-run critical scenarios across model versions — stochasticity means a single pass is not a reliable signal.

- **Tools:** DeepEval (open-source, pytest-native, git-backed audit trail) for engineering-led teams. LangSmith for LangChain/LangGraph stacks. Braintrust for SaaS-first teams needing vendor-managed evaluation primitives.
- **What it catches:** Prompt regression, model swap regressions, tool interface breakage, known edge-case regressions.
- **What it misses:** Real user distribution gaps, silent trajectory failures (correct answer via broken path), distribution collapse over time.

### Layer 2 — Trajectory scoring (the missing middle)

Score the sequence of steps — not just the output. Key trajectory metrics:

- **Tool-call accuracy:** Did the agent call the right tools with valid arguments? Tool-call hallucination (calling a non-existent tool or malformed arguments) is invisible to final-answer scoring.
- **Step efficiency:** Did it reach the answer in a reasonable number of steps? An agent that reaches the correct answer in 20 steps with 3 policy violations is a failing trajectory.
- **Recovery rate:** Did it handle recoverable errors gracefully, or did it give up and fabricate a response?
- **Policy compliance:** Did it avoid disallowed actions, hallucinated entities, or off-task drifts across turns?
- **Handoff correctness:** In multi-agent systems, did the right agent receive the right context at the right time?

LangSmith trajectory evaluations, Confident AI's DeepEval traces, and arXiv's PAEF framework (Production Agentic Evaluation Framework) all implement this layer. Yehudai et al.'s 2025 survey identifies three failure modes entirely invisible to outcome-only metrics: tool-call hallucination, silent catch-handler masking, and cross-turn intent drift.

### Layer 3 — Production monitoring (continuous, sampled)

Sample live production traces and run online evaluations continuously. This layer answers: are we drifting from our quality baseline? What new failure modes are users encountering? Are the offline test cases still representative?

- **Human-in-the-loop calibration:** Sample 5–10% of traces for human review. Use human rubrics to calibrate LLM-as-a-judge. If the judge disagrees with humans systematically on a dimension, retune the rubric or swap the judge model.
- **Operating envelope tracking:** Monitor latency per task, cost per task, token efficiency, and tool reliability alongside quality scores. A technically correct agent that costs 10x the budget is not viable.
- **Promote failures to test cases:** A real production failure trace becomes a frozen CI regression test. This is the highest-signal test case you can have — it came from reality.
- **Per-turn classifiers:** Score each individual turn in production, not just the trajectory end. Catches jailbreaks, prompt leaks, policy violations, and user frustration signals invisible to trajectory-level or end-answer scoring.

### Judge design (for LLM-as-a-judge layers)

- Design 3–5 rubric dimensions that map to user value, not generic quality. Each dimension is a separate question to the judge, not a single monolithic score.
- Calibrate on human-reviewed samples before trusting the judge at scale. Validate on known-bad examples ("does the judge flag this clearly wrong output?").
- Be aware of known judge biases: verbosity inflation (longer outputs score higher regardless of quality), self-preference (GPT-4o judge favors GPT-4o outputs), and position effects (earlier options ranked higher).
- For cost-sensitive pipelines, small distilled judges (e.g., Luna-2 class) can achieve 88–95% judge accuracy at 97% cost reduction versus frontier models — making inline runtime verification economically viable.
- Intrinsic self-correction is unreliable without external grounding. "Check your work" prompts degrade performance on reasoning tasks; use structured verification against external sources instead.

## Evidence

- **arXiv paper (2025):** "Evaluating Agentic AI in the Wild" identifies 7 production failure modes unique to continuous agentic operation. Standard benchmarks (HELM, MT-Bench, AgentBench, BIG-bench) fail to detect 4 of 7 entirely and detect 3 others only after multi-cycle lag. PAEF detects all 7 within one cycle. — [arXiv:2605.01604](https://arxiv.org/pdf/2605.01604)
- **GitHub ADR (2026):** Architecture team at ThomasChangX/llm-reporting adopted PAEF in July 2026 after finding that 78% of enterprises have AI agent pilots but fewer than 15% reach production scale — primarily due to missing evaluation pipelines. Their ADR-0018 documents the decision. — [GitHub ADR-0018](https://github.com/ThomasChangX/llm-reporting/blob/main/adr/0018-agent-evaluation-framework.md)
- **Industry analysis (2026):** GitHub runs 4,000+ offline tests before any model deployment to Copilot, combining automated code quality assessments, LLM-based evaluation, and manual testing. 57%+ of surveyed production agent teams now use LLM-as-a-judge at runtime — crossed from eval harness to load-bearing infrastructure. — [GitHub AI Evals Blog](https://github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot/), [Zylos Research 2026](https://zylos.ai/research/2026-04-10-llm-as-judge-production-agent-verification-2026)
- **Framework comparison (2026):** DeepEval (open-source, pytest-native), Braintrust (SaaS eval primitives), LangSmith (LangChain/LangGraph native + observability), and Patronus AI (research-grade hallucination detection) each fit a distinct deployment shape — not interchangeable. Picking by generic feature matrix produces wrong procurement outcomes. — [AgentMode AI](https://agentmodeai.com/agent-eval-frameworks-deepeval-braintrust-langsmith-patronus/)

## Gotchas

- **Confusing traces for evals.** LangSmith/Braintrust/Galileo capture what the agent did. That is observability, not evaluation. You still need a rubric and a judge to determine if what it did was right. Beautiful trace UIs over zero measurable quality signals are decorative.
- **Single-run pass/fail is not a reliability signal.** Models are stochastic. Re-run critical scenarios at least 3–5 times and report pass rates, not single-pass outcomes. A 100% pass rate on one run is meaningless.
- **Outcome-only scoring misses the most expensive failures.** An agent that hallucinates a tool parameter, triggers a catch handler that produces a passable-looking result, and delivers a polite useless answer scores green on final-answer evaluation. In production it runs up costs, triggers monitoring alerts, and may cause real harm. Trajectory evaluation would catch this; outcome scoring would not.
- **Judge bias invalidated by production deployment.** If you deploy a GPT-4o-powered agent and use GPT-4o as the judge, the judge will systematically favor outputs that resemble its own reasoning style. Cross-model judges (e.g., Claude-as-judge for a GPT-4o agent) reduce this bias.
- **Offline evals go stale.** Test cases designed against last quarter's user distribution will not catch drift in this quarter's user behavior. Production sampling and failure-to-test-case promotion is the only mechanism that keeps the test suite fresh.
