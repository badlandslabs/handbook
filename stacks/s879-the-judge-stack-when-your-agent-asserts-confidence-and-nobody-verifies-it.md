# S-879 · The Judge Stack — When Your Agent Asserts Confidence and Nobody Verifies It

You ship an agent into production. It calls tools, plans, executes. It returns a result. You have no idea whether the result is correct, whether the plan it followed was sound, or whether a tool call somewhere in the chain hallucinated an argument. You've hit the judge gap: your agent makes claims; nobody checks them. LLM-as-judge closes this gap — but using it wrong is worse than not using it at all.

## Forces

- **Agents are non-deterministic truth-claimers.** A single agent run produces a trajectory of decisions — tool calls, plan changes, output synthesis. The final output tells you nothing about whether intermediate steps were sound. Final-output scoring misses the failure mode location.
- **Intrinsic self-correction is unreliable.** UC Berkeley's Zylos research found that self-correction only works when the failure is recoverable *within the same capability level* — roughly 15-23% of cases. For everything else, the agent doubles down on its mistake.
- **Human review doesn't scale.** At 100+ agent runs per day, reviewing every trajectory manually becomes the bottleneck. The economics of autonomous agents break if human review is required per task.
- **External benchmarks don't predict production.** All eight prominent agent benchmarks studied (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) were found to be exploitable by UC Berkeley researchers. Lab-to-production performance gap: **37%**.
- **Proprietary judges are expensive at runtime.** Running GPT-4o as an inline verifier at every step multiplies cost by 4-10x. But cheap is useless if it's wrong 30% of the time.

## The Move

Treat LLM-as-judge as load-bearing infrastructure, not a dashboard metric. Use the right judge architecture for the right decision point in the trajectory.

**1. Separate offline eval from runtime verification.** Offline evaluation runs comprehensive checks on logged trajectories — slow, thorough, used to tune prompts and catch regressions in CI. Runtime verification runs lightweight checks inline — fast, narrow, used to gate tool calls or block bad outputs. Mixing them creates a system that's both expensive and unreliable.

**2. Use tiered judges.** High-stakes decisions (financial, legal, safety) get a large proprietary judge (GPT-4o, Claude 3.7 Sonnet) at runtime. Low-stakes decisions get a small distilled judge (Luna-2 3B-8B, Prometheus 2 7B, Patronus Lynx 8B). Studies show small distilled judges achieve **97% cost reduction** at **0.88–0.95 accuracy** versus GPT-4-based evaluation — sufficient for volume checks, insufficient for boundary cases.

**3. Gate at the critical path, not the terminal output.** Verifying the final output is too late — if step 4 is wrong, step 10's output is structurally compromised. Insert judge checks after high-uncertainty actions: tool-call arguments before execution, plan confirmation before long-horizon steps, and output synthesis before delivery.

**4. Combine trajectory scoring with golden-answer scoring.** Golden answers catch regressions on known cases. Trajectory scoring (did the agent follow the right steps in the right order?) catches the failure modes that look fine in the output: step repetition (17% of multi-step failures), reasoning-action mismatch, and hallucinated tool arguments.

**5. Use self-consistency loops for ambiguous outputs.** Run the agent's reasoning 3-5 times with temperature variation and check for consensus. For high-stakes outputs where a judge model might have the same blind spots as the agent, cross-validation across runs is the only defensible approach.

**6. Instrument the judge itself.** Track judge accuracy against human-labeled samples over time. Judge drift (a judge model that was 94% accurate six months ago now at 78%) is invisible without a calibration loop. Run human-in-the-loop audits on a random 2-5% sample of judged trajectories.

## Evidence

- **Research paper:** "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems" (arxiv:2511.14136) — Evaluated six enterprise agents on 300 tasks. CLEAR framework (Cost, Latency, Efficacy, Assurance, Reliability) predicted production success at ρ=0.83 vs accuracy-only evaluation at ρ=0.41. Lab-to-production gap: 37%. — [https://arxiv.org/html/2511.14136v1](https://arxiv.org/html/2511.14136v1)

- **Research brief:** Zylos Research "LLM-as-Judge in Production" (2026) — 57% of surveyed production agent teams use judge LLMs at runtime. Six patterns identified: offline eval, online runtime verifier, self-consistency loops, Reflexion, constitutional AI/RLAIF, inference-time reward models. Small distilled judges: 97% cost reduction at 0.88-0.95 accuracy. Intrinsic self-correction unreliable outside 15-23% of recoverable cases. — [https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)

- **Research brief:** Zylos Research "AI Agent Evaluation and Benchmarking" (2026) — All eight prominent agent benchmarks exploitable. UC Berkeley findings. CLEAR framework developed to address benchmark crisis. — [https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)

## Gotchas

- **Judge positional bias is real.** LLMs as judges consistently favor longer responses and responses from larger models. If you're comparing outputs from different model sizes, inject length normalization and blind the judge to model identity.
- **A judge that agrees with the agent isn't confirmation — it's noise.** If your judge agrees with the agent 95% of the time, it's not catching failures, it's rubber-stamping. Target judge agreement in the 60-85% range on known failure cases to confirm the judge is actually discriminating.
- **Checking the final output is too late to recover.** A judge that only scores the terminal output can identify failure but can't prevent it. Move verification upstream to decision points, not deliverables.
- **Distilled judges fail on edge cases that matter most.** A 3B-parameter judge trained on majority-correct outputs will confidently agree with the agent on novel edge cases — exactly the scenarios where you need verification most. Keep a human escalation path for judge-flagged unknowns.
