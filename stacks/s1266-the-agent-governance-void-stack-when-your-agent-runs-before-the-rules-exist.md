# [S-1266] · The Agent Governance Void Stack

When your agent runs before the rules exist.

## Forces
- Agents fail **plausibly** — confident, articulate, wrong decisions that scale silently until a human notices. Unlike traditional software (crash → visible), agents can produce entirely plausible failures at volume.
- Enterprise governance is built for deterministic systems. Agents are non-deterministic. The governance framework built for your payment processor cannot be copy-pasted onto an autonomous agent.
- The pilot-to-production gap: 67% of pilots report gains; only 10% successfully scale to production. The gap is structural, not technical.
- Gartner projects 40% of agentic AI projects will be cancelled by end of 2027 — not because agents fail at their jobs, but because organizations cannot prove they are good at them.

## The Move

The minimum viable governance layer for a production agent has five components. You need them *before* go-live, not after the first incident.

### 1. Decision Audit Trail
Every agent decision that touches sensitive data or consequential actions must be logged with: timestamp, input snapshot, reasoning trace, tool calls made, output, and the human authority who approved or delegated this action class.

This is not request-level logging — it is *decision-level* logging. The same request can produce dozens of decisions. Log the decisions, not the requests.

```
decision_id | agent_id | action_class | input_hash | reasoning_trace | output_hash | authority_id | timestamp
```

Without this, post-incident review is reconstruction, not investigation.

### 2. Escalation Paths (not escalation *policies*)
Define what happens when the agent reaches its confidence threshold or encounters an unmapped situation class. The answer "a human looks at it" is not a path — it is a hope.

A real escalation path specifies: which human or team, within what latency bound, with what context window provided to the reviewer, and what state the agent holds during the review pause.

Agents that hit an unknown situation and continue anyway are not autonomous — they are ungoverned.

### 3. Decision Override Capability
Any agent action that has already executed (tool calls, messages sent, records modified) must have a corresponding compensating action defined *at design time*, not discovered at incident time.

Compensating actions do not need to be automatic. They need to be *defined*. A human can invoke them. But you cannot invoke a rollback you never designed.

### 4. Action Class Authorization Matrix
Before deployment, classify every action class the agent will perform (read-only query, internal write, external API call, data deletion, financial transaction, etc.) and explicitly authorize each class for each agent role.

The authorization matrix answers: "Which agent, performing which action class, under which conditions, requires which human approval — pre-action or post-action?"

Agents operating without this matrix are operating without a security policy.

### 5. Compliance Reporting Gate
Define the compliance reports the agent must be able to generate on demand: decision volume by class, error rates by action type, escalation frequency, override/compensation events, and authority delegation chain.

If your compliance team cannot generate these reports from the audit trail, the audit trail is insufficient.

## The Structural Insight

The governance void is not a technology problem. It is a sequencing problem: organizations deploy agents, then discover they needed the governance layer first.

The fix is not better agents. The fix is: do not move an agent from pilot to production until the five governance components above are instrumented and tested — not just documented.

## Distinguishing from Related Patterns
- **S-1265 (Kill Switch):** Kill switch is the emergency stop. Governance void is the policy layer that makes the kill switch meaningful — without an audit trail, the kill switch fires and you still cannot explain what happened.
- **S-1264 (Execution Version Control):** Version control manages the agent's artifacts. Governance manages the agent's authority. Different failure modes, different mitigations.
- **S-1256 (Scope Attenuation):** Scope attenuation prevents agents from escalating permissions. Governance void covers the broader question of what to do once an agent acts — audit, override, escalation.
