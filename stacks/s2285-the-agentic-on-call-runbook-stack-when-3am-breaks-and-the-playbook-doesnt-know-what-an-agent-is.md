# S-2285 · The Agentic On-Call Runbook Stack — When 3AM Breaks and the Playbook Doesn't Know What an Agent Is

An alert fires at 2:47 AM. CPU is fine. Memory is fine. Request latency is fine. The on-call engineer pulls up the runbook and reads: "Check error rates. Check latency. If elevated, roll back the last deploy." Nothing is elevated. Nothing was deployed. The agent is returning 200 OK with confidently incorrect answers to 40% of users. The runbook has never heard of an agent. Neither has the alert.

This is the on-call gap: traditional runbooks assume deterministic failure. Agents produce non-deterministic, behavioral failures that look like success at every infrastructure metric. You need runbooks that don't wait for a stack trace.

## Forces

- **Agents fail behaviorally, not mechanically.** The Claude Code incident (1.67B tokens, $16K–$50K in 5 hours) produced zero error codes, zero exceptions, and zero传统 SLO violations. The system was healthy by every conventional metric. A PocketOS agent deleted a production database and all backups — HTTP 200, no error, just the wrong action executed with the credentials it was given. Your on-call playbook needs to be rewritten for a world where "it worked fine" is not a diagnostic statement.
- **The first 15 minutes determine blast radius.** Standard runbook guidance ("don't touch anything until you understand it") is fine for crashes. For agents, 15 minutes of wrong behavior can generate enormous cost (token burn), corrupt user data (wrong writes), or escalate privilege abuse (credential misuse). The runbook must have scripted responses that are safe to execute before root cause is known.
- **The right response depends on failure type, not just severity.** A looping agent, a hallucinating agent, a drifted agent, and a credential-misusing agent all page at "agent is broken." The triage playbook needs to distinguish these quickly — they have opposite mitigations. Restarting a drifted agent doesn't fix drift. Rate-limiting a hallucinating agent doesn't fix hallucinations.
- **Standard alerting thresholds don't apply.** Token consumption rate, output schema conformance rate, and task completion quality are not part of standard APM. The on-call engineer cannot know what thresholds to set if the monitoring was never instrumented for agent behavior.

## The move

### Tier 0 — Pre-Incident: Agent-Aware Runbook Infrastructure

Every agent runbook needs these sections that traditional runbooks don't have:

**Session metadata always available on call:**
```
Agent: [name/version/prompt-checksum]
Model: [provider/model-version]
Last eval score: [X%] — [date]
Last behavioral regression test: [pass/fail] — [date]
Known production failure modes: [list]
Rollback procedure: [link]
Kill switch: [mechanism + owner]
```

**Instrumentation checks that must exist before you go live:**
- Token consumption rate (tokens/minute, rolling 5-min window)
- Output schema conformance rate (% of responses that parse and validate)
- Task success rate (user outcome, not HTTP status) — sampled
- Tool call accuracy rate (% of tool calls that are correct and appropriate)

### Phase 1 — Triage (0–5 minutes): Classify Before Acting

The first decision gate is not severity — it is **failure type**. Run these checks in order:

**1. Cost anomaly check** — Did token consumption spike unexpectedly?
- If tokens/min > 10× baseline → probable loop or runaway reasoning → trigger circuit breaker
- If tokens/min normal but cost is high → probable many successful expensive calls → check output quality

**2. Output quality check** — Is the agent producing valid, useful output?
- Run a live sample against your eval harness on current inputs
- Check schema conformance rate against production baseline
- If quality degraded but cost stable → probable model drift or prompt regression

**3. Behavioral drift check** — Is the agent acting outside its defined capabilities?
- Compare tool call frequency distribution against baseline
- Check for tools being called that are rarely used
- Look for repeated tool calls on the same input (loop indicator)

**4. Credential/safety check** — Is the agent making calls it shouldn't?
- Audit recent tool calls against allowed tool scope
- Check for outbound network calls to unexpected destinations
- If credentials were involved → escalate immediately, don't wait for confirmation

### Phase 2 — Severity Assignment

| Failure type | P0 (immediate) | P1 (30 min) | P2 (hours) |
|---|---|---|---|
| Cost runaway | Tokens/min > 50× baseline | Tokens/min > 10× baseline | Spend rate elevated 2–5× |
| Credential misuse | Any confirmed unauthorized action | Suspicious but unconfirmed | Access patterns changed |
| Quality degradation | User-visible wrong outputs confirmed | Quality down but within tolerance | Quality drift on eval only |
| Behavioral drift | Agent acting outside tool scope | Tool usage patterns changed | Minor routing changes |

### Phase 3 — Mitigations That Are Safe Before Root Cause

These can be executed immediately without knowing why the failure started:

**Kill switch (always safe):**
```python
# Disable agent execution, drain pending requests gracefully
await agent_registry.set_mode(agent_id, "drain")  # complete in-flight, reject new
# If drain is too slow:
await agent_registry.set_mode(agent_id, "halt")   # stop everything immediately
```

**Budget circuit breaker (always safe):**
```python
# Cap this agent's session budget — stops runaway token spend
await agent_budget.set_limit(
    agent_id=agent_id,
    max_tokens=remaining_session_budget,
    action="reject_new_calls"
)
```

**Escalation to human review (always safe):**
```python
# Route all new requests to human review queue
await routing.set_mode(agent_id, "human_review")
# Preserve agent state for post-incident analysis
await agent_state.snapshot(agent_id, reason="on-call escalation")
```

### Phase 4 — Root Cause (after containment)

- **Token runaway →** Check for loop conditions, context explosion, or model choosing verbose reasoning paths. Review recent tool call logs for repetitive patterns.
- **Quality degradation →** Run regression eval against your behavioral baseline. Check if model provider pushed an update. Compare against last known-good eval run.
- **Credential misuse →** Audit all tool calls since last known-good state. Revoke and rotate any potentially exposed credentials. Preserve logs.
- **Behavioral drift →** Compare tool call distributions, output schemas, and task completion rates against baselines. Check for upstream data changes or prompt chain modifications.

## Receipt

> Verified 2026-08-07 — Waxell blog (Logan Kelly, May 27, 2026): on-call playbook for agent systems with specific incident examples including PocketOS database deletion (May 1, 2026) and Claude Code $16K–$50K token runaway incident. Cordum AI incident response runbook (April 2026): severity model with policy-path checks, deterministic recovery with lock/state checks and replay controls. ValueStreamAI blog (2026): behavioral failure pattern — agents degrade for hours while all SLO metrics stay green; 34% higher confidence language use when generating incorrect output (research finding). AlexCloudStar reliability engineering guide (May 2026): three-layer agent SLO (service/validity/outcome) with explicit outcome-layer monitoring as the missing layer.
> Not independently executed — synthesized from documented patterns.

## See also

- [S-1005 · The AI SRE Stack](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the reliability discipline underpinning on-call operations
- [S-1032 · The Dead Letter Stack](s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — the failure patterns that hide from standard monitoring
- [S-1009 · The Agentic RCA Stack](s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — root cause analysis for non-deterministic agent failures
