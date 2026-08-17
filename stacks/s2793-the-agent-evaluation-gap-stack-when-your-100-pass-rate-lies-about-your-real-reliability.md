# S-2793 · The Agent Evaluation Gap Stack — When Your 100% Pass Rate Lies About Your Real Reliability

You ran your agent through 100 test cases and got 98% pass. You shipped to production and watched it fail 30% of real requests within a week. The gap isn't a flaky benchmark — it's that single-run pass/fail and production reliability are measuring completely different things. Your eval suite proved the agent *can* succeed. It said nothing about whether it *will* succeed at scale, under drift, or when tool shapes change.

## Forces

- **Single-run pass rate measures capability, not reliability.** A 98% pass rate on 100 curated cases tells you the agent has the capability to succeed. It tells you nothing about the distribution of failures, the trajectory quality, or how the agent behaves when it fails.
- **Benchmarks measure what agents *can* do, not what they *will* do in your system.** SWE-bench, WebArena, and GAIA evaluate model capability on standardized tasks. They don't measure whether your agent degrades when your API schemas shift, your vector store quality drifts, or your tool definitions become stale.
- **Trajectory is invisible to outcome-only metrics.** An agent can reach the correct answer via a broken reasoning chain that happens to land on the right answer — until a slightly different input causes it to confidently reach the wrong one. Outcome-only evals miss this entirely.
- **LLM output is non-deterministic, so human spot-checking doesn't scale.** Running the same test case twice can produce two different trajectories. Static golden-output comparisons fail. Teams need automated evaluation that accounts for probabilistic behavior.

## The Move

Build a two-layer evaluation system that measures both *how the agent reasons* and *what the agent produces*, then gate deployments on trajectory health, not just outcome accuracy.

**Step 1 — Separate trajectory metrics from outcome metrics.** Trajectory metrics evaluate the execution path: was the reasoning chain coherent? Were the right tools selected? Did the agent recover from errors? Outcome metrics evaluate the final result: did the task complete, and was the output correct? Track both separately. Trajectory tells you *why* the agent failed; outcome tells you *if* it worked.

**Step 2 — Use LLM-as-judge with a 0.80+ Spearman correlation target against human-labeled ground truth.** Train an automated judge on a human-curated calibration set. Verify the judge's agreement with humans before trusting its verdicts. Re-calibrate periodically as capabilities shift — an LLM judge that was 85% accurate six months ago may now be systematically over- or under-counting certain failure modes.

**Step 3 — Gate deployment with progressive thresholds.** Set environment-specific pass thresholds rather than a single bar: Development at 70% allows fast iteration, Staging at 85% forces production-quality reasoning chains, Production at 95% ensures only stable trajectories deploy. Any trajectory that exceeds max tool-call count, max execution time, or cost-per-task ceiling should auto-fail, independent of outcome.

**Step 4 — Integrate evals into CI/CD as a regression gate, not a pre-launch checkbox.** Run evaluation on every commit, on a schedule (catch regressions from upstream API changes), and on event triggers (new tool definition added, model upgraded). Treat eval failures as deployment blockers — not warnings.

**Step 5 — Select domain-matched benchmarks, not generic ones.** SWE-bench Verified for code agents, GAIA for general assistants, WebArena for web interaction. Use at least three benchmark suites that collectively cover the agent's actual tool categories. Generic MMLU/HumanEval scores are not proxies for agent performance.

**Step 6 — Measure cost-per-task alongside quality.** Track not just whether the agent succeeded but what it cost to succeed: token count, execution time, tool calls made. A 99% success rate at 3x budget is a different product than 95% at 1x budget. Set cost-per-task ceilings that auto-escalate to human review if breached.

## Evidence

- **Engineering blog (Dev Note, Apr 2026):** Production agent reliability challenges — trajectory vs. outcome metrics distinction. Documents that standard benchmarks miss production reliability challenges, and that trajectory metrics reveal *why* agents fail while outcome metrics only reveal *if* they failed. — [Dev Note: AI Agents in Production](https://devstarsj.github.io/ai/architecture/2026/04/11/ai-agents-production-architecture-patterns-memory-safety-reliability/)
- **LLM evaluation guide (Galileo AI, 2026):** Documents the 3-tier rubric approach (7 dimensions → 25 sub-dimensions → 130 items), LLM-as-judge Spearman correlation targeting 0.80+, and CI/CD integration patterns with commit/scheduled/event-driven eval triggers. Cites Gartner's prediction that over 40% of agentic AI projects will be canceled by end of 2027, driven largely by inability to measure reliability. — [Galileo AI: Agent Evaluation Framework](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Engineering blog (Harsha Rastogi, Mar 2026):** Real production failures: candidate evaluation agent hallucinated tool parameters and got stuck in loops (cost 3x budget); image pipeline approved flawed outputs because it optimized for workflow completion over quality. Both failed trajectory-level checks that outcome metrics would have missed. — [Harsha Rastogi: Agentic AI in Production](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Open-source framework (FuturOneAI, May 2026):** Production-grade eval framework with primary metrics: Task Completion Rate (>85%), First-Pass Accuracy (>70%), Tool Call Accuracy (>90%), Cost Per Task. Includes YAML benchmark definitions and progressive deployment gate structure. — [GitHub: FuturOneAI/ai-agent-evaluation-framework](https://github.com/FuturOneAI/ai-agent-evaluation-framework)

## Gotchas

- **Golden-output comparison fails for non-deterministic output.** The same input can produce two valid, different responses. Use rubric-based evaluation with LLM judges, not exact-match assertions.
- **Human spot-checking does not detect trajectory regressions.** You can manually verify 20 outputs per sprint and miss the 30% failure rate on the remaining 10,000. Automated trajectory-level regression gates are the only thing that scales.
- **Model upgrades invalidate your LLM-as-judge calibration.** A model swap changes what counts as a "good" trajectory. Re-run human calibration on every model change — the Spearman correlation target must be re-verified, not assumed.
- **Cost ceiling violations often precede quality failures.** An agent starting to loop often escalates cost-per-task before producing obviously wrong outputs. Treat cost as an early-warning signal, not a separate concern from quality.
- **Single benchmark suite gives you a false sense of coverage.** An agent that scores well on GAIA may still fail catastrophically on your domain-specific tool calls. Use at minimum three benchmark suites that cover distinct failure modes.
