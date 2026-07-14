# S-1099 · The Judgment Stack — When Your Agent Grades Its Own Homework

You run an LLM judge to evaluate your agent. The judge scores it 91%. You ship. In production, the agent hallucinates 30% of its tool calls — but every one of those hallucinations still produces a plausible-looking trajectory that the judge scores as correct. The judge wasn't wrong: it evaluated trajectories the same way the agent produced them — by pattern-matching on surface coherence. Both models share the same blind spots. You built an echo chamber and called it quality assurance.

This is the LLM-as-judge calibration problem: using an LLM to evaluate an LLM creates systematic blind spots that inflate scores and hide failures until production exposes them.

## Forces

- **Correct outputs hide broken reasoning.** An agent can refund a customer, file the ticket, and send the confirmation — all correctly — while using a tool it invented rather than one that exists. The outcome is right. The trajectory is wrong. A judge that checks outcomes only never sees this.
- **LLM judges share the agent's blind spots.** Both models are trained on similar data, see the world through similar priors, and make the same categories of mistake. A judge that would flag the agent's error has to catch itself — and often doesn't.
- **Trajectory traces are unreadable at scale.** A single agent run can produce hundreds of steps across nested tool calls, reasoning chains, and state mutations. Transforming that nested JSON into human-readable traces for review is expensive and slow. Teams default to automation because human review doesn't scale.
- **Non-determinism makes binary pass/fail useless.** Agents don't produce the same output twice. A CI gate that expects exact matches fails on legitimate variation while passing on subtly broken runs. You need soft thresholds, but soft thresholds are easy to game.
- **Production data is the ground truth that benchmarks never have.** The queries that break your agent in production are not in your evaluation set — they haven't happened yet. The evaluation framework is always one production incident behind.

## The move

**Separate trajectory evaluation from outcome evaluation from the start.** These answer different questions and require different methods. Outcome metrics tell you if the agent works. Trajectory metrics tell you why it failed.

**Calibrate LLM judges against human-labeled ground truth, not against each other.** Run 50–100 agent runs through human reviewers first. Use those labeled examples to measure your judge's accuracy before deploying it at scale. Without calibration, you don't know if your judge is better than random.

**Check for tool call hallucination as a distinct signal.** Log every tool the agent invokes and verify — asynchronously, not in the critical path — whether that tool exists in your registry. A 5% hallucination rate on tool names is common and invisible unless you measure it. It doesn't show up in outcome metrics.

**Implement soft CI thresholds with trajectory-level gates.** Rather than binary pass/fail, gate on: tool call hallucination rate < 2%, step completion rate > 85%, and cost per task within 1.5x budget. A run that hits all three gates advances. A run that fails one gets human review. This catches broken trajectories before they pass on a technicality.

**Feed production traces back into the evaluation set.** After each incident, add the production query and the correct resolution to the reference dataset. This is the virtuous loop — the evaluation suite learns from the world, not just from the team's assumptions about it.

## Evidence

- **Label Studio (Mar 2026):** "Automated LLM judges share the blind spots of the agents they evaluate. Correct final outputs often mask broken reasoning and hallucinated tool calls." Found that without human calibration, LLM judges achieve Spearman correlation of ~0.3 with human judgment — barely above chance. — [How to evaluate AI agents in production — Label Studio](https://labelstud.io/blog/how-to-evaluate-ai-agents-in-production/)
- **Google Cloud Blog (Nov 2025):** "An agent can produce a correct output through an inefficient or incorrect process — what we call a 'silent failure'. An agent tasked with reporting inventory gives the correct number but references last year's report." Documented a three-layer evaluation framework: outcome metrics, trajectory metrics, and operational metrics, with CI gates that fail on any layer. — [A methodical approach to agent evaluation — Google Cloud](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Amazon ML Blog (Feb 2026):** "In multi-agent systems evaluation, HITL becomes critical because of the increased complexity and potential for unexpected emergent behaviors that automated metrics might fail to capture." Described three categories that automated metrics consistently miss: inter-agent communication failures, conflict resolution on contradictory recommendations, and logical consistency when multiple agents contribute to a single decision. — [Evaluating AI agents: Real-world lessons from Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Galileo AI (Jul 2026):** "Agents can achieve 60% success on single runs, but only 25% across eight runs." Found that standard outcome-only benchmarks miss reliability challenges that appear under repeated execution. — [Agent Evaluation Framework — Galileo](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **An agent that passes your benchmark can fail every time in production.** Benchmarks measure the distribution of queries you anticipated. Production serves the queries you didn't. The benchmark score is a floor, not a ceiling — and often not even that.
- **Soft CI thresholds are easy to game.** If you relax thresholds to reduce false positives, you reduce the signal. The right threshold is calibrated against human judgment, not tuned for convenience.
- **Checking the judge is not optional.** Run your LLM judge against a human-labeled subset every sprint. If the judge's accuracy drops, recalibrate before scaling it further. An uncalibrated judge is worse than no judge — it produces false confidence.
