# S-1123 · The Trajectory Evaluation Stack — When Your Benchmark Says 95% but Users Are Furious

Your agent scores 95% on your evaluation suite. Your users still file bug reports. The disconnect: your eval measures what the agent *says*, not what it *does*, and not *how* it got there. The agent completes the calendar invite API call successfully but puts it on the wrong day. Your benchmark logs it as a pass. Trajectory evaluation closes this gap.

## Forces

- **Output scores lie.** Agents can reach correct answers through flawed reasoning, or fail at the goal while reporting success. A benchmark that only checks final output is blind to both failure modes.
- **The benchmark crisis is real.** UC Berkeley researchers examined eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all of them could be gamed to near-perfect scores using distractor artifacts in test environments — without solving the actual task. Standard benchmarks are contaminated for production decision-making.
- **Trajectory evaluation costs 4–11x more than outcome-only.** LLM-as-judge pipelines that score every reasoning step consume dramatically more tokens. Production teams need a triage strategy, not uniform rigor.
- **Partial success is the silent killer.** The agent reports "meeting scheduled" (API returned 200 OK) but the user is still looking at an empty calendar. Your eval shows green. Your user is frustrated. The system lied to you gently.

## The Move

Evaluate the full reasoning path, not just the endpoint — but strategically, not uniformly.

- **Distinguish outcome from trajectory.** Outcome eval asks "did the agent achieve the goal?" Trajectory eval asks "did it get there the right way?" Both matter; most teams only measure the first.
- **Use three grader types in a tiered strategy.** Code-based graders for verifiable assertions (file exists, function returns X, API call logged). Model-based graders for subjective quality (is the explanation coherent? is the tone appropriate?). Human graders for calibration and edge cases. Apply each where it has highest leverage — don't use expensive graders on cheap problems.
- **Capture transcripts as first-class artifacts.** A transcript (also called trace or trajectory) is the complete record: every tool call, every reasoning step, every intermediate result. Store them. They are your debugging material, your regression suite, and your evidence when the agent does something surprising.
- **Define success at the environment level, not the output level.** Check the actual state of the world after the agent runs, not just what the agent said it would do. If the task was "schedule a meeting for Tuesday," verify the calendar event, not just the API response.
- **Evaluate trajectory quality with structured rubrics.** Break the reasoning path into steps: tool selection, argument construction, execution, recovery. Score each. The `agent_trajectory_evaluation` package (GitHub: `abhiai-git/agent_trajectory_evaluation`) provides `correctness`, `efficiency`, and `robustness` metrics over tool-use trajectories — designed to integrate with LangChain traces.
- **Run evals continuously, not just at release.** Agent behavior drifts with model updates, prompt changes, and tool schema modifications. A regression test suite that runs on every commit catches drift before users do. LangSmith, Honeycomb (with OpenTelemetry), and DeepEval all support CI-integrated eval pipelines.
- **Calibrate graders against human judgment periodically.** LLM-as-judge models themselves get updated, causing scores to shift even when the agent hasn't changed. Re-anchor against human-graded samples every few weeks.

## Evidence

- **Engineering blog: Anthropic's eval taxonomy (Jan 2026).** Defines the canonical vocabulary: task, trial, grader, transcript, outcome, harness, and scaffold — and recommends the three-grader tiered approach. Stresses that "evaluating agents requires evaluating the harness and the model together, not in isolation." — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Research paper: Berkeley benchmark contamination study (2025).** Eight leading agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) all contained exploitable distractors allowing near-perfect scores without genuine task completion. Finding prompted the field's pivot toward trajectory-based and live-environment evaluation. — [Zylos Research citing UC Berkeley](https://zylos.ai/research/2026-05-13-ai-agent-evaluation-benchmarking/)
- **GitHub: DeepEval 4.0.** Open-source LLM evaluation framework with native integrations for OpenAI Agents, LangChain, LangGraph, and CrewAI. Ships coding-agent-specific eval harnesses, trace inspection TUI, and GitHub Actions CI integration. Claims "eval-engineering is as important as prompt engineering." — [Confident AI / GitHub](https://github.com/confident-ai/deepeval)
- **HN discussion: debugging multi-agent workflows.** Practitioners report that OpenTelemetry tracing (LGTM stack) is the dominant approach for visualizing execution paths across agent steps. Authority-boundary checking (whether agent transitions are allowed) requires explicit contracts (schemas, validators) rather than implicit discovery. — [Hacker News](https://news.ycombinator.com/item?id=47358618)

## Gotchas

- **Beware the "infinite repair loop."** A trajectory eval that flags every suboptimal reasoning step can push agents into cycles of self-correction that cost 10x more than the original run. Define a repair budget (max retries per step) and fail fast when exceeded.
- **Distinguishing distractor noise from real signal in benchmarks.** If your eval suite was built by scraping public benchmarks, it likely inherits the same contamination Berkeley identified. Audit your test cases against real production scenarios, not just the benchmark's stated task.
- **Token cost of comprehensive evaluation.** Prioritizing accuracy alone yields agents 4.4x to 10.8x more expensive to run than cost-aware alternatives (Label Studio research, citing arxiv 2511.14136). Build cost into your eval criteria from the start — a "perfect" agent that costs $2 per task isn't production-ready if a "good enough" one costs $0.02.
- **The partial-success detection gap.** If your eval only checks the agent's final output message, you won't catch cases where the agent reports success but the underlying operation failed silently. Instrument at the environment level — verify side effects, not just self-reports.
