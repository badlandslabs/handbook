# S-2097 · The Silent Failure Blindspot Stack — When Your Agent Succeeds But Your Users Don't

Your agent ran 12,000 times last week. Zero errors in your dashboard. Your error rate dashboard is green. Then a power user sends you a screenshot: the agent has been routing every international ticket to the domestic queue for three weeks. Nobody noticed because the request completed, returned valid JSON, and never threw a single exception. This is the silent failure blindspot — the gap between "did it run?" and "did it do the right thing?"

## Forces

- **Standard monitoring only answers the first question.** Uptime, latency, error rate, and throughput — every monitoring system answers "did the process execute?" not "did it produce the right output?" Silent failures live in the second question.
- **Agents are designed to produce plausible output.** LLMs are trained to fill gaps, infer missing fields, and generate coherent responses from ambiguous input. This is the opposite of what you want when something goes wrong — you want the agent to say "I don't know" instead of fabricating a confident answer.
- **HTTP 200 is the enemy of detection.** Silent failures return normal HTTP responses with wrong results. No exception fires. No alert fires. Your incident dashboard shows green while customers get wrong answers.
- **Retries can mask or compound the problem.** An agent that retries a failed tool call and gets a different error may silently resolve onto a weaker execution path — still completing, still returning 200, still wrong.

## The Move

Layer output-level validation as a first-class monitoring concern, not an afterthought:

- **Deploy a grader agent alongside your execution agent.** A second, lighter model (or the same model with a validation-focused prompt) reviews the output before it's returned to the user. Check: does the output actually answer the user's request? Are key fields populated correctly? Does the classification match what a human would assign?
- **Implement structural output validation.** Parse the response schema and assert non-nullability on required fields. A tool that returns `{}` is not an error — it's a silent failure. Assert that `ticket_type` is one of the valid enum values, not an invented variant the model hallucinated.
- **Build fail-plausible escalation.** The observer should not just detect failure — it should surface doubt upstream. Glivera's four-layer architecture surfaces the quality signal before it reaches the client. The grader writes to a separate channel that your on-call team monitors.
- **Instrument tool call boundaries with semantic checks.** Don't just log that `search_database` was called and returned in 200ms. Log whether the returned rows match the expected schema. Log whether the result set is non-empty when the user asked for a specific record. Log whether the response time changed significantly from baseline.
- **Watch for confidence drift, not just errors.** The Anthropic Sonnet 4 incident (August 2025) showed that model quality can degrade silently for weeks — 0.8% of requests at first, reaching 16% at peak — with latency, error rate, and throughput all unaffected. Detecting it required evaluating outputs against ground truth, not infrastructure signals.
- **Log the rejection rate, not just the error rate.** Your grader's rejection rate is the metric that tells you whether your agent is producing reliable output. A rising rejection rate is a leading indicator; a green error rate is a lagging one.

## Evidence

- **Engineering blog (Anthropic, Sep 2025):** A routing misconfiguration sent Claude Sonnet 4 requests to servers provisioned for a different context window. The bug affected 0.8% of requests initially, worsening to 16% at peak hours. It ran for weeks undetected. Anthropic's postmortem concluded: "We relied too heavily on noisy evaluations" — the monitoring showed no latency, throughput, or error rate anomalies. — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)
- **Engineering blog (Glivera, May 2026):** Silent failures fall into three classes: hallucination under confidence (model fills missing input with plausible-but-wrong data), structural null embedding (required fields silently nullified), and downstream silent corruption (valid-seeming data passed to dependent systems). Production systems that compound in reliability "flag their own doubt before it becomes the client's problem." — [Glivera](https://glivera.com/blog/silent-failures-agent-systems/)
- **Technical blog (Tessary, Jun 2026):** Four classes of silent failure account for most production incidents: hallucinated tool calls, tools that return with wrong data, quality decay after model changes, and retries that resolve onto a weaker path. Detecting them requires "graders over real traffic, not raw trace counts." — [Tessary](https://tessary.ai/blog/silent-llm-agent-failures)
- **HN discussion (543 points, Jun 2025):** Debate over Anthropic's "Building Effective Agents" post surfaced the framework vs. direct-API debate, but multiple practitioners noted the hardest production problem isn't architecture choices — it's knowing when the agent is quietly producing wrong output. — [Hacker News](https://news.ycombinator.com/item?id=44301809)

## Gotchas

- **Infrastructure monitoring and output monitoring are different disciplines.** You can have perfect uptime and a completely broken agent. If your alerting is built only on infrastructure signals, silent failures will never trigger an alert.
- **Human review catches 70% of silent failures today.** This is the embarrassing baseline: most silent failures are caught by users noticing wrong answers, not by automated checks. If you're not building output-level validation, you're relying on your users to QA your agent.
- **A retry that succeeds may still be a failure.** If the agent retries a tool call, gets a different result, and continues, it may have silently resolved onto a degraded execution path. Log the full decision tree, not just the final state.
- **Model changes are silent quality events.** Upgrading to a new model version, switching API providers, or even a backend infrastructure change can alter response quality without any infrastructure signal. Evaluate outputs against ground truth after any model-level change.
- **The grader itself can fail.** If your validation agent uses the same model family as your execution agent, it may share blind spots. Use a structurally different validation path — different prompt, different model, or deterministic rule-based checks — to avoid correlated failures.
