# S-2677 · The Evaluation Stack — When Your Agent Succeeds in Staging and Disappears in Production

Your agent passed every test you wrote. It still fails in production — silently, expensively, and without warning. The gap isn't the model. It's that you're testing outputs when you should be testing trajectories. This stack covers how teams actually measure agent quality in production, from the three-layer evaluation model to the observability tooling that makes debugging tractable.

## Forces

- **The single-run illusion** — agents scoring 60% on one run drop to 25% across eight runs. Single-turn eval pass rates are almost meaningless for production readiness
- **Trajectory vs. outcome mismatch** — you can get the right answer via the wrong reasoning path and never catch it with output-only scoring
- **Non-determinism breaks traditional testing** — unit tests assume `f(x) = y`. Agents assume `f(context) ≈ y` with non-deterministic variance you can't suppress
- **Cost observability gap** — agents that loop or re-call tools can spike token costs 5–10× without any quality signal in the output
- **The silent quality cliff** — LLM drift, upstream data changes, and tool API changes degrade agent quality gradually, without throwing errors

## The move

**Build a three-layer evaluation stack that runs continuously, not just at deploy time.**

1. **Output (unit) layer** — does the final response match the expected answer or format? Fast, cheap, automatable. Use for regression on structured tasks. This catches obvious failures but misses trajectory problems.

2. **Trajectory (integration) layer** — did the agent take a reasonable reasoning path? Did it call the right tools in the right order? Did it recover from failures? Trace the full execution tree and score tool-call sequences, decision points, and recovery attempts. This is where agents reveal their hidden failure modes.

3. **Outcome (live) layer** — did the task actually accomplish the user's goal across real production traffic? Correlate with user feedback, downstream system state, or business metrics. This is ground truth and must run on live data, not synthetic test cases.

**Instrument before you optimize.** Every agent step should emit a trace: input, LLM call, tool call, output, tokens, latency, cost. Langfuse, LangSmith, or Braintrust all provide this. Without traces, you're debugging a black box.

**Use LLM-as-judge targeting 0.80+ Spearman correlation with human judgment.** For trajectory and outcome evaluation, an LLM evaluator with a well-designed rubric outperforms automated string matching. Calibrate against human labels before trusting it.

**Set cost and step limits with hard circuit breakers.** `max_iter=5-8` per agent (not the default 25). Track token spend per run and alert at thresholds. One unbounded loop can burn a month's budget in minutes.

**Run evals on every commit, not just pre-deploy.** Agent quality regresses silently when upstream dependencies change. CI-triggered eval suites on git push catch drift before users do.

## Evidence

- **Blog post (Ashutosh Tripathi, Principal ML Engineer):** "Agents aren't deterministic systems. They don't just execute predefined logic. They make decisions based on context, they choose which tools to use, they navigate multi-step workflows, and they reason through problems in ways that can vary each time." The three-layer model (output, trajectory, outcome) must run simultaneously — any single layer misses at least two categories of production failure. — [ashutoshtripathi.com, Dec 2025](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide/)

- **AI observability comparison (jangwook.net, Mar 2026):** Five real contenders in the observability space: LangSmith (best LangChain integration, most polished), Langfuse (best open-source, self-hostable), Braintrust (best evaluation workflows), Helicone (cheapest, easiest drop-in), and Arize Phoenix (best open-source eval framework). On traces: Langfuse wins for self-hosting flexibility, LangSmith wins for out-of-the-box agent visualization, Braintrust wins for eval workflows, Helicone wins for fastest time-to-first-trace. "If you can't answer 'why did it give that response?' and 'how much did it cost?' within 5 minutes in a multi-agent system, you've already lost control of it." — [jangwook.net](https://jangwook.net/en/blog/en/ai-agent-observability-production-guide/)

- **HN Ask HN thread (2025):** 7 engineers responding to monitoring failures (DataTalks DB wipe by Claude Code, Replit agent deleting data during code freeze) named the same four gaps: no step-by-step visibility, untracked token spend, undetected risky outputs, no audit trail. Tools named: AgentShield (execution tracing + risk detection + cost tracking + human-in-the-loop), Lava (gateway proxy with spend keys), OpenTelemetry + custom dashboards. — [HN 47301395](https://news.ycombinator.com/item?id=47301395)

- **Galileo AI evaluation framework (Feb 2026):** "Agents can achieve 60% success on single runs, dropping to 25% across eight runs." Production eval must use trajectory metrics alongside outcome metrics. Recommended benchmarks: WebArena for web agents, SWE-bench Verified for coding agents, GAIA for general assistants. LLM-as-judge should target 0.80+ Spearman correlation before being trusted. Over 40% of agentic AI projects will be cancelled by end of 2027 — weak evaluation is cited as the primary cause. — [galileo.ai](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **Evaluating only the final output misses loops, tool call spam, and recovery failures.** A correct answer via a 47-step reasoning chain is not the same as a correct answer via 3 steps. Score the path, not just the destination.
- **Synthetic test sets go stale fast.** Real production inputs surface failure modes that hand-curated eval sets never catch. Build mechanisms to sample live traffic into eval pools continuously.
- **LLM-as-judge correlation drifts.** The judge model's standards shift as it gets updated. Re-calibrate against human labels on a monthly cadence, at minimum.
- **`max_iter` defaults (25 in CrewAI) are cost traps.** Set explicit step limits per agent. Track cost-per-task and alert on statistical outliers — one looping agent can cost more than the rest combined.
- **Trajectory eval is computationally expensive.** Scoring full execution trees is 10–50× slower than output scoring. Run trajectory eval on a sample or on triggered conditions (new code, new tools, new model), not on every request.
