# S2047 · Measuring the Agent That Measures Itself: The Multi-Dimensional Agent Eval Stack

You built the agent. It calls tools, loops, recovers. Now you need to know if it actually works — across the full distribution of real inputs, not just the ones you tested on. Traditional test suites won't tell you; the agent is non-deterministic and multi-step.

## Forces

- **Reliability collapse:** An agent hitting 60% on a single run drops to ~25% across 8 consecutive runs. Standard evaluation misses this entirely — you only see it when you measure consistency over multiple trials.
- **Trajectory vs. outcome:** The final answer is only part of the story. A wrong tool call in step 3 can accidentally produce a right answer in step 5. Evaluating only outcomes gives false confidence; evaluating only reasoning chains misses the point.
- **Non-determinism is the norm, not the exception:** Identical inputs can produce different trajectories. A single eval run tells you almost nothing. You need pass@k over many trials, and you need to know when a flaky pass is actually a failure.
- **Grader quality is the ceiling:** Your eval is only as good as your grader. A code-based grader that checks structured outputs is precise but narrow. An LLM judge is flexible but can be wrong and overconfident. Most teams use the wrong grader for the wrong thing.
- **Eval maintenance is underappreciated:** As agent behavior changes (prompt updates, model swaps, tool logic changes), eval cases go stale. Unmaintained evals give false signal. This is the most common reason eval programs fail in practice.

## The Move

Build a three-layer eval program: task success, step-level quality, and system health. Run multiple trials, use calibrated graders, and wire results into CI.

**Three eval dimensions, not one:**

- **End-to-end task success** — Did the agent achieve the user's goal? Did the final action produce the right state? This is what most teams measure; it's necessary but insufficient.
- **Step-level quality** — Did the planner pick the right tool? Did each step move the agent forward? Tool-call accuracy and recovery from errors are the key signals here.
- **System-level performance** — Latency, cost, token-per-task ratios, error rates, and robustness to adversarial or malformed inputs. This is where production incidents surface before users notice.

**Use pass^k for reliability, not pass@1:**

For an agent with 70% per-trial success, pass@1 is ~70% but pass^3 (failing all 3 trials) drops to ~34%. Run at minimum 3 trials per task; 5–10 for high-stakes agents. Track both pass@1 and pass^k to detect reliability collapse.

**Choose graders by task type:**

- **Code-based graders** (regex, JSON schema validation, assertions) for anything with a structured ground truth — tool call arguments, return types, state mutations. Fast, deterministic, cheap. Use these wherever possible.
- **LLM-as-judge** for open-ended quality — did the agent handle edge cases gracefully? Was the explanation coherent? Calibrate against 100+ human-labeled examples before trusting the judge; require Fleiss kappa ≥ 0.6 vs. human reviewers.

**Build eval datasets from production failures, not intuition:**

The best eval cases come from real agent failures in staging or production traces. Log failed trajectories, extract the input pattern, write a deterministic check for that failure mode. This is the "golden dataset" that grows over time.

**Gate CI on eval scores, not just linting:**

A regression in your agent should block a merge, the same as a regression in any other critical system. Define a minimum pass rate (e.g., 85% pass@3) per eval suite and treat it as a first-class quality gate.

**Track trajectories, not just outcomes:**

Store full transcripts (tool calls, intermediate results, reasoning steps) for every eval trial. When a task fails, the transcript tells you whether it was a reasoning failure, a tool failure, or bad luck from non-determinism. This is the difference between fixing the root cause and guessing.

## Evidence

- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" (Jan 2026) establishes the three-dimensional eval framework — tasks, graders, and outcomes — and defines key terminology (trial, transcript, grader). Emphasizes that agents require measuring trajectories, not just final outputs. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Industry research:** Digital Applied's "AI Agent Evaluation Pipeline: 2026 Methodology" (June 2026) reports the pass@3 vs pass^3 gap empirically — a 70%-per-trial agent shows 97% pass@3 vs ~34% pass^3, a 63 percentage-point collapse. Also reports that elite teams spend 60–80% of development time on evals, and that 100+ labeled examples with kappa ≥ 0.6 are the minimum bar for trusting an LLM judge. — [digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology](https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)
- **Y Combinator launch:** Lucidic AI (YC W25) — founded by Stanford AI Lab researchers — identifies the core observability gap: traditional LLM tracing misses agent-specific failure modes like behavioral loops, wrong tool selection, and state mutation errors. The HN discussion surfaced that eval cases added without systematic maintenance go stale as agent behavior evolves, a problem echoed across multiple practitioner discussions. — [news.ycombinator.com/item?id=44735843](https://news.ycombinator.com/item?id=44735843)
- **Benchmark data:** Presenc AI's "Coding Agent Benchmarks 2026" shows SWE-Bench Verified climbing from 13% (2024) to 74–78% (May 2026) for top agents, while real-world PR pass rates sit at 35–50% — a significant gap between benchmark performance and production reality that standard evals alone don't close. — [presenc.ai/research/coding-agent-benchmarks-2026](https://presenc.ai/research/coding-agent-benchmarks-2026)

## Gotchas

- **Measuring only outcomes hides the failure mode.** An agent can arrive at a correct answer via wrong reasoning (e.g., wrong tool, accidental correct result). Without trajectory inspection, you won't catch the reasoning failure — and it will surface as a real failure on the next similar input.
- **A single eval run is nearly meaningless for agents.** Non-determinism means one pass/fail is almost random. Always run k trials and report both pass@1 and pass^k. Teams that don't do this are flying blind on reliability.
- **LLM judges are wrong more often than they look.** Without calibration against a human-labeled gold set, an LLM judge can be confidently wrong — especially on edge cases. Require statistical agreement (kappa ≥ 0.6) before trusting judge verdicts for any high-stakes decision.
- **Eval suites rot fast.** Prompt changes, model swaps, tool API updates — any of these can invalidate eval cases. Treat eval maintenance as a first-class engineering concern, not a one-time setup.
- **Cost accumulates quickly.** Running 10 trials × 1000 eval cases × multiple agent configurations = substantial token spend. Budget for eval infrastructure separately from agent infrastructure.
