# S-1761 · The Trajectory Grade Stack

When your agent gets 97% on your benchmark and 60% of production requests expose a silent failure — wrong tool called first, lucky recovery, ignored constraint that didn't bite this time. The benchmark was a finish-line photo. The real evaluation is the whole race.

## Forces

- **Endpoint scoring is blind to path** — two agents reach the same correct answer, but one used three precise tool calls and the other thrashed through a dozen irrelevant steps. Final-answer grading calls them identical.
- **Benchmarks certify point-in-time, not production** — GPT-4 showed measurable behavior changes across versions: tasks at 97% accuracy in March 2023 dropped to 87% by June 2023 on the same benchmark (Chen et al., "How Is ChatGPT's Behavior Changing over Time?").
- **Agents are systems, not models** — evaluating a foundation model's capabilities tells you nothing about whether your agent's tool-calling policy, error recovery logic, and memory retrieval are wired correctly. An agent can be built on a brilliant model and still fail because of assembly mistakes.
- **Classical metrics don't apply** — BLEU and ROUGE scores measure surface-level text similarity, not whether the agent took the right action, called the right API, recovered from a failure, or stayed within policy constraints.

## The Move

Evaluate trajectories, not answers. Grade the full run — which tools were called, in what order, with what arguments, whether each step satisfied policy — and you surface the failure modes that endpoint scoring hides.

**The four-layer production eval stack:**

1. **Trajectory instrumentation first.** Log complete traces: plans and subgoals, every tool call with parameters and responses, intermediate reasoning steps, final answer, and side effects. Without this you have nothing to evaluate. Tools: OpenTelemetry + Langfuse, Maxim, Phoenix (Arize), or Weights & Biases W&B.

2. **Multi-dimensional trajectory metrics.** Task Success Rate (TSR) tells you if the agent resolved the intent. But also track: Trajectory Efficiency (steps/tokens per success), Tool Call Accuracy (right tool, right parameters), Step-level policy compliance, and failure-mode distribution (plan failure vs. tool failure vs. environment failure). NVIDIA recommends separating TSR by scenario type — normal, degraded tools, ambiguous instructions — to expose brittleness.

3. **LLM-as-a-judge as the workhorse evaluator.** Large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes verification; small distilled judges (Luna-2 3B–8B, Prometheus 2 7B, Patronus Lynx 8B) for high-throughput inline checks. Small models deliver 97% cost reduction at 0.88–0.95 accuracy versus their large counterparts. Critical: self-correction only works when grounded in external feedback — prompting "check your work" without grounding degrades reasoning performance. Judge patterns:
   - **Offline async** — run after the fact, latency irrelevant, bounded cost per run
   - **Online runtime gate** — synchronous in the request path, blocks delivery until approved (Amazon Prime Video's pattern for quality-critical outputs)
   - **Synthetic golden dataset generation** — RAGAS generates test question-answer pairs using the actual retrieved context, so eval covers your actual retrieval pipeline

4. **CI/CD regression gates.** Embed eval into your pipeline with three tiers:
   - **PR tier (minutes, cheap)** — 50–200 curated examples, per-step rubrics, LLM-as-judge, blocks merge on threshold breach
   - **Nightly tier (hours, moderate cost)** — expanded suite with replay harnesses against captured production traces, statistical regression tracking
   - **Production tier (sampled, continuous)** — online evaluators on a percentage of live traffic, alert on drift from baseline

## Evidence

- **NVIDIA Technical Blog (2026):** Final-answer grading treats agents as identical when one uses three precise tool calls and another thrashes. Recommends measuring Task Success Rate per scenario type (normal, degraded tools, ambiguous instructions), trajectory efficiency, and failure-mode distribution. — [developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)

- **jamesm.blog (2026):** Minimum viable production eval: 50–200 real examples, per-step rubrics, 10+ runs per example, statistical regression tracking, and a held-out set never tuned against. Replay harnesses re-run captured traces against new models or policies without re-hitting production. Endpoints certify answers, not behavior. — [jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)

- **Zylos Research (2026):** >57% of production agent teams now use judge LLMs at runtime. Two-tier pattern: large proprietary judges for high-stakes verification, distilled small judges (Luna-2, Prometheus 2, Patronus Lynx) for high-throughput inline checks — 97% cost reduction at 0.88–0.95 accuracy. Self-correction without external grounding degrades performance; only works when grounded. — [zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

- **InfoQ (2026):** An order-triage agent correctly identifies a shipping exception in step one, but when the refund API returns an unexpected error in step two, the agent silently skips the refund and reports the case as resolved. No single-turn accuracy test catches that failure. Recommends hybrid evaluation: automated scoring (LLM-as-judge, trace analysis) for repeatability + human judgment for tone, trust, and contextual appropriateness. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **arXiv 2507.21504 (KDD 2025):** Survey of agent evaluation taxonomy: two-dimensional framework organizing evaluation into Evaluation Objectives (what to measure) and Evaluation Process (how to measure). Key finding: agent evaluation assesses a car's performance comprehensively under various driving conditions, not just the engine's power on a dyno. — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)

## Gotchas

- **Benchmarks decay.** Static task-completion scores fail to capture reliability, cost efficiency, safety, and long-horizon competence. Treat benchmarks as pre-deployment sanity checks, not release gates.
- **Self-grounding self-correction is unreliable.** Prompting "recheck your answer" without external grounding consistently degrades performance — the agent reinforces its initial reasoning rather than catching errors. Only use reflection loops when grounded in retrieved evidence or tool feedback.
- **Held-out sets get contaminated.** If you tune against your eval set repeatedly, you get measurement without generalization. Keep a sealed holdout set that is never used during development, only for final certification.
- **Three eval frameworks, not one.** RAGAS for synthetic test generation and experimentation, DeepEval for CI regression gates (50+ metrics, pytest-native), TruLens for production tracing — they are layers of one stack, not competitors. Using only one creates blind spots.
- **Context-dependent judges hallucinate.** LLM-as-judge frameworks cannot catch wrong-but-plausible context on highly specialized domains. Domain calibration (domain expert review of judge outputs) is mandatory for high-stakes applications.
