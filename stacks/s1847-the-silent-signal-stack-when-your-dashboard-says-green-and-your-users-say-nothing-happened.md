# S-1847 · The Silent-Signal Stack — When Your Dashboard Says Green and Your Users Say Nothing Happened

Your agent ran for 300 seconds. It logged no errors. It called every tool it planned to call. Your APM shows 100% success rate. Three users reported the task was never completed. The cron said it succeeded. The trace said it succeeded. The user got nothing.

This is the silent-signal problem: the most dangerous failures in production agent systems are the ones that look identical to success from every internal vantage point. APM was built for a world where exceptions are the failure signal and a green run means the user got served. Agents don't fit that world — and the gap between "trace success" and "user outcome" is where silent failures live.

## Forces

- **The agent's model of success diverges from the system's model.** Agents log success when they believe a task is complete. That belief is a probabilistic inference, not a verifiable proof. A timed-out API call, a silently dropped message, a tool that returned a 200 but did nothing — all of these produce confident success logs from an agent operating on incomplete state.
- **Standard APM only sees what throws an exception.** Error rates, latency histograms, and CPU saturation catch crashes. They do not catch behavioral regressions — a routing agent that has been sending tickets to the wrong queue for 72 hours, or a summary agent that stopped including attachments three days ago.
- **Trajectory volume buries signal.** A single agent session can produce hundreds of spans. Raw trace counts say nothing about whether the outcome the user needed actually occurred. You need a layer that asks: "Did the user get what they asked for?" not "Did the agent finish its run?"
- **Change velocity makes regression invisible.** Prompt updates, model swaps, and tool schema changes happen weekly in mature agent systems. Each change can silently shift behavior in ways that don't surface as errors but change what the agent actually does.

## The Move

Build a signal layer between agent traces and user outcomes. The core principle: **every agent run needs an outcome assertion, not just a completion status.** Instrument the seams where agent claims and system reality can diverge.

### 1. Cron Delivery Assertion — Prove the User Received the Artifact

The problem: your cron framework only knows what the agent reported per-run, not what the user received. A 300-second timeout that eats 75 seconds on bootstrap can silently consume 25% of your budget and produce zero user-visible output.

```
Cron assertion pattern:
  before: record expected_artifact (e.g., "email sent to user@example.com")
  after: verify_artifact_exists(email_log, S3 object, DB record, Slack message)
  if missing: ALERT — agent completed but delivery failed
  attach: delivery_proof_id to trace span
```

The assertion runs AFTER the agent believes it's done. It doesn't care whether the agent logged success. It checks whether the artifact the user needed is actually where it should be.

### 2. Tool-Call Effect Verification — Prove the Side Effect Actually Happened

The problem: a tool call returning 200 OK does not mean the operation produced the intended state change. The network dropped after the server logged "OK." The file was written to a temp directory that gets cleaned up. The API accepted the payload but the downstream system silently dropped it.

Wrap every state-mutating tool call in an effect verification:

```
Tool wrapper:
  tool_result = original_tool(args)
  verify_effect(tool_result, expected_state)
    e.g., GET the resource after POST to confirm it exists
    e.g., query the database after write to confirm record appears
    e.g., check webhooks after API call for downstream event
  if effect missing: flag span with `outcome=incomplete`
  attach verification_proof to span
```

The agent's tool result and your verification result are independent signals. When they diverge, that's your alert trigger.

### 3. Inbound Signal Monitor — Catch What Never Reached the Agent

The problem: a routing decision made before the agent bootstraps can silently discard inbound work. The agent never saw the request, so the agent never failed — but the task was dropped.

```
Inbound monitor:
  on inbound request received:
    emit span: `inbound.received` with request_id
  on agent startup:
    emit span: `agent.bootstrapped` with request_id
  if agent.bootstrapped missing within SLA:
    ALERT — inbound request was received but never reached agent
  attach request_id correlation to full trace
```

This catches routing misconfigurations, queue consumer failures, and load-balancer drops that never surface as agent errors.

### 4. Budget Tracker Span — Know What Bootstrap Actually Costs

The problem: agent initialization is invisible in standard metrics. Loading a 200K-token context, bootstrapping a runtime, and warming up a model can consume 60–80 seconds before the first user-meaningful action. In a 300-second budget, that's 25%+ consumed before work starts.

```
Budget span hierarchy:
  session.init:     bootstrap + context load
  session.tools:    MCP discovery + schema parsing
  session.think:   first model call
  session.work:     user-meaningful actions  ← what you actually measure
  session.deliver:  result transmission + verification
  
  alert if session.work < 20% of total session time
```

Use OpenTelemetry GenAI semantic conventions (genai.* spans: `genai.choice`, `genai.tool_call`, `genai.output`, `genai.usage`). Attach session phase spans so your cost dashboards show where time and tokens actually went, not just total run cost.

### 5. Behavioral Grader Over Traffic — Detect the Regression APM Cannot See

The problem: a routing agent that started sending invoices to the wrong queue three days ago has zero error signals. Every span looks normal. Every tool call succeeded. Users are the only ones who know.

Standard observability counts: how many spans, how many errors, how much latency. Behavioral grading counts: did the agent do the right thing?

```
Grader over traffic (not traces):
  sample_rate: 5-10% of production sessions
  for each sampled session:
    grader_prompt: "Given the user's request and the agent's final output,
                    did the agent accomplish the stated goal?
                    Rate: complete / partial / failed / unknown.
                    If failed, describe what went wrong."
    attach grader verdict + reasoning to session span
    if grader verdict == failed AND no error span in session:
      → SILENT FAILURE — emit alert with session trace
      → increment silent_failure_counter
```

This catches the failure mode where the agent completes without throwing an exception but delivers the wrong result. Graders over raw traffic (not manually selected traces) catch regressions that span teams never notice because nobody is looking at those specific session types.

### 6. Timeout Surface — Make Timeouts Observable

The problem: a timeout looks like a clean exit to your observability stack. The agent hit its budget and returned what it had. But the user expected a complete answer and received a partial one with no indication it was partial.

```
Timeout handler:
  on budget_exhausted:
    if partial_state_exists:
      emit span: `outcome=partial` with state_hash
      attach: what_was_completed, what_was_abandoned
      ALERT with session trace attached
    else:
      emit span: `outcome=timeout_empty`
      ALERT — agent timed out with nothing to show
```

The key is treating a partial timeout as a different outcome category than a clean completion. Don't conflate them. A partial timeout that achieved 80% of the goal is not a success — it's a conditional success that should be routed to a retry or escalation path.

## Putting It Together

The silent-signal stack adds four layers above standard observability:

| Layer | Signal | Detects |
|---|---|---|
| Delivery assertion | Artifact exists post-run | Cron success / no delivery |
| Effect verification | Tool claim vs. actual state | Tool 200 / effect missing |
| Inbound monitor | Request ID correlation | Dropped requests |
| Behavioral grader | Outcome correctness | Silent behavioral regression |
| Budget tracker | Phase-level time attribution | Bootstrap budget waste |
| Timeout surface | Outcome categorization | Partial completions as success |

Every span in your agent trace should carry an `outcome` attribute: `complete`, `partial`, `failed`, or `unknown`. Don't let your observability layer treat `no exception` as a proxy for `task accomplished`.

The discipline is straightforward: **treat user outcomes as first-class observable signals**, not derived inferences from agent-reported status. When the dashboard says green and users say nothing happened, you have a measurement gap — and this stack closes it.
