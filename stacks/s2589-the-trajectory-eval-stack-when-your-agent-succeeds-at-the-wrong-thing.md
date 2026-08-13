# S-2589 · The Trajectory Eval Stack — When Your Agent Succeeds at the Wrong Thing

Your agent completes the task. The final output looks right. The user is satisfied. Then you check the trace and find it reached the answer by calling the wrong tool, ignoring three intermediate steps, and fabricating the reasoning that justified the detour. Outcome-only evaluation would have called this a pass. A trajectory eval caught it mid-loop. The gap between what agents produce and what they do to produce it is where eval strategy makes or breaks production reliability.

## Forces

- **Error compounding across steps** — a wrong tool call at step 2 corrupts steps 3–12, so the final answer can look correct while the path is deeply broken
- **Non-deterministic outputs** — the same agent given the same input can take different trajectories on different runs, making pass/fail assertions alone insufficient
- **Grader alignment drift** — LLM-as-judge graders develop their own biases (leniency, position preference, verbosity bias), and without calibration they can mask real regressions
- **Harness vs. model dominance** — the behavior of an agentic system is dominated more by its tool definitions, loop logic, and context than by the underlying model, but most teams only eval the model
- **Regression surface area** — a prompt update that fixes one workflow silently breaks another, and without a regression suite you won't know until users complain

## The move

Build a **three-layer eval harness** that scores outcomes, trajectories, and system metrics independently — then gate releases on all three.

**Layer 1 — Outcome eval (did it solve the task?):**
- Define tasks as concrete inputs + success criteria, not rubrics
- Use deterministic graders for verifiable facts (exact match, schema validation, SQL query correctness)
- Supplement with LLM-as-judge for subjective quality, but calibrate it against a human-labeled holdout set first
- Re-run the full suite as a regression gate on every change before shipping

**Layer 2 — Trajectory eval (did it take the right path?):**
- Instrument tool call traces at span granularity: which tool, which arguments, which results, in what order
- Score each step: correct tool selection, correct argument construction, correct sequencing, no unnecessary loops
- Use the aggregated trace graph view to spot pathological shapes — repeated steps, cycle edges, unexpected branches — at a glance
- Flag trajectories where the correct answer was reached through a wrong sequence (the most dangerous failure mode)

**Layer 3 — System eval (was it efficient and reliable?):**
- Track token cost per task, latency, tool call count, and step budget consumption
- Set thresholds: within_step_budget, cost_per_task, recovery_rate_from_errors
- Alert on regressions in these metrics even when outcome scores hold — an agent that works but burns $50/query won't ship

**The eval loop:**
- Run evals on every commit (CI gate)
- Sample production traces for online eval (catches distribution shift)
- Use a small labeled holdout set to calibrate graders
- Distinguish when the agent failed vs. when the grader was wrong — examine both

## Evidence

- **Engineering blog (Anthropic, Jan 2026):** Claude Code started with fast iteration from user feedback, then added evals — first for narrow behaviors (concision, file edits), then for complex ones (over-engineering). Found that evals make behavioral changes visible before they reach users, and that their value compounds over the agent lifecycle. Absent evals, debugging is reactive — teams wait for complaints, reproduce manually, and can't distinguish regressions from noise. — [Anthropic Engineering: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Research survey (KDD 2025, SAP Labs):** Systematic survey of LLM agent evaluation at scale — argues that "LLM evaluation is like examining the performance of an engine. Agent evaluation assesses a car's performance comprehensively, as well as understanding the driver's decisions at each turn." Identifies enterprise-specific challenges: role-based access control, reliability guarantees, dynamic/long-horizon interactions, and compliance requirements. Two-dimensional taxonomy: evaluation objectives (behavior, capabilities, reliability, safety) × evaluation process (interaction modes, datasets, metrics, tooling). — [arXiv:2507.21504 — Evaluation and Benchmarking of LLM Agents: A Survey](https://arxiv.org/html/2507.21504v1)

- **Engineering post (Langfuse, Jul 2026):** Trajectory score like `within_step_budget` on every sampled production trace turns "the agent has gotten slower and more expensive" from anecdote into a dashboard line. Aggregated trace graph mode collapses repeated steps and cycle edges to reveal the agent's shape and loops at a glance. Expanded mode unrolls every call for pinpointing exactly where one run went wrong. Online eval on production traces catches distribution shift that offline suites miss. — [Langfuse: AI Agent Evaluation — Trajectory, Tool Calls, and Task Completion](https://langfuse.com/resources/engineering/ai-agent-evaluation)

## Gotchas

- **Outcome eval alone is a false floor.** The correct answer reached through the wrong trajectory is a production incident waiting to happen — it will fail on the next input that requires the skipped reasoning steps.
- **LLM-as-judge graders drift.** Without a calibrated holdout set (human-labeled ground truth), a grader can develop leniency bias over time, causing it to pass regressions. Re-calibrate before major releases.
- **Synthesized golden datasets miss distribution shift.** Evals written by engineers tend to cover the known edge cases. Real production failures come from inputs nobody anticipated. Supplement static suites with sampled production traces evaluated online.
