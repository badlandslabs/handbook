# S-2324 · The Side-Effect Blindspot Stack — When Your Agent Shows Green and the User Got Nothing

Your agent run finished without errors. APM confirms: 200 OK, response time within SLO. But the user received nothing — the email wasn't sent, the Jira ticket wasn't created, the Slack message never arrived. The agent's last tool call succeeded, but the *delivery* step ran out of budget, timed out silently, or ran after the context window expired. Standard observability has no signal for this class of failure.

## Forces

- **The success trap.** APM and run-time dashboards measure whether the agent process completed, not whether the user's intended outcome was achieved. A run can complete all its work and die on the last step — still marking as "success" in every metric.
- **Agents own their own outcomes.** Unlike a REST endpoint that returns a value, an agent's output is often a side effect: a database write, an API call, an email, a file. The agent reports success when its own logic succeeds, not when the world changed.
- **Silent failures don't surface.** Tool calls return errors to the agent, but the agent may swallow or retry them in ways that mask the underlying failure. The agent runtime has no obligation to surface tool errors to the observability layer.
- **Long-running agents compound the problem.** An agent running for 30 minutes has made dozens of tool calls and written intermediate state. By the time a late failure occurs, you can't tell if earlier outputs are valid or if they've been superseded by a failed step.
- **Context budget exhaustion looks like success.** An agent that runs out of context tokens mid-delivery doesn't crash — it simply stops generating. The run ends, the traces look clean, and the user gets silence.

## The move

Instrument the gap between *run completion* and *outcome delivery* as a first-class observability signal, not an inferred one.

**1. Model every agent outcome as a delivery claim, not a run claim.**
Define the terminal side effect explicitly: "email was sent," "ticket was created," "file was written." Wire a delivery-verification check as the final span in every agent run. This is a separate call — it pings the external system (SMTP server, Jira API, S3) to confirm the write succeeded, independent of what the agent reported.

**2. Build a terminal-span instrument for every run.**
Add a structured `delivery_attempt` span as the last step regardless of agent outcome. It checks the claim: `was_email_sent(email_id)`, `ticket_exists(ticket_id)`, `file_exists(path)`. If this span fails, the entire run is marked failed — even if every prior span passed. This flips the burden: the run only succeeds if the delivery succeeded, not if the agent thought it succeeded.

**3. Tag traces with end-state classification, not just run-state classification.**
Label each trace with one of: `outcome_delivered`, `outcome_failed`, `outcome_unknown`. The `unknown` state is acceptable only during execution — every completed trace should exit with a definitive outcome tag. Untagged completed traces are themselves a failure mode to alert on.

**4. Separate timeout budgets from work budgets.**
Give the agent a `work_timeout` (how long it can think and act) and a separate `delivery_timeout` (how long the final delivery step gets). Protect the delivery step from being starved by upstream reasoning. Budget exhaustion should be caught at the `work_timeout` boundary and escalated before the delivery step runs.

**5. Capture the claim chain: what the agent tried to do vs. what actually happened.**
On every tool call, record both the agent's claim of success and the tool's actual response. Diff these at trace time. An agent that calls `send_email(to="user", body="...")` and treats `{"status": "queued"}` as success is wrong — it should treat `{"status": "delivered"}` as the only valid success signal.

**6. Route unknown outcomes to human-in-the-loop before they become incidents.**
Any trace that exits with `outcome_unknown` after a threshold (e.g., 5 minutes post-run) should create a human review task automatically. This closes the loop on silent failures by making a person responsible for deciding whether the outcome happened.

## Evidence

- **Engineering blog (Pazi):** Real incident — bug-triage cron with 300s timeout where ~75 seconds were eaten by bootstrap, leaving only ~15 seconds for tool calls. The cron completed "successfully" because the agent logic finished, but the GitHub issue creation was silently dropped. Solution: separate delivery-timeout from work-timeout, wire a GitHub API verification step as terminal span. — [blog.pazi.ai](https://blog.pazi.ai/silent-failure-modes-production-ai-agents)
- **Engineering blog (Tian Pan, 2026):** Identifies "confident errors" and "silent drifts" as the two failure modes standard monitoring misses. Emphasizes that traditional APM marks a request healthy when the LLM call completes, even if the response is wrong or the downstream write failed. — [tianpan.co](https://tianpan.co/blog/2025-10-17-llm-observability-production)
- **OpenTelemetry blog (2025):** Positions telemetry as a feedback loop for continuous agent quality improvement. Standardization via `gen_ai.*` semantic conventions enables vendor-neutral span attributes (model name, token counts, finish reason, tool name, tool arguments) that allow outcome signals to flow across tracing backends. — [opentelemetry.io](https://opentelemetry.io/blog/2025/ai-agent-observability/)

## Gotchas

- **The agent reports success on the tool call returning, not on the side effect completing.** Most APIs return 200 when a write is *accepted*, not when it's *effective*. The agent sees 200 and moves on. The delivery didn't happen.
- **Verifying delivery from inside the agent loop creates a circular dependency.** If the verification API call also runs through the agent, it can also fail silently. Keep delivery verification outside the agent's execution path — it should be a trusted infrastructure call, not an agentic one.
- **Sampling strategies that discard "successful" traces will lose your worst failures.** If you sample down to 1% of runs and your sample threshold is "no exception thrown," you'll keep almost all failures out of your trace store. Sample on `outcome_delivered=false` or on high-token-count traces (which correlate with looping or excessive tool use) instead.
- **Retries can hide delivery failures permanently.** If an agent retries a failed delivery call 3 times and only the last attempt is logged, you'll see one apparent success and never know the first two failed. Log each attempt distinctly, not just the final state.
