# S-1415 · The Agent Evaluation Stack — When You Ship an Agent and Have No Idea If It's Working

Your agent passed the demo. It passed the five test cases you wrote. You shipped it. Two weeks later you're getting bug reports you can't reproduce, watching an agent loop forever in production, and discovering a $4,000 API bill because nobody was tracking tokens per task. The demo worked. The evaluation didn't.

## Forces

- **Standard unit tests don't work on probabilistic systems** — an LLM doesn't return the same output twice on the same input, and "correctness" is a matter of degree, not a binary pass/fail. The entire premise of unit testing breaks when the system you're testing is non-deterministic by design
- **Task completion and output quality are different problems** — an agent can generate a perfectly formatted, grammatically correct response that completely misses the user's intent. Traditional metrics like BLEU and ROUGE measure text quality, not task success. They tell you nothing about whether the agent actually did the right thing
- **The path matters as much as the destination** — agents that reach the correct final answer via broken reasoning, excessive tool calls, or dangerous permissions are failures even when the output looks right. Final-answer scoring hides trajectory quality entirely
- **Production reveals failure modes that demos never surface** — loops, hallucinated tool arguments, silent API failures, permission boundary violations. These don't appear in curated test sets. Only production traffic or shadow evaluation catches them

## The Move

Evaluate across three layers, not one:

- **Final-answer scoring** — does the agent complete the task? Pass/fail against ground truth, or LLM-as-judge scoring on a rubric. This is the minimum. It's also insufficient alone.
- **Trajectory analysis** — examine the full sequence: tools called, arguments passed, loops detected, recovery attempts. Requires tracing the complete span tree from start to end. Catch the agent that reaches the right answer through the wrong steps.
- **Per-turn production labeling** — real-time classification of each turn in production. Flag looping, hallucinated tool names, permission creep, and silence. Feed these labels back into the regression suite so tomorrow's version learns from yesterday's failure.

Measure four dimensions simultaneously:

- **Task completion rate** — did it finish? Did it finish correctly?
- **Tool call accuracy** — right tool, right arguments, appropriate frequency
- **Output quality** — grounded, relevant, safe, well-formed
- **Failure recovery** — does it fail gracefully? Does it retry intelligently? Does it escalate?

Build a layered evaluation pipeline:

- **Offline regression suite** (CI gate) — run on every commit against a curated golden dataset. Catch regressions before deploy. Re-run critical scenarios even on "pass" — models are stochastic and a single pass can mislead.
- **Shadow evaluation** (production mirror) — run the new version against sampled real traffic in parallel. Compare distributions, not just averages. Two versions can have the same average score while failing on completely different tasks.
- **Human calibration sample** (ground truth anchor) — have humans score a small sample of traces on a rubric. Use these to validate and calibrate LLM-as-judge accuracy. Catch "metric green, user red" gaps.

Track operational constraints as first-class metrics:

- Cost per task, latency per step, token efficiency, tool reliability rate, policy compliance rate
- These determine whether a technically capable agent is viable at enterprise scale

## Evidence

- **Survey (Cleanlab, 2025):** Out of 1,837 engineering/AI leaders surveyed, only 95 had AI agents deployed in production. Of those with agents live, fewer than 1 in 3 were satisfied with their observability and guardrail solutions. 70% of regulated enterprises reported rebuilding their AI agent stack every 3 months or faster — primarily due to lack of reliable evaluation. — [Cleanlab: AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **HN discussion:** In response to recent production incidents (DataTalks database wiped by Claude Code, Replit agent deleting data during code freeze), practitioners shared common failure modes: no step-by-step visibility into agent actions, surprise LLM bills from untracked token usage, risky outputs going undetected, and no audit trail for post-mortems. Solutions included execution tracing, per-agent cost tracking, and human-in-the-loop approval for high-risk actions. — [Hacker News: Ask HN — How are you monitoring AI agents in production?](https://news.ycombinator.com/item?id=47301395)
- **Engineering blog (Inductivee, 2025–2026):** "You cannot unit test an LLM. But you can systematically evaluate agent behavior through statistical measurement over sampled inputs." Four-dimension framework: task completion rate, tool call accuracy, output quality, and failure recovery behavior. Core insight: the goal is statistical reliability, not deterministic reproducibility — measure pass rates over 200 test inputs, not pass/fail on single runs. — [Inductivee: How to Test Autonomous Agents](https://inductivee.com/blog/ai-agent-evaluation-testing-framework)
- **Guide (Microsoft AI Agents for Beginners, 2026):** Observability for agents uses trace/span semantics — a trace is the complete agent task from start to finish; spans are individual steps within it. Tools like Langfuse and Microsoft Foundry provide this structure. Straces enable step-by-step replay, per-step cost/latency attribution, and failure localization. — [Microsoft: AI Agents in Production — Observability & Evaluation](https://microsoft.github.io/ai-agents-for-beginners/10-ai-agents-production/)

## Gotchas

- **Single-pass final-answer scoring gives false confidence** — the answer can be right while the path was wrong, expensive, or unsafe. Always complement final-answer metrics with trajectory analysis
- **LLM-as-judge needs its own validation** — the judge model can be biased, inconsistent, or systematically wrong. Calibrate against a human-scored sample before trusting judge scores at scale
- **Golden datasets stale fast** — production distributions shift. A regression suite that isn't refreshed becomes a false negative factory. Build periodic dataset refresh into the evaluation workflow
- **Average scores hide distribution** — two agent versions can have identical average scores while failing on completely different tasks. Always compare per-task distributions, not just aggregates
- **Observability without actionable alerting is noise** — tracing every step generates enormous data. Without automated anomaly detection and alert thresholds, you get dashboards nobody reads until something breaks
