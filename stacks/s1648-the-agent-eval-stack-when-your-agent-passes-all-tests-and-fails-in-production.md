# S1648 · The Agent Eval Stack: When Your Agent Passes All Tests and Fails in Production

You have an agent that scores 97% on your eval suite, runs flawlessly in staging, and surfaces a new failure class every Monday morning from production traffic. The gap between eval signal and production reality is where agents quietly destroy trust.

## Forces

- **Benchmarks measure completion, not correctness.** A task-completion rate of 95% can coexist with a 30% actual-task-success rate when the agent completes the wrong action (wrong tool, wrong parameter, wrong goal interpretation). Standard metrics don't catch goal misalignment.
- **Trajectories are invisible in final-output evals.** An agent can reach the right answer through a broken reasoning chain, making the destination look valid while the path would fail on any variation.
- **LLM judges are confidently wrong without calibration.** Anthropic research found 62% of teams using unvalidated LLM judges report systematic bias — typically a 40% verbosity bias (longer responses score higher) and position bias (first/last items favored).
- **Production distribution drifts constantly.** Model version updates, API changes, and user input distribution shifts all change agent behavior. An eval that passed in March may be meaningless by June — GPT-4 showed measurable behavior changes across versions that degraded some task accuracy from 97% to 87% within months.
- **Golden dataset construction is undervalued.** Teams skip it because it feels slow, then pay through reactive firefighting and silent failures.

## The Move

A layered eval stack that operates across the full agent lifecycle — offline before deployment, trajectory-level during development, session-level at integration, and production-level at runtime.

### Layer 1: Offline Capability Benchmarks (Pre-Deployment)

- Build a **golden dataset** of 200–500 real production queries with verified correct answers — sampled from actual user inputs, not synthetic. Mix: ~60% common flows, ~25% edge cases, ~15% high-risk/intent-critical paths.
- Include **expected trajectory metadata** — what tools should be called, in what order, with what parameters — not just final answers. This enables trajectory-level eval, not just outcome eval.
- Run benchmarks on every model upgrade, prompt change, and tool schema change. Treat as CI gate, not optional.

### Layer 2: Trajectory Quality (Development / Pre-Production)

- Evaluate the **reasoning path**, not just the destination. Check: correct tool selection, correct argument construction, appropriate loop count (agent didn't give up or loop indefinitely), and coherent intermediate reasoning steps.
- Use **Agent-as-a-Judge** (Zhuge et al., 2025) — a specialized evaluator agent that assesses reasoning quality alongside outcome. Particularly valuable when the journey matters as much as the answer.
- Run automated regression on the full golden set on every commit. Gate merges on trajectory-pass thresholds, not just task-completion rate.

### Layer 3: Session-Level Outcomes (Integration / Staging)

- Measure **task success rate** against the golden dataset — not just "did it complete" but "did it achieve the user's actual intent." These diverge frequently when agents optimize for the wrong proxy.
- Track **step efficiency**: number of tool calls per task, cost per task, latency per task. Inefficiency is a failure mode even when the outcome is correct.
- Capture **failure mode taxonomy**: categorize failures into goal misalignment, tool selection errors, hallucinated steps, planning failures (give-up/loop), and edge case failures. Review failure distributions weekly.

### Layer 4: LLM Judge Calibration (If Used as Automated Evaluator)

- **Never deploy an unvalidated LLM judge.** An unevaluated judge is worse than no eval — it produces confident wrong signals that look trustworthy.
- Run the judge against **human-labeled subset** of the golden dataset first. Require **0.75+ Fleiss kappa** agreement with human annotators before using at scale.
- Calibrate for known biases: verbosity bias (longer responses inflate scores by ~40%), position bias (first/last options favored), and self-preference bias (judge favors responses similar to its own style).
- **Monitor judge drift over time.** Re-run calibration on a monthly cadence or after model upgrades.

### Layer 5: Production Observability and Alerting (Runtime)

- Instrument traces for every LLM call, tool invocation, and control-flow decision — capturing prompts, completions, token usage, cost, latency, and retrieved context.
- Alert on **leading indicators before user-visible failures**: error rate > 10% in rolling 100-task window, quality score average < 0.7, cost spike beyond threshold, or tool success rate degradation.
- Implement **shadow mode eval**: run production inputs through eval pipeline with a delay, surfacing failures before they cluster into incidents.
- Use **OpenTelemetry with AI semantic conventions** (adoption grew 30% QoQ through 2025) for standardized, vendor-agnostic traces across Langfuse, LangSmith, or custom backends.

## Evidence

- **arXiv Survey (KDD '25):** Comprehensive taxonomy of LLM agent evaluation across two dimensions — evaluation objectives (behavior, capabilities, reliability, safety) and evaluation methods (reference-based, model-based, human-based). Introduces the "engine vs. car" analogy: LLM eval examines an engine; agent eval assesses the full car under varied driving conditions. — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)
- **Production Failure Analysis (2025):** Empirical study of production agentic systems finding that standard metrics fail to detect seven critical failure modes including goal misalignment, tool hallucination, and planning failures. Introduces PAEF (Production Agentic Evaluation Framework) with five evaluation dimensions for continuous production monitoring. — [arXiv:2605.01604](https://arxiv.org/html/2605.01604v1)
- **LLM Judge Calibration Research:** Found that 62% of teams using unvalidated LLM-as-Judge evaluators report systematic bias, with average human-evaluator agreement at 0.52 (far below the 0.75+ threshold required for reliable use). Verbosity bias inflates scores by ~40% on longer responses. — [eval.qa](https://www.eval.qa/learn/llm-judge-calibration.html)
- **Langfuse Agent Observability Guide (2025):** Documents that complete agent observability must capture LLM calls, tool calls, control flow, retrieved context, session grouping, and quality signals — and that failures hide in intermediate steps, not in final answers. — [Langfuse Blog](https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse)
- **Gartner Projection (2026):** Projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring rather than model capability gaps. — [thinking.inc](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production)
- **Golden Dataset Guide:** Best-practice recommendation of 200–500 examples minimum for core flows, sampled from real production queries (not synthetic), with monthly refresh cadence and immediate refresh on policy/product changes. — [datasops.com](https://www.datasops.com/blog/llm-evaluation-evals)

## Gotchas

- **Task-completion rate ≠ task-success rate.** A 95% completion rate can mask 30% actual user-intent failures if the agent is completing the wrong action. Always eval against intent, not activity.
- **Synthetic golden datasets fail.** Models trained on the same synthetic data as the agent will overfit. Start with real production queries and annotate those.
- **LLM judges default to "helpful" not "accurate."** They reward verbose, well-formatted outputs even when wrong. Calibration against human labels is not optional.
- **Eval is not one-time.** Gartner's 40% failure-from-eval-gap projection assumes continuous evaluation, not point-in-time certification. Set up regression gates and monitor drift.
- **Platform choice locks you partially.** LangSmith covers the full lifecycle (eval + alerting + managed deployment); Langfuse is open-source for tracing/prompts but lacks production alerting depth. Choose based on where you need the most coverage.
