# S-844 · The Agent Incident Forensics Stack — When Your Agent Failed and You Can't Reconstruct Why

Your agent ran for eleven days. The API returned 200. No exceptions fired. A Slack message at 3 AM told you the bill hit $47,000. When you opened the trace log, you found a pile of LangSmith spans — full of partial outputs, ambiguous error codes, and no record of what the agent *thought* it was doing. You spent three days reconstructing the incident from fragments. An NTSB investigator would call this a black box that was never installed.

Agent incident forensics is the discipline of capturing structured, deterministic records of agent failures — not just logs, but a complete incident artifact that survives scrutiny from engineers, auditors, and regulators. The AgentIncident open specification (Apache 2.0, agentincident/agentincident on GitHub) defines the emerging standard: a JSON incident record that captures trace, fault class, dollar impact, and remediation chain.

## Forces

- **Agent behavior is non-deterministic and stateful.** The same input can produce different trajectories across runs. A raw transcript of *one* run is not enough — you need replayable evidence across the full decision path.
- **Agent failures are structurally ambiguous.** The agent didn't throw an exception — it made a sequence of rational-sounding decisions that happened to be wrong. Traditional postmortem fields (root cause, fix, prevention) don't map cleanly when the LLM was the proximate cause.
- **Dollar impact is estimated, not measured.** Most teams back into cost after the fact. Regulators and actuaries want quantification, not estimates.
- **Compliance now demands it.** The EU AI Act Article 11 requires technical documentation for high-risk autonomous systems. "We have logs" is not documentation. "Here is the incident.json" is.

## The move

### Capture: incident.json

The core artifact is a structured JSON record with five core fields:

```json
{
  "incident_id": "inc_2026_047_k",
  "trace": [
    {
      "seq": 1,
      "tool": "stripe.refund",
      "input": {"customer_id": "cus_9x2k", "amount": 4200},
      "output": {"status": "succeeded", "refund_id": "re_3f8k"},
      "ts": "2026-06-10T03:17:42Z",
      "hash": "sha256:a3f7c..."
    },
    {
      "seq": 2,
      "tool": "email.send",
      "input": {"to": "customer@example.com", "body": "Your refund has been processed."},
      "output": {"delivered": true},
      "ts": "2026-06-10T03:17:44Z",
      "irreversible": true
    }
  ],
  "fault_class": "TOOL_CAPABILITY_ERROR",
  "impact_usd": 18420.00,
  "remediation": ["action_item_1", "action_item_2"]
}
```

The `irreversible` flag on each trace step marks actions that cannot be undone — deletions, writes, payments, deployments. When reconstructing an incident, irreversible steps are where the forensics effort focuses first.

### Fault classification: know what kind of failure you had

AgentIncident defines a deterministic fault taxonomy — eight mutually exclusive classes that map to distinct remediation paths:

| Fault Class | Description | Remediation Path |
|---|---|---|
| `TOOL_CAPABILITY_ERROR` | Tool invoked correctly but produced unexpected/wrong output | Fix tool schema, add output validation |
| `TOOL_SCHEMA_ERROR` | Tool called with wrong arguments or wrong tool | Improve tool descriptions, add argument validation |
| `GOAL_DRIFT` | Agent pursued a different goal than requested | Tighten goal contract, add confirmation gates |
| `CONTEXT_OVERFLOW` | Agent ran out of context window mid-task | Increase budget, add compaction triggers |
| `PROVIDER_MODEL_CHANGE` | External model provider silently updated the model | Pin model version, add behavioral regression tests |
| `HALLUCINATED_CREDENTIAL` | Agent fabricated authentication details or API keys | Restrict credential visibility, validate before use |
| `PROMPT_INJECTION` | External input redirected agent behavior | Add input sanitization, capability gating |
| `LOOP_DETECTED` | Agent repeated the same tool call N times | Add loop guard, increase budget |

The taxonomy's value is determinism: two engineers reviewing the same incident.json should reach the same fault class. This closes the "ambiguous root cause" problem that plagues LLM-driven postmortems.

### Dollar impact: quantify before you estimate

Every trace step carries a `cost_usd` field. Sum the field across all steps to get the run cost. For incidents involving downstream financial harm (wrong refund, incorrect data write, unnecessary API calls), the `impact_usd` field captures total loss — not just token spend, but actual business impact.

```python
def compute_incident_impact(trace: list[dict], downstream_loss: float = 0.0) -> float:
    token_cost = sum(
        step.get("input_tokens", 0) * INPUT_PRICE
        + step.get("output_tokens", 0) * OUTPUT_PRICE
        for step in trace
    )
    return token_cost + downstream_loss
```

Teams who quantify impact in dollars find a surprising pattern: the cost of the agent run is usually a rounding error compared to downstream harm. The $47K agent bill gets attention; the $400K in incorrect refunds it caused is the real number.

### Instrument once: SDK integration

LangChain, CrewAI, OpenAI SDK, and Vercel AI all have AgentIncident integration examples. The instrumentation pattern is the same regardless of framework:

```python
from agentincident import AgentIncident

ai = AgentIncident(agent_id="support-triage-v3")

async def run_with_forensics(client, task):
    async with ai.incident_context() as ctx:
        result = await agent_loop(client, task)
        if result.get("status") == "failed":
            ctx.fault_class = classify_failure(result)
            ctx.impact_usd = compute_incident_impact(ctx.trace)
        return result
```

The `incident_context()` wrapper captures the full trace automatically — every tool call, every input, every output, every timestamp. On failure, it finalizes the record and writes `incident.json`. On success, the record is discarded unless the calling code explicitly saves it as a near-miss.

### The postmortem gets a new section

LLM-driven incidents need a section standard postmortem templates don't have: **the decision log**. Between each major action, record what the agent stated it intended to do, what it actually did, and what signal it acted on. This is not the trace — it's the agent's own reasoning, captured at decision time.

```markdown
## Decision Log

| Step | Stated Intent | Actual Action | Signal Source |
|------|--------------|---------------|---------------|
| 3 | "Refund $42 to customer" | Called stripe.refund($4200) | Tool description said "amount in cents" — agent misinterpreted |
| 5 | "Confirm refund sent" | Sent email to wrong address | Retrieved email from stale memory entry |
```

This section closes the accountability gap: when the regulator asks why the agent issued a $4,200 refund instead of $42, you have the agent's own words.

### Compliance: the artifact is the argument

For EU AI Act Article 11 documentation, the incident.json is the technical artifact. Five fields — trace, fault class, impact, remediation, and timestamp — demonstrate that you captured the failure, classified it, measured it, and closed the loop. That is the "technical documentation" requirement, fulfilled structurally rather than narratively.

## Receipt

> Receipt pending — 2026-07-09. AgentIncident is a live open-source project (agentincident/agentincident on GitHub, Apache 2.0) with SDK integrations documented at agentincident.com. Fault taxonomy verified against SPEC.md v0.1. The code examples are structurally consistent with the SDK patterns described in the AgentIncident start.md guide. A live receipt requires a running agent with instrumentation — deferring to the next session when a full agent loop can be exercised.

## See also

- [S-843 · The Agent Failure-Handling Stack](s843-the-agent-failure-handling-stack-when-the-agent-crashes-but-your-system-cant.md) — recovery patterns; this entry covers the forensic layer before recovery
- [S-655 · Silent Failure Detection in Agentic Loops](s655-silent-failure-detection-in-agentic-loops.md) — detection; forensics is the post-mortem layer
- [S-829 · The Eval Stack](s829-the-agent-eval-stack-when-task-completion-is-not-enough.md) — evaluation; forensics is the failure-specific complement
- [S-787 · Invisible Model Drift](s787-invisible-model-drift-the-silent-provider-update-pattern.md) — a specific fault class in the taxonomy above
