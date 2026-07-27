# S-1715 · The Judge Stack — When Your Agent Grades Its Own Homework

You shipped the agent. The benchmark pass rate is 94%. Your users are complaining the agent confidently writes wrong code, approves flawed outputs, and contradicts itself mid-reasoning. The benchmark never caught it — the benchmark was written by the same team that built the agent. You need a judge that doesn't share the agent's context, its training biases, or its incentive to finish the task.

This is the evaluator problem in production agentic systems. Ground-truth labels are sparse, expensive, and stale the moment your agent evolves. LLM-as-judge closes the gap — but it has its own failure modes.

## Forces

- **Ground truth is the bottleneck.** Building a labeled eval set for a live agent costs weeks of SME time and goes stale with every prompt or model change.
- **Agents optimize to the metric, not the mission.** An agent trained against a static benchmark learns to pass the benchmark, not to solve the underlying problem well.
- **Judges carry the same model's biases.** A judge that shares the agent's model family has the same failure modes — it won't catch hallucination patterns that are native to that architecture.
- **Evaluation cost compounds at scale.** Running GPT-4o as a judge on every agent output at production volume is economically viable at small scale; at 100K calls/day it becomes the dominant cost center.
- **Process vs. outcome is a false choice.** Traditional evals measure the final answer. Agentic systems fail in the middle — wrong tool calls, reasoning loops, premature commitment. You need both.

## The move

### 1. Separate the judge from the agent

The evaluator should not share the agent's model, context window, or system prompt. Microsoft's multi-agent reference architecture explicitly calls this out: the evaluator is its own agent with its own observation access and scoring rubric. A judge built on the same model as the agent has structurally limited ability to catch that model's failure modes.

**In practice:** Use GPT-4o or Claude 3.7 Sonnet as high-stakes judge; use a small distilled judge (Prometheus 2 7B, Patronus Lynx 8B, or Galileo Luna-2 3B/8B) for inline per-step gating where cost matters.

### 2. Layer deterministic checks before the LLM judge

Not everything needs an LLM to evaluate. JSON schema validation, regex checks, API contract enforcement, and code compilation all run deterministically at near-zero cost. The LLM judge handles the fuzzy middle — did the agent's reasoning follow a logical path? Is the answer faithful to the retrieved documents? Does the output match the implied intent?

**In practice:** Run schema validation first. If it passes, run the LLM judge. If it fails, fail fast without spending judge tokens.

### 3. Use a rubric-first evaluation prompt

Judges perform poorly on vague instructions. Decompose the evaluation into explicit criteria — Harsh Rastogi from Asynq.ai and Modelia.ai recommends scoring each dimension independently (correctness, safety, coherence, tool use fidelity) rather than a single overall pass/fail. Promptfoo's recommended approach uses graduated scoring anchors ("8/10: answer is correct but uses slightly outdated terminology") rather than binary judgments.

**In practice:** Write the rubric before you run the judge. Test it on 20 manually-labeled examples. Measure inter-annotator agreement between the judge and your SMEs.

### 4. Gate on process, not just outcome

Code-based evaluation (does it compile? do the tests pass? does the refactor preserve the API contract?) catches a different class of failure than outcome evaluation. Microsoft recommends four evaluation types in multi-agent systems:

- **Code-based:** execution, compilation, test pass/fail
- **LLM-based:** coherence, reasoning quality, faithfulness to intent
- **Rule-based:** safety violations, PII leakage, policy breaches
- **Reference-based:** comparison against known-good outputs

Run all four. A plan-and-execute agent that produces a working final output via a broken intermediate step still failed — process gates catch this.

### 5. Calibrate judges against human labels before deploying

The Zylos Research 2026 study found that LLM judges achieve 0.88–0.95 accuracy on agentic evaluation tasks when properly calibrated. Uncalibrated judges on novel tasks can be worse than random. The calibration workflow (Promptfoo's approach): pick one evaluation dimension → create 20 hand-labeled examples → score with judge → compute agreement → iterate rubric → deploy.

### 6. Use distilled judges for inline gating, proprietary judges for high-stakes decisions

Galileo Luna-2 3B/8B achieves 97% cost reduction versus GPT-4-based evaluation at 0.88–0.95 accuracy on agentic tasks (Zylos, 2026). For per-step inline checks in a long agent run, this is the right tradeoff. For final output gating, approval of a medical diagnosis, or any high-stakes decision, a capable proprietary judge is worth the cost.

## Evidence

- **Microsoft Multi-agent Reference Architecture:** Documents the four evaluation types (code-based, LLM-based, rule-based, reference-based) and the Planner → Executor → Verifier pipeline where a dedicated verifier agent judges each step's output before the next step begins. — [Microsoft/multi-agent-reference-architecture](https://microsoft.github.io/multi-agent-reference-architecture/docs/evaluation/Evaluation.html)
- **Zylos Research (2026):** Survey of production agent teams: 57%+ now use judge LLMs at runtime for quality gating. Large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes; small distilled judges (Luna-2 3B/8B, Prometheus 2 7B) for inline checking — 97% cost reduction at 0.88–0.95 accuracy. "Self-correction is unreliable without external grounding." — [Zylos.ai](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)
- **Asynq.ai / Modelia.ai production postmortem:** Candidate evaluation agent hallucinated tool parameters and contradicted own reasoning; image generation agent approved obviously flawed outputs. Root cause: evaluation was based on final output only, not step-by-step verification. Fix: structured JSON scratchpad (working memory) + per-step verification before proceeding. — [Harsh Rastogi, March 2026](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Promptfoo LLM-as-Judge Guide:** Detailed rubric construction, scoring anchors, evaluation approaches (direct scoring, G-Eval chain-of-thought, reference-based, classifier-based, RAG faithfulness). — [promptfoo.dev](https://www.promptfoo.dev/docs/guides/llm-as-a-judge)
- **AgentGym (ACL 2025):** Unified evaluation framework across 7 real-world scenarios and 14 environments for LLM-based agents. Addresses the problem that static benchmarks go stale and don't capture multi-turn decision-making quality. — [ACL Anthology](https://aclanthology.org/2025.acl-long.1355/)

## Gotchas

- **Judges drift on novel inputs.** A judge calibrated on routine tasks will confidently misjudge edge cases outside its training distribution. Treat calibration as ongoing, not one-time.
- **The judge also hallucinates.** LLM-as-judge does not eliminate hallucination — it relocates it. Budget for cases where the judge confidently gives wrong scores.
- **Reward hacking transfers.** If the agent and judge share architecture or training data, the agent can learn to produce outputs that score well without solving the real problem. Isolation between agent and judge is structural, not aspirational.
- **Binary pass/fail loses signal.** A judge that only says "pass" or "fail" gives you no diagnostic signal. Use multi-dimensional scoring so you know whether the agent failed on correctness, safety, or coherence.
- **Eval sets go stale.** An eval set built against agent v1.0 will penalize agent v2.0 for legitimate improvements. Re-label periodically, or use dynamic evaluation that generates test cases alongside agent evolution.
