# S-1574 · The Eval Gap Stack — Why Your Agent Passes Every Test and Still Fails in Production

You run every benchmark. The accuracy numbers look fine. You ship. Three weeks in, customers report the agent getting stuck in loops, misusing tools, and producing subtly wrong answers that look right. The problem isn't the model — it's that you're evaluating the wrong thing at the wrong granularity. Grading only the final message misses the most important question: did the agent actually do the task correctly, through the right steps?

This is the eval gap: the belief-execution chasm between knowing agents need evaluation and actually measuring what matters.

## Forces

- **Agents are systems, not models** — they plan, call tools, modify state, and adapt across many turns. Single-turn metrics (BLEU, ROUGE, exact-match accuracy) don't capture how agents fail in practice. You need to evaluate trajectories, not endpoints.
- **Multiple valid outputs break ground truth** — traditional ML evaluation relies on ground truth labels. LLMs can produce three equally correct answers that differ from the reference. Surface-similarity metrics fail to capture semantic correctness.
- **Agents are probabilistic** — the same input can produce different outputs across trials. One run is not enough. You need multiple trials and statistical confidence.
- **Evals are undervalued until they aren't** — 72% of teams believe comprehensive testing drives AI reliability, yet only 15% achieve elite eval coverage (90–100% of behaviors tested). The gap between belief and execution is where production failures live.
- **The measurement instrument drifts** — LLM-as-judge systems calibrate against human labels, but those labels themselves shift as model behavior evolves. Recalibration is not a one-time setup task.

## The move

Evaluate trajectories, not answers. Grade the reasoning and action layers separately. Build a layered eval stack that runs offline, in CI, and in production.

**Build two eval types from day one:**
- **Capability evals** — target the behaviors your agent currently struggles with. Start with a low pass rate; improve until you're satisfied, then graduate to regression.
- **Regression evals** — protect known-good behaviors. Aim for ~100% pass rate. Any regression is a signal to investigate before shipping.

**Grade at the right granularity:**
- Use **deterministic assertions** for verifiable outputs (file written, API called, test passed).
- Use **LLM-as-judge** for subjective quality (answer helpfulness, tone, explanation clarity).
- Use **trace-level analysis** (not just final-message grading) to catch mid-workflow failures: wrong tool selected, state corrupted, loop entered.
- Evaluate the **reasoning layer** (is the plan sound?) and **action layer** (were the right tools called correctly?) separately, then together.

**Version and maintain your golden datasets:**
- Golden datasets decay as agent behavior and real-world data distributions shift. Treat them like code — review, update, and version them on a regular schedule.
- Use synthetic data generation to augment small datasets, but validate synthetic examples against human-labeled ground truth.

**Calibrate LLM judges against human annotations:**
- Run Spearman correlation between your LLM judge's scores and human-labeled examples.
- Recalibrate judges monthly — the measurement instrument drifts alongside model behavior.
- For high-stakes domains (healthcare, finance, legal), human judgment is not optional; it anchors the automated system.

**Instrument production:**
- Log every trace: tool calls, reasoning steps, intermediate results, final outputs.
- Monitor human intervention rate — a gradual increase is the leading indicator of silent degradation.
- Run offline evals in CI on every PR. Run online evals on a sampled production traffic slice.

**Evaluate by agent type:**
- **Coding agents** — grade on deterministic test outcomes, code quality, tool call correctness, and state verification. Well-specified tasks in stable environments are the easiest to eval.
- **Conversational agents** — simulate user personas with a second LLM. Grade both task completion and interaction quality (tone, trust, appropriateness). The quality of the *interaction itself* is part of what you're measuring.
- **Research agents** — grade on information accuracy, source credibility, citation correctness, and synthesis quality. Hallucination detection is a first-class metric.

## Evidence

- **Engineering blog (Anthropic, Jan 2026):** "The capabilities that make agents useful — autonomy, intelligence, and flexibility — also make them harder to evaluate." Grading only the final message misses whether the task was completed correctly through the right steps. Agents that call the wrong tool but produce a plausible-looking final output will pass final-message grading while failing in practice. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Industry survey (Galileo, 2026):** Of 500+ enterprise AI practitioners, 72% strongly believe comprehensive testing drives AI reliability, yet only 15% achieve elite eval coverage (90–100% of behaviors tested). The top-performing teams use multi-layered evaluation: offline datasets + CI regression gates + production monitoring. — [https://galileo.ai/blog/ai-agent-metrics](https://galileo.ai/blog/ai-agent-metrics)

- **Academic survey (KDD '25):** LLM agent evaluation differs fundamentally from traditional software testing — agents are probabilistic and behave dynamically. Effective evaluation requires multi-dimensional taxonomies covering evaluation objectives (behavior, capabilities, reliability, safety) and evaluation processes (interaction modes, data sources). Offline eval is cheaper but prone to error propagation; online eval with simulated users captures failure modes static testing misses. — [https://arxiv.org/html/2507.21504v1](https://arxiv.org/html/2507.21504v1) — Mohammadi, Li, Lo, Yip (SAP Labs)

- **Open-source framework (DeepEval, GitHub):** Implements agent eval with separate reasoning-layer metrics (plan quality, coherence) and action-layer metrics (ToolCorrectnessMetric, whether the right tools were called in the right order). Designed for pytest-style unit testing of agent traces — runnable in CI. — [https://github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)

- **Practitioner guide (InfoQ, Mar 2026):** "Agents are systems, not models — evaluate them accordingly." BLEU/ROUGE don't capture agentic failure. The five evaluation pillars are: Intelligence & Accuracy, Performance & Efficiency, Reliability, Responsibility (safety), and User Experience. Operational constraints (latency, cost per task, token efficiency) are first-class evaluation targets for enterprise viability. — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

## Gotchas

- **Evaluating only the final answer** — the most common mistake. An agent can reach the right answer through the wrong reasoning or wrong tools, or reach a wrong answer that looks right. Trace-level grading catches what final-message grading misses.
- **One eval run is not enough** — probabilistic outputs require multiple trials per task. A single pass gives you noise, not signal.
- **Golden dataset decay** — datasets built today become stale as real-world data distributions shift and agent behavior evolves. Treat golden datasets as living artifacts that need regular review and updates.
- **LLM-as-judge without calibration** — an uncalibrated judge is as unreliable as an uncalibrated instrument. Without correlation testing against human annotations, you have no idea if your judge is measuring the right thing.
- **Eval coverage inflation** — running evals on 30% of behaviors and claiming "we have evals" creates false confidence. Elite teams target 90–100% of behaviors tested, not just the easy ones.
- **Treating evals as a one-time setup** — evals are a continuous discipline. Model updates, prompt changes, tool modifications, and upstream API changes all require eval re-runs. If evals aren't in CI, they will be forgotten.
