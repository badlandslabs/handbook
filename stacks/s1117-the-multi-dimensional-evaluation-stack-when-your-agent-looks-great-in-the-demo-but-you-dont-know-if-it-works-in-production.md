# S-1117 · The Multi-Dimensional Evaluation Stack — When Your Agent Looks Great in the Demo But You Don't Know If It Works in Production

Your agent passes every demo. Your users still complain. The benchmark says 91% success. Your production logs say something different. You have no systematic way to know which signal is right — and no way to catch regressions before they ship. You need a multi-dimensional evaluation stack: metrics that actually measure what matters in production, not just what is easy to score.

## Forces

- **Pass@1 is a lie told with numbers.** A 75% single-trial success rate sounds decent until you run pass@3 and get 42% (0.75³). For agents where consistency matters — customer-facing, safety-critical, or multi-step — you need pass@k and pass^k, not pass@1. A model that is impressive once is not necessarily reliable every time.
- **Task completion is necessary but insufficient.** Many teams track "did the agent finish the task?" while ignoring cost per completion, safety violations, hallucinated tool calls, and recovery behavior after failure. These second-order effects compound in production.
- **Benchmarks are statistically contaminated.** UC Berkeley researchers found that eight of the most prominent AI agent benchmarks have significant data contamination — training data overlap, answer leakage into agent-accessible space, and static test sets that decay as frontier capability improves. Public leaderboard scores may not reflect real-world performance.
- **Deterministic checks and LLM judges serve different purposes.** Regex assertions catch hard failures (did it call the right tool? did it output valid JSON?). LLM-as-judge catches qualitative failures (did it explain the reasoning? was the tone appropriate?). Neither alone is sufficient.
- **Human evaluation is slow and expensive — but still irreplaceable for calibration.** The MAP survey (N=306 practitioners, 20 case studies) found 74% of production teams rely primarily on human evaluation. The gap between "what the eval says" and "what the user experiences" requires periodic human sampling to close.

## The Move

Build a layered evaluation stack that answers four questions at once:

- **Can it do the task?** (Task success — deterministic check or ground truth comparison)
- **Did it do it the right way?** (Behavioral quality — tool call sequence, recovery, cost efficiency)
- **Is it safe?** (Constitutional constraints — no PII leakage, no harmful outputs, no tool misuse)
- **Will it keep working?** (Regression suite — run against every code change, model upgrade, and prompt revision)

### Implementation

- **Define task-level success criteria before writing a single line of prompt.** A task is a (problem, success criteria, environment state) tuple. The agent harness runs trials against the environment and checks state after. Score 1 if the final state meets criteria, 0 otherwise.
- **Use deterministic checks for hard constraints.** Tool called? Schema valid? API returned 200? State mutated correctly? These are cheap, fast, and unambiguous. Write them first.
- **Use LLM-as-judge for qualitative dimensions.** Evaluate tone, reasoning coherence, explanation quality, and "would a human find this useful?" Use a different model for judging than the one being evaluated. Inject the judging criteria as structured rubric, not freeform.
- **Report pass@k and pass^k, not just pass@1.** Run k trials per task. pass@k = probability at least one succeeds (optimistic). pass^k = probability all k succeed (consistency). For user-facing agents, pass^k is the more honest product metric.
- **Track cost-per-task and latency-per-task as first-class metrics.** An agent that achieves 95% success at $4.20 per task is a different product than one at 93% for $0.12. Optimization without cost awareness is a business blind spot.
- **Build a regression suite of known failure cases.** When a production bug slips through, add the failing input to the eval suite before you fix the code. This makes eval suites grow organically from real failures, not from imagined edge cases.
- **Sample production traces for human review on a schedule.** Set a cadence — e.g., weekly — to have a human label a random sample of N traces. Compare human labels to eval scores. When they diverge, the eval is wrong, not the agent.

## Evidence

- **Survey (N=306, 20 case studies):** "68% execute at most 10 steps before requiring human intervention, 70% rely on prompting off-the-shelf models instead of weight tuning, and 74% depend primarily on human evaluation." Production teams favor simplicity and control over SOTA methods. — *Pan et al., "Measuring Agents in Production," arXiv:2512.04123, December 2025* — [https://arxiv.org/abs/2512.04123](https://arxiv.org/abs/2512.04123)

- **Engineering post:** Anthropic's eval taxonomy distinguishes three components: the task (problem + success criteria), the trial (one stochastic attempt), and the agent harness (scaffold that runs the agent and feeds it environment state). Agents differ from chat responses because they mutate external state — evaluating only the final message misses the actual outcome. — *Anthropic Engineering, "Demystifying Evals for AI Agents," January 2026* — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **HN thread (43 comments):** Practitioners described eval practices ranging from "no evals at all" to sophisticated pipelines with LangFuse, promptfoo, and LLM judges — described as "very, very heterogeneous and fast moving." Core challenge: the same prompt produces different quality across model families, and subjective quality ("good response") remains unsolved without human judgment. — *yelmahallawy, "Ask HN: How are people doing AI evals these days?" Hacker News, March 2026* — [https://news.ycombinator.com/item?id=47319587](https://news.ycombinator.com/item?id=47319587)

## Gotchas

- **Do not grade only the final message.** An agent that takes 47 steps and arrives at the wrong answer looks identical to one that gets there quickly if you only read the output. Instrument the tool call sequence and inspect intermediate state.
- **LLM judges are not ground truth.** They are useful proxies, but they have biases, drift with model version updates, and can be gamed by prompt injection in adversarial settings. Treat them as one input to the decision, not the decision itself.
- **Benchmarks decay.** A static benchmark that was hard in 2024 may be trivially solved in 2026, inflating apparent model improvements. Prefer procedural or live-environment benchmarks when possible. Cross-reference benchmark results with production trace sampling.
- **One eval run is not enough.** Non-determinism means a single run gives you one sample from a distribution. Run multiple trials, report confidence intervals, and distinguish between a bad run and a bad agent before debugging the wrong thing.
