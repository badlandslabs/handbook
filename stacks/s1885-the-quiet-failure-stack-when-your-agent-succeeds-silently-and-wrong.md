# S-1885 · The Quiet Failure Stack

When your agent completes a task with plausible output, no error messages, and a confident tone — but the action was wrong. You only find out three weeks later when a customer complains about silently corrupted data. Traditional software fails loudly. Agents fail politely.

## Forces

- **Agents fail without signals.** Unlike code that crashes with exceptions, an agent can produce coherent, confident, entirely wrong output. No stack trace. No 500 error. Just bad outcomes that accumulate silently.
- **Standard LLM benchmarks measure the wrong thing.** Benchmarks like SWE-bench score single prompt-response pairs. Agent evaluation requires measuring trajectories: tool calls, intermediate states, and cumulative outcomes across multi-step workflows. A model that scores 80%+ on SWE-bench Verified may merge at half the rate of human pull requests in production.
- **Task completion != quality.** Tracking latency, token counts, and tool call counts tells you how efficiently the agent runs, not whether it actually accomplished what the user needed. Teams that only measure the former ship with false confidence.
- **Evaluation pipelines lag behind deployment.** 78% of enterprises run AI agent pilots. Fewer than 15% reach production scale. The primary blocker is not model capability — it is evaluation infrastructure that hasn't kept pace.

## The move

Build an evaluation system that tests trajectories, not turns. Treat production failures as permanent additions to the test suite. Use three interlocking layers:

- **Golden traces from real failures.** Every production failure becomes a test case. A user query that exposed a failure mode becomes a regression test the agent must pass before the next deploy. This is the highest-signal feedback channel — it represents failures that already cost something.
- **Three-layer eval framework.** (1) **Node-level precision** — did the agent select the right tool with the right parameters at each step? (2) **Session-level outcomes** — did the agent complete the overall task correctly? (3) **System efficiency** — latency, token cost, and tool call efficiency. Track all three. Latency alone creates false confidence.
- **LLM-as-judge with calibration gate.** LLM-as-judge scales scoring but requires calibration: validate against human-annotated labels until agreement exceeds 85%. Without this, you are measuring the judge's biases, not the agent's quality.
- **The eval flywheel.** Offline eval → deploy → online monitoring → failure analysis → expand golden dataset → agent optimization → repeat. Every production failure permanently converted into a regression test. The core principle: the same error should never happen twice.
- **CI gate on every change.** On model upgrades or agent code changes, run the full golden dataset. Any degradation beyond threshold blocks the release. Golden datasets must be versioned alongside agent code so changes and their validations live in the same commit.
- **Online sampling with alerts.** Even perfect offline eval cannot anticipate every query. Sample live traffic, score asynchronously, alert when scores fall below thresholds. Flag patterns by failure category (factual error, wrong tool, partial failure) to identify systematic weaknesses.

## Evidence

- **Engineering post (Datadog, 2025):** Built an evaluation platform for their autonomous SRE agent ("Bits Investigation") by turning production incidents into reproducible investigation environments. Key insight: a feature that improved one investigation type quietly degraded others — no crashes, no test failures, just a quality shift that required trace-level comparison to detect. — [Datadog Engineering Blog](https://www.datadoghq.com/blog/engineering/bits-ai-eval-platform/)
- **Engineering post (Anthropic, Jan 2026):** "Good evaluations help teams ship AI agents more confidently. Without them, it's easy to get stuck in reactive loops — catching issues only in production, where fixing one failure creates others." Defines the core vocabulary: task (test case with inputs and success criteria), trial (one attempt), grading function (determines pass/fail). — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Industry analysis (Maxim AI / Kunal Ganglani, Jul 2026):** "An agent that achieves 95% task success but costs 3x more than a simpler alternative isn't better — it's just more expensive." Three-layer framework: System Efficiency + Session-Level Outcomes + Node-Level Precision. Recommends starting with 50 golden traces from production traffic, growing through weekly review rituals. — [Maxim AI Blog](https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices/), [Kunal Ganglani](https://www.kunalganglani.com/blog/evaluate-ai-agents-production)
- **ADR from production (ThomasChangX/llm-reporting, Jul 2026):** Documents a real evaluation architecture with golden dataset management, CI gates on model upgrade/agent code change, and per-VP dataset subsets. Key principle: immutable versioned datasets where each new failure case produces a new version. — [GitHub ADR-0018](https://github.com/ThomasChangX/llm-reporting/blob/main/adr/0018-agent-evaluation-framework.md)

## Gotchas

- **Measuring speed instead of correctness.** Latency and token metrics are easy to collect and seductive to dashboard. They tell you nothing about whether the agent's output was right. Add task-completion scoring from day one.
- **Benchmark scores create false equivalency.** A model that scores 80% on SWE-bench Verified may not be the best agent for your specific workflow. Benchmarks run in controlled environments against isolated repositories. Real production has API drift, partial failures, and ambiguous inputs the benchmark never saw.
- **LLM-as-judge without calibration is measurement theater.** Deploying LLM-as-judge before validating against human labels introduces judge bias into your quality signal. Calibrate to 85%+ human agreement first.
- **One-shot eval is not enough.** A single offline evaluation pass before deployment does not capture the distribution of real queries. You need continuous sampling from production traffic feeding back into the test suite.
- **Ignoring failure cascade.** In multi-step agents, an error in step 3 corrupts steps 4, 5, and 6. Node-level precision (did this step succeed?) is necessary but insufficient — you also need session-level outcome scoring (did the overall trajectory reach the right end state?).
