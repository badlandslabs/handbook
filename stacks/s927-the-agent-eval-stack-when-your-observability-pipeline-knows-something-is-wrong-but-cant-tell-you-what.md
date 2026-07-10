# S-927 · The Agent Eval Stack — When Your Observability Pipeline Knows Something Is Wrong But Can't Tell You What

You've instrumented everything. Traces flow, latency is logged, token counts are tracked, error rates are on dashboards. Then a model upgrade ships and users start complaining. You can see that metrics changed but you can't prove whether quality improved or degraded — because you were never measuring whether the agent was *correct*, only whether it was *running*. The 37-point gap between observability and evaluation is where agent quality goes to die.

## Forces

- 89% of AI teams have observability tooling but only 52% have evaluation frameworks — a gap that makes model upgrades a coin flip rather than a data-driven decision.
- Agents are probabilistic, multi-step, and stateful — they fail in ways that single-turn prompt-response scoring completely misses: wrong tools called, malformed arguments, retrieval dead-ends, loops, and silent off-task drift.
- Traditional software testing assumes deterministic outputs against fixed assertions — agents produce probabilistic outputs with reasoning chains, tool-call sequences, and emergent behaviors that only surface under production workloads.
- Evaluation assets (datasets, graders, rubrics) are treated as one-off experiments rather than shared infrastructure, so effort doesn't compound across the organization.
- Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring, not model capability gaps.

## The Move

Build a three-layer eval stack and run it on every meaningful change — not just at launch.

**Layer 1 — Outcome evals:** Does the final answer solve the task? Use code-based graders for verifiable assertions (exact string match, regex, JSON schema validation) and model-based graders for subjective quality (tone, coherence, relevance). Code graders are fast, cheap, and objective but brittle. Model graders are flexible and handle nuance but non-deterministic. Anthropic recommends combining both — code for the measurable, models for the subjective. Grade the final output, not the process.

**Layer 2 — Trajectory evals:** Grade the full execution trace — every reasoning step, tool call, tool result, and handoff in sequence. This is the critical layer most teams skip. The interesting failures hide inside the sequence: a wrong tool was called, an argument was malformed, a retrieval returned nothing, the agent looped. OpenAI's eval tooling (Responses API, AgentKit, Agents SDK) exposes trace data specifically for this — each trace is a structured record with `input`, `steps` (ordered reasoning + tool calls), and `output`. Graders assert on the process, not just the product. A task passes only if the right tools were called in the right order with the right arguments. This is what makes regression visible.

**Layer 3 — Capability benchmarks (pre-deployment gate):** Run the full eval suite before every production deploy. Record scores at all three layers. Compare against baseline. An outcome accuracy drop of more than 2 percentage points fails the upgrade. A trajectory efficiency degradation (agents taking 30%+ more steps for the same tasks) also fails it. Pin the new model version, run the same suite, diff layer by layer.

**Dataset strategy:** Curate eval datasets from real production inputs, not synthetic easy cases. Representative distributions catch edge cases that curated benchmarks miss. Tag every dataset entry with difficulty level (GAIA provides a three-level schema; Level 3 tasks fail 39% of the best agents). Build a shared library of known failure patterns that engineers contribute to — this is the compounding asset.

**Grader selection guide:**
| Grader type | Best for | Limitation |
|---|---|---|
| Code-based | Verifiable outputs, JSON schema, exact match | Brittle, misses semantic correctness |
| Model-based | Subjective quality, prose, style | Non-deterministic, expensive |
| Human | Calibration, edge cases, new failure modes | Slow, expensive, inconsistent |

## Evidence

- **Anthropic Engineering blog (Jan 2026):** Complete guide to agent evals — documents the three grader types, trajectory grading, and the "evaluations make behavioral changes visible before they affect users" principle. Recommends combining code, model, and human graders based on what you're measuring. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **OpenAI Developer Documentation:** AgentKit evaluation workflow — datasets, trace grading, automated prompt optimization, and CI integration as a first-class concern. Explicitly distinguishes trace grading (debugging) from eval runs (systematic evaluation) and ties both to acceptance thresholds. — [developers.openai.com/api/docs/guides/agent-evals](https://developers.openai.com/api/docs/guides/agent-evals)
- **RaftLabs State of AI Testing (May 2026):** 52% of teams have evaluation frameworks vs 89% with observability — a 37-point gap. Top GAIA Level 3 score is 61%, meaning even the best agents fail 39% of difficult tasks. Reports that a model scoring 94% on an eval suite might score 88% on the same suite after a checkpoint update. — [raftlabs.com/blog/ai-agent-testing-evaluation-guide](https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide)
- **Show HN — Agent-triage (2026):** Open-source tool for diagnosing agent failures from production traces. Addresses the problem of having observability data but no systematic way to triage failures — the exact gap between trace collection and evaluation. — [github.com/converra/agent-triage](https://github.com/converra/agent-triage)
- **Show HN — AgentLens (2026):** Open-source observability platform with cryptographically verifiable, SHA-256 hash-chained audit trail. Built for EU AI Act Article 12 record-keeping. Tracks decision trees, context window utilization, and per-decision/per-agent cost. — [github.com/agentkitai/agentlens](https://github.com/agentkitai/agentlens)

## Gotchas

- **Observability is not evaluation.** You can have perfect traces and zero ability to answer "was this correct?" Traces tell you what happened; evals tell you whether it was right. Teams with observability but no eval frameworks can't prove quality changed after a model upgrade.
- **Grading only the final output misses 80% of agent failures.** Wrong tool calls, malformed arguments, failed retrievals, and off-task loops don't appear in the final answer. You need trajectory grading to surface these.
- **Eval datasets go stale.** Production input distributions shift. A dataset that reflected real queries six months ago may not reflect current ones. Treat dataset maintenance as a recurring engineering task, not a one-time setup.
- **Model-based graders are non-deterministic.** The same grader run twice can produce different scores. Run each eval with 3-5 trials and use the distribution, not a single score. This is why code-based graders are preferred for regression gates — they give consistent signals.
- **Human calibration drift.** Human graders are inconsistent over time and between reviewers. Use human annotations to calibrate model-based graders, then run model graders for volume. Re-calibrate periodically.
