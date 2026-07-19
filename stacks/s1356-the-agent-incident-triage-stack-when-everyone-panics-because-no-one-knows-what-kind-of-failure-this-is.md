# S-1356 · The Agent Incident Triage Stack

When you reach for this: Production is on fire, nobody knows what kind of agent failure they're in, the kill switch hasn't been pressed yet, and the incident channel has 14 people arguing about whether this is a prompt regression or a tool outage or a model degradation or a memory poison. The fix: a triage stack that classifies failure shape before prescribing response.

## Forces

- **Agents fail in distinct shapes that require opposite responses.** A loop needs a hard stop. A wrong-answer regression needs a kill switch + rollback. A tool outage needs retry logic. A memory poison needs session flush. Treating all agent failures the same — "restart it" — is how a 30-second incident becomes a 4-hour outage.
- **The kill switch is under-used because teams haven't classified the failure.** Most teams have an emergency kill switch for their agent, but they hesitate to use it because they don't know if it's a "real" incident or a transient issue. The cost of waiting is almost always higher than the cost of stopping.
- **Agent forensics require three parallel traces nobody collects.** Traditional incidents: check logs. Agent incidents: you need the intent log (what the agent decided to do), the execution log (what actually happened), and the state log (what the world looks like after). Most teams have none of these at incident time.
- **40–60% of on-call burden for agent-heavy systems comes from agent-specific failures with known fixes.** The gap isn't knowledge — it's that the fixes live in someone's head, not in a playbook.

## The move

### Step 1 — Classify the failure shape (first 60 seconds)

Don't reach for a fix. Name the failure type. Four shapes, each requiring a different response:

| Failure Class | Symptom | Response Priority |
|---|---|---|
| **Loop/Burn** | Token usage spiking, repeated similar tool calls, no forward progress | Hard stop + step limit |
| **Regression** | Agent producing wrong but plausible outputs, 200 OK throughout | Kill switch + rollback to prior prompt/model version |
| **Tool/Dependency** | Specific tool calls failing consistently, agent retrying or giving up | Circuit break that tool, route around |
| **Memory Poison** | Agent acting on corrupted/influenced context, behavior changed mid-session | Flush session, invalidate affected memory entries |

The classification question: *is the agent failing to complete, failing correctly, or completing incorrectly?* Completion correctness is the most dangerous because it looks healthy.

### Step 2 — Kill switch (first 90 seconds for P0/P1)

For active-harm incidents (unauthorized writes, data exfiltration, dangerous outputs being delivered):

1. **Activate kill switch** — stop agent from processing new requests. This is always step one. Do not investigate while the agent is still running.
2. **Scope the blast** — check how many requests were affected before the kill. Agent blast radius compounds: one poisoned session can corrupt shared memory, which poisons downstream agents, which write bad data.
3. **Preserve forensics** — snapshot current session state, tool call logs, and memory contents before any rollback. Agent state is ephemeral; you lose it when you reset.

```
# Kill switch activates two things simultaneously:
# 1. Agent processing halt (new requests queue or 503)
# 2. Execution guard (in-flight tool calls complete or abort based on risk level)
```

### Step 3 — Assemble the forensics trident

For every agent incident, collect three traces in parallel:

- **Intent trace:** What did the agent decide to do? (model input/output pairs, tool call decisions, reasoning steps)
- **Execution trace:** What actually happened? (tool dispatch logs, API responses received, write confirmations)
- **State trace:** What is the world state now? (database writes, external API calls made, memory contents)

The gap between intent and execution reveals tool-layer failures. The gap between execution and expected state reveals memory/state corruption. Most root causes live in one of these gaps.

### Step 4 — Run the appropriate recovery playbook

**Loop/Burn recovery:**
- Hard stop with step-count enforcement (cap: 50 steps default, configurable per task type)
- Enable cost circuit breaker: auto-pause if token spend exceeds 3× task-type baseline
- Replay with step-limit + progress checkpointing enabled
- Identify loop trigger: check for recurring tool pattern (same tool called 3+ times with similar params = loop condition)

**Regression recovery:**
- Identify the prompt/model/config change that introduced regression
- Roll back to last known-good version tag
- Re-run eval on affected task types before re-enabling
- Check eval set: if eval passed but production regressed, the eval set is stale — update it

**Tool/Dependency recovery:**
- Isolate the failing tool: mark unavailable, return explicit error to agent
- Agent should gracefully degrade (skip, use alternative, ask for clarification)
- If no graceful degradation: pause task, surface error, do not hallucinate a workaround
- Verify recovery: re-enable tool only after confirmed fix, not after assumption

**Memory Poison recovery:**
- Flush all affected session memory (not just the corrupted entries — poison spreads via associative retrieval)
- Check the poison source: was it retrieval (RAG false positive), tool output (bad API response), or cross-session contamination (shared memory corruption)?
- Re-issue affected tasks from clean state
- For cross-session poison: audit all agents reading from the affected memory store

### Step 5 — Post-incident: close the playbook loop

The incident isn't over when the agent restarts. Agent incidents have a habit of recurring because the fix was in infrastructure, not in the agent definition:

- Document the failure class and recovery in the incident playbook registry
- Add the failure shape to your agent failure mode taxonomy (S-395)
- If the failure was undetected for >1 hour: add a detection rule — agent incidents are won or lost by dwell time
- If the kill switch wasn't pressed fast enough: review the classification criteria and make the activation threshold clearer

## Receipt

> Verified 2026-07-19 — Framework synthesized from: niuexa.ai AI Agent Incident Response Runbook (severity classification and P0/P1/P2 structure), Agentbrisk.com real-incident analysis (refund agent $1.2M exposure, e-commerce $230K product repricing), iamstackwell.com incident triage approach (failure shape classification, forensics trident concept), Anfloy.com multi-agent failure modes (Gartner 1,445% multi-agent inquiry surge, 40% pilot failure rate), Zylos.ai 2026 research (42% specification failures, 37% coordination, 21% verification gaps in multi-agent deployments). Specific playbook steps are informed synthesis from these sources; adapt to your team's risk tolerance and agent autonomy level.

## See also

- [S-395 · Agent Failure Mode Taxonomy](/stacks/s395-agent-failure-mode-taxonomy.md) — the classification taxonomy this playbook references
- [S-370 · Agent Chaos Engineering](/stacks/s370-agent-chaos-engineering-fault-injection-testing.md) — fault injection to find failure modes before production does
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the reliability discipline that makes incident response faster and less chaotic
- [S-1335 · Blast Radius Formula](/stacks/s1335-the-blast-radius-formula-stack-when-a-single-agent-can-take-down-your-entire-infrastructure.md) — quantifying and containing blast radius, the primary damage-control lever
