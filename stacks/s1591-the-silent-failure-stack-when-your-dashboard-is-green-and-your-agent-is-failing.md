# S-1591 · The Silent Failure Stack — When Your Dashboard Is Green and Your Agent Is Failing

Your APM dashboard is green. No exceptions, no timeouts, no 500s. Your agent processed 3,000 tickets overnight. Every HTTP response was 200. You get to work and find 47 customer complaints: wrong answers, looping until timeout, a confident email to a vendor that committed your company to terms that don't exist. The agent never crashed. It succeeded at running and failed at the job. This is the silent failure problem — and it's the defining operational challenge of agentic systems in production.

## Forces

- Traditional APM assumes a request is a deterministic unit: it either succeeds or fails with a clear signal. Agentic requests are probabilistic, multi-step workflows where "success" is a spectrum, not a boolean.
- Agents can produce wrong outputs while returning HTTP 200 — the entire traditional monitoring contract breaks down.
- The failure surface is enormous: tool parameter hallucination, wrong tool selection, loop detection, policy violations, cost overruns, and outcome failures that no log line captures.
- The gap between what you measure (latency, uptime, error rate) and what matters (did the agent do the right thing?) is where production incidents hide.
- Sampling traces in production is necessary but not sufficient — you need a signal that tells you *which* traces to look at.

## The Move

The move is **observability-first production monitoring**: treating the execution trace as the primary artifact, deriving all metrics from it, and building a layered monitoring strategy that catches silent failures before users do.

- **Trace everything by default.** Capture full LLM call inputs/outputs, tool arguments and responses, latencies per step, token counts, session grouping. The trace is the raw material every other metric is derived from. Without it, you cannot debug a silent failure.
- **Track step count and token burn rate.** An agent that normally takes 5 steps suddenly taking 47 is a loop. An agent that normally costs $0.02 suddenly costing $3.20 is either attacking a hard problem or hallucinating its way through a dead end. Both are silent failures. Set thresholds and alert on deviation from per-workflow baselines.
- **Distinguish technical health from outcome quality.** Technical health (HTTP 200, no exceptions, fast responses) tells you the agent ran. Outcome quality tells you if the run was correct. You need both — and conflating them is how silent failures survive into production.
- **Implement lightweight output verification.** For structured-output workflows, validate against expected schemas. For classification tasks, spot-check against a golden dataset. For generative tasks, use an LLM judge with calibrated rubric. The key is *defined success criteria per workflow* — without them, you only find failures from user complaints.
- **Build a human review queue for edge cases.** Route low-confidence outputs, high-stakes actions (sending emails, issuing refunds, updating records), and novel input patterns to human review. Tagging these traces creates training data for future evals.
- **Convert failing production traces into regression evals.** Every silent failure you catch is a candidate for a golden test case. Braintrust and similar platforms recommend turning the input from a failing trace into an eval that prevents regression. This closes the feedback loop from production back to development.

## Evidence

- **HN Ask thread:** Practitioners shared incidents including the DataTalks database wipe by Claude Code and a Replit agent deleting data during a code freeze — both caused by agents with no step-level visibility and no human-in-the-loop guardrails. The community's response converged on tracing SDKs (AgentShield, OpenTelemetry) and cost-per-agent tracking as minimum viable observability. — [Ask HN: How are you monitoring AI agents in production? — news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **Inference.net guide:** Documents the five core failure modes specific to agents: wrong tool selection, tool parameter hallucination, partial success (tool call returns partial data), looping (excessive tool calls), and cost overruns from exponential token growth. Proposes deriving all metrics from the execution trace as the primary data source. — [AI Agent Monitoring: Metrics, Traces & Failure Modes — inference.net](https://inference.net/content/ai-agent-monitoring/)
- **Thoughtworks framework:** Reports that ~95% of enterprise AI projects fail, and Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation and monitoring rather than model capability gaps. Proposes a layered eval strategy: synthetic personas in dev, refined personas in UAT, real-world monitoring in production — with the personas evolving based on authentic user intent. — [Evaluating AI agents in production: A practical framework — thoughtworks.com](https://www.thoughtworks.com/en-us/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)

## Gotchas

- **Sampling full traces can miss your worst failures.** PII risk and storage cost drive teams to sample, but rare failure modes (1-in-500 runs) are exactly the ones that cause incidents. Sample intelligently — sample at high rate for high-stakes workflows, and always capture error traces at 100%.
- **Latency percentiles lie for agents.** P50 latency can look healthy while P99 spikes because an agent called three slow tools in sequence. Track P50/P90/P99 per LLM call *and* per full session — the session-level metric reveals the agentic overhead that per-call metrics hide.
- **Golden datasets go stale.** A golden dataset that isn't refreshed quarterly becomes a measure of historical failure modes, not current ones. Treat your golden dataset as a living artifact fed by production failure cases.
