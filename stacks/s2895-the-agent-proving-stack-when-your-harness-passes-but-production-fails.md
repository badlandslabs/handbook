# S-2895 · The Agent Proving Stack — When Your Harness Passes But Production Fails

You spent three weeks building an eval harness. It has 3,000 test cases, a CI gate, and a coverage report. Your agent passes at 97%. You ship it. On day two, it confidently tells 200 users the wrong refund amount because your harness tested what the agent said, not whether the refund actually processed. Your tests were comprehensive. Your measurement was wrong. This is the eval gap: most teams measure whether agents sound right, not whether they work right.

## Forces

- **Agent quality compounds non-linearly.** A single agent at 95% accuracy per step drops to ~60% by step ten in a chained workflow — yet most teams measure the final output only, ignoring step-level drift.
- **Harness diversity is not the same as production diversity.** Synthetic test cases match what engineers can imagine. Real users surface what engineers never considered. The gap between these is where agents break.
- **LLM-as-judge is load-bearing infrastructure now.** Over 57% of surveyed production teams run judge LLMs at runtime — but the judge can be wrong, expensive, and gameable. Knowing when to trust it is non-obvious.
- **The vibe check is a false negative factory.** Manually chatting with the agent tells you nothing about what it will do at 2 AM under load with a flaky API dependency.
- **Eval criteria drift from business outcomes.** Teams optimize for token efficiency and API call reduction — metrics that don't map to "did the customer's problem get solved."

## The move

The move is a **three-layer eval architecture** that treats evaluation as a production system, not a pre-launch checkpoint. Each layer answers a different question and catches failures the others miss.

### Layer 1 — Offline unit evaluation (pre-deploy gate)

Run structured tests against the agent's **outputs and intermediate steps** before any code reaches users:
- Use **DeepEval** (or equivalent) for CI/CD integration — it runs pytest-style assertions against agent responses and is designed for developer loops
- Test **task completion rate** (did the agent reach the goal?), **tool call accuracy** (right tool, right parameters?), **reasoning coherence** (did the thought chain make sense?), and **cost per task**
- Build a **golden dataset from actual production failures**, not idealized scenarios — every outage becomes a regression test
- Keep Layer 1 fast (seconds per run) so engineers use it on every PR

### Layer 2 — Online trace evaluation (runtime)

Capture the full execution trace (every LLM call, tool invocation, state change) and evaluate the trace itself, not just the final output:
- Use **LangChain's trace layer**, **AgentOps**, or **Datadog LLM Observability** (for Bedrock agents) to capture traces in production with <5% overhead
- Run **LLM-as-judge** as a production gate for high-stakes actions — the judge evaluates whether the agent's reasoning at each step is sound, not just whether the final answer is right
- Track **step-level error rates** alongside end-to-end task success — if step 4 of a 7-step workflow fails 12% of the time, a 97% overall score hides it
- Log traces to a searchable store (e.g., Postgres + pgvector, or ClickHouse) so you can replay any failed run

### Layer 3 — Outcome monitoring (production telemetry)

Measure whether the agent's work actually accomplished the business goal, not whether it seemed convincing:
- Instrument the **external systems the agent acts on** (database writes, API calls, email sends) and verify the post-action state matches expectations
- Track **task completion with ground-truth verification** — e.g., for a support agent, does the ticket status actually reflect the resolution the agent reported?
- Set **SLOs on outcome metrics**: task success rate, hallucination rate (measured by comparing claims against source documents), error budget per agent
- Run **canary comparisons** when deploying new prompt versions — split traffic and compare outcome rates before full rollout

### Judging the judge

LLM-as-judge is powerful but has failure modes — it over-trusts reasoning chains that sound confident, and it under-trusts correct answers that sound unconventional. Calibrate with:
- **Calibrated LLM-as-judge**: use the same model family as the agent (e.g., Claude judge for a Claude agent) to reduce calibration drift
- **Small distilled judges** (Luna-2 3B–8B, Lynx 8B) for high-volume, low-stakes gates — they deliver 97% cost reduction at 0.88–0.95 accuracy vs. GPT-4-based evaluation on formal domains (code, math, factual QA)
- **Self-correction loops are unreliable** without external grounding — Reflexion-style self-correction degrades on complex reasoning tasks; only use it where the judge can reference a ground-truth source

## Evidence

- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" (Jan 2026) defines the core eval vocabulary — task, trial, grader, transcript — and emphasizes that agents operating over many turns require tracing intermediate steps, not just final outputs. — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Industry survey:** The LangChain State of Agent Engineering (1,340 teams) found 89% of teams have observability tooling but only 52% run outcome evaluations — the eval gap is structural, not tooling. — [Paperclipped practitioner report](https://www.paperclipped.de/en/blog/ai-agent-production-issues)
- **Research:** Zylos Research (Apr 2026) surveyed 57%+ of production agent teams now running judge LLMs at runtime; documents the six LLM-as-judge patterns (offline eval, runtime verifier, self-consistency, Reflexion, constitutional AI/RLAIF, inference-time reward models) with their latency, cost, and failure mode profiles. — [Zylos Research](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)
- **Practitioner guide:** Google Cloud's "From Vibe Checks to Continuous Evaluation" (Feb 2026) shows how to wire Bedrock Agent Development Kit traces to Vertex AI + Datadog for Layer 2 and Layer 3 monitoring, including real SLO setup. — [Google Cloud Blog](https://cloud.google.com/blog/topics/developers-practitioners/from-vibe-checks-to-continuous-evaluation-engineering-reliable-ai-agents)

## Gotchas

- **A passing harness is necessary but not sufficient.** If your eval only checks final output, it cannot catch step-level drift, tool-call parameter errors, or hallucination in intermediate reasoning. Add trace-level assertions.
- **Layer 1 and Layer 2 regressions become Layer 3 cases in production.** Every production failure should be added to the golden dataset. If it happened once, it will happen again — automate the promotion of failures to test cases.
- **Judges need grounding.** An LLM judge evaluating itself is a conflict of interest. Ground judgments against external sources (document retrieval, database state, API responses) wherever possible.
- **Outcome metrics lag feedback.** Task success rate measured at 2 AM won't reach your dashboard until morning. Run synthetic smoke tests on a schedule against production-integrated agents so you catch regressions before users do.
- **Eval dataset staleness is a silent killer.** An agent trained or prompted on January data will ace an eval built on January scenarios. Re-seed golden datasets from current production traffic at least monthly.
