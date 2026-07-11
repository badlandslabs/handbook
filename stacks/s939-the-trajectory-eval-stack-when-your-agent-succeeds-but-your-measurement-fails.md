# S-939 · The Trajectory Eval Stack — When Your Agent Succeeds but Your Measurement Fails

You run your eval suite. Green across the board. You deploy. Users complain within the week. The agent isn't worse — your measurement was wrong all along. You were optimizing against a folder of 20 examples someone wrote before a demo, and treating a confident-looking number as ground truth. Agent evaluation is not LLM evaluation. The same tools that grade a chatbot will miss the failure modes that actually kill production agents.

## Forces

- **Agents have trajectories, not just outputs.** A single-turn LLM eval is clean: prompt in, response out, grader scores it. Agents use tools across many turns, modify state in their environment, and adapt mid-flight. Mistakes propagate and compound. Final outcome can be correct even when the path looks wrong — or vice versa.
- **Trajectory metrics and outcome metrics measure different things.** You can fail at the goal but succeed at the process (wrong answer, right reasoning). You can succeed at the goal but fail at the process (right answer, dangerous path). Which do you care about?
- **Your eval dataset is probably lying to you.** A folder of twenty examples written in an afternoon, mixed with support tickets pasted in before a demo, produces a precise-looking score that means nothing. Optimizing a prompt against a bad dataset for weeks produces a beautiful eval curve while production quietly degrades.
- **LLM-as-judge is your only scalable option for subjective quality — and it's also the most fragile.** One model judging another that can hallucinate. Eval-aware models can recognize benchmarks and decrypt answers. Conventional metrics (BLEU, ROUGE) measure surface overlap, not meaning.

## The move

**Separate what you can score programmatically from what needs an LLM judge, then build a golden dataset that mirrors production reality — not demo reality.**

### The four-bucket golden dataset

Structure your eval set in four buckets with proportional sizing from production data:

- **Stratified production sample (60%)** — random sample of real inputs from production traffic, labeled by domain experts. Defines what "correct" actually means for your agent in context.
- **Adversarial coverage (15%)** — inputs specifically designed to trick or confuse the agent. Capture the edge cases attackers probe.
- **Edge cases (15%)** — low-frequency but high-impact scenarios (rare error states, unusual user intents, tool failures).
- **Failure replays (10%)** — exact transcripts of past production failures. Retest them every run to prevent regressions.

### Evaluate trajectories, not just outputs

For agentic systems, scoring the final text is insufficient. Check three things per step:

1. **Did the agent call the right tool?** Correct final answer without the right tool call is still a bug — the agent didn't accomplish the task through the intended mechanism.
2. **Did it pass the right parameters?** `initiateRefund(amount: 0)` instead of `initiateRefund(amount: 49)` is a silent failure no text scorer catches.
3. **Did it follow the required sequence?** Missing a required intermediate step is a failure even if the final state looks right.

### Dual-scoring: code-based + LLM-judge

Use fast, cheap, deterministic **code-based scorers** for everything you can express as logic: regex checks, JSON structure validation, exact-match assertions, tool-call sequence verification. Reserve **LLM-as-judge** for the cases where deterministic scoring genuinely cannot capture what you need — tone, reasoning quality, helpfulness, policy adherence.

For LLM-as-judge, calibrate your judge model against multi-rater human labels targeting **0.80+ Spearman correlation** with human judgment before using it as a gate. Track judge consistency over time. Know which monitors are "soft" (trend monitoring) and which are "hard" (immediate alert on breach).

### Build eval into every sprint

The eval harness is not a release gate — it's a development tool. Wire it into CI so it runs on every commit. Run evaluation against your benchmark dataset before every deploy. Track score trends over time intervals (hour, day, week). When prompt changes, model updates, or data drift happen, you catch regression before users do.

Start small: **20–30 curated examples and 3–5 scorers** are enough to begin catching regressions. Grow coverage as the agent matures.

### Watch for eval contamination

Web-enabled models (Claude Opus 4.6, GPT-4o) can recognize benchmarks, find test instances, and decrypt answers. When models are web-accessible, eval integrity breaks. Use closed-world evals, rotate test sets, or implement eval-awareness mitigations. Monitor for anomalous accuracy spikes that suggest contamination.

## Evidence

- **Anthropic Engineering:** Claude's own team defines agent evals as distinct from LLM evals — a grader scores a transcript (complete record of outputs, tool calls, responses) not just the final output. Their production agents like Claude Code use multi-trial runs per task to account for output variance. They emphasize that good evals make problems visible *before* users are affected. — [Anthropic Engineering: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Nearform (Alfonso Graziano, March 2026):** Building on 100+ enterprise agent deployments, Nearform found the top failure mode after POC is teams that only evaluate final text output. Their recommended fix: code-based scorers for deterministic checks + LLM-as-judge for nuanced quality, plus golden datasets built with domain experts. Specifically calls out that tool-call correctness (right tool, right parameters, right sequence) must be evaluated independently of output quality. — [Nearform: From AI Prototype to Production: Building Evals for Reliable Agents](https://nearform.com/digital-community/from-ai-prototype-to-production-how-to-build-evals-for-reliable-agents)

- **Galileo AI / Gartner:** Enterprise AI agents achieve ~60% success on single runs, dropping to ~25% across eight runs — a reliability variance that benchmarks don't capture. Survey of 100+ enterprise deployments identified a 12-metric framework covering trajectory-level (reasoning, tool selection, decision sequences) and outcome-level (final task completion) dimensions separately. Monte Carlo found that BLEU/ROUGE have low correlation with human judgment for open-ended tasks, validating the LLM-as-judge approach for subjective quality. — [Galileo AI: Agent Evaluation Framework — Metrics, Rubrics & Benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

- **Hacker News (roadside_picnic, HN #44712315):** Community discussion on agent evaluation practices surfaced that the #1 reason teams don't catch regressions is treating the eval dataset as an afterthought. One commenter: "Did we just give up on evaluations these days? Over, and over again." — [HN: Principles for Production AI Agents — Discussion](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **Over-relying on LLM-as-judge without calibration.** An uncalibrated judge will produce confident scores that correlate poorly with actual quality. Always measure judge accuracy against human labels before trusting it as a release gate.
- **Eval contamination in web-enabled models.** Models with web access can recognize benchmarks. High accuracy on a benchmark in a web-enabled context may reflect contamination, not capability. Use closed-world evals or benchmark rotation for production agents.
- **Conflating trajectory success with outcome success.** A safe, reasoning-heavy path that fails to reach the goal is a real failure. A dangerous path that reaches the right answer is also a real failure. Measure both dimensions independently.
- **Small, unrepresentative eval sets.** 20 examples written by engineers for happy paths will miss the edge cases that surface in production. Build your dataset from production data and adversarial inputs, not just engineer-authored test cases.
- **Not versioning the golden dataset.** When your agent changes, your eval set ages. Track which examples map to which agent version, and recalibrate when you add new capabilities.
