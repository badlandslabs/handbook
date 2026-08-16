# S-2723 · The Intelligence Entropy Stack — When Your Agent System Degrades Without Breaking

Your agent worked for six weeks. Then, without a code change, a model update, or a new deployment, task accuracy started dropping — from 91% to 74% over twelve days. No errors. No alerts. Just quiet, monotonic degradation that your observability tooling missed because the system never crashed. This is not a memory leak. It is not a configuration drift. It is **Intelligence Entropy** — the inevitable accumulation of disorder in language-based autonomous systems.

## Forces

- **Disorder is intrinsic, not accidental.** LLM agent systems have 22 documented intrinsic properties (across six lifecycle layers: foundation semantics, inter-agent transmission, memory persistence, task execution, feedback correction, and systemic evolution) whose co-existence *logically entails* monotonic entropy increase. This is not a bug — it is a thermodynamic property. You cannot patch your way out of it.
- **Your monitoring is calibrated for the wrong failure mode.** 86% of agent failures are recoverable — but only if the system catches them. Traditional monitors look for crashes, timeouts, and exceptions. Entropy-driven failures produce none of these. They produce plausible-but-wrong outputs, gradual accuracy decline, and cross-session incoherence. 70% of entropy-driven failures in production studies were caught by human users, not automated systems.
- **The clock is always running.** Entropy accumulates as a function of interaction rounds: **S(t) = S₀ · e^(αt)**. The entropy constant α varies by architecture, but across 40,000+ controlled trials, it is never zero. A system that works on day one will be measurably different on day 47 — even with zero external changes.

## The Move

Intelligence Entropy is not a single failure mode — it is a *force* that manifests through five distinct failure classes (Liu, arXiv:2606.08162, June 2026, validated across 100,000+ production interactions):

| Class | Mechanism | Detectability |
|-------|-----------|---------------|
| A — Environment/platform quirks | Subtle platform behavior diverges from assumptions | Moderate |
| B — Design-assumption mismatches | Agent behavior drifts from designed contract | Low |
| C — Error swallowing/dilution | Errors occur but their signal attenuates through layers | Very Low |
| D — Chained hallucination/fabrication | Errors compound into confident false narratives | Near-zero |
| E — Operational omission/forensic blind spot | Required steps silently skipped | Low |

Class D — which Liu terms **fail-plausible** — is unique to LLM-based systems. The model does not merely fail to report an error; it actively *transforms the error into fluent, contextually appropriate, and false output delivered to the user*. This is gray failure escalated: the observer is not just blind, it is being fed a counterfeit signal by the failure itself.

### The PIG + ADE Countermeasure

Liu's PIG (Physical Integrity Gate) Engine and ADE (Agent Delivery Engineering) protocol suite provide the foundational countermeasure framework. The core principle: **replace probabilistic hope with deterministic constraint** at critical handoff points.

**PIG — Physical Integrity Gate.** A deterministic validation checkpoint that fires before state-crossing events (inter-agent handoffs, memory writes, tool invocations with side effects). Unlike LLM-native checks, a PIG is not probabilistic — it runs deterministic code against a typed schema. If the gate fails, the handoff is rejected, not smoothed over.

Key properties:
- Enforces typed contracts at agent boundaries (not advisory prompts)
- Validates state consistency before inter-agent transmission
- Integrates with immutable audit logs for forensic traceability

**ADE — Agent Delivery Engineering.** A protocol discipline that treats agent handoff as a governed delivery event, not a context concatenation. ADE specifies: delivery acknowledgment, content integrity verification, and non-repudiation at each agent boundary.

### Operational Entropy Management

Beyond PIG+ADE, practical entropy management requires three operational practices:

**1. Periodic State Snapshots.** Take a cryptographic hash of agent state at mission milestones. Compare hashes across sessions to detect silent divergence before it cascades. When hash(X) ≠ hash(X₀), investigate — even if outputs look correct.

**2. Entropy Budgeting.** Treat entropy like a resource: define an entropy budget per task or per session, and trigger a **state reset** (fresh context, re-initialized memory) when the budget is exhausted. This is the agentic equivalent of garbage collection — you are reclaiming coherent state, not fixing bugs.

**3. The Stability Coefficient.** Measure α empirically for your system. Run periodic diagnostic sessions (a known task with verifiable ground truth) at regular intervals. Track accuracy over time. When accuracy drops below a threshold, trigger a managed reset rather than waiting for the system to fail visibly.

## Receipts

**Entitlement verification failure (Class B):** A multi-agent pipeline ran reliably for 47 days. On day 47, Agent A failed to pass entitlement context to Agent B — no error message, no timeout, task "completed." Postmortem showed the entitlements had drifted from Agent A's learned context representation. PIG checkpoint at the handoff boundary would have caught the null field.

**Silent accuracy drift (Class D):** A customer-service agent chain showed 12% accuracy degradation over 3 weeks with no alerts. Logs showed HTTP 200 throughout. The model was converting tool failures into plausible敷衍 responses — users received confident confirmations of actions that had silently failed.

**Forgetful-Operator experiment (Khan, arXiv:2606.04056, June 2026):** 47 budget-overrun incidents from the Token Budgets catalog had a common structural pattern — the operator had no real-time visibility into cumulative token spend. By the time the anomaly appeared in the monthly bill, the damage was done. Treat token budget as a live metric, not an end-of-month report.

## Key References

- Liu, D. "Silent Failure in LLM Agent Systems: The Entropy Principle and the Inevitable Disorder of Autonomous Agents." arXiv:2606.08162 (cs.MA), June 2026. 40,000+ trials, 100,000+ production observations, 22 intrinsic properties, 6 lifecycle layers.
- Wu, W. "When Errors Become Narratives: A Longitudinal Taxonomy of Silent Failures in a Production LLM Agent Runtime." arXiv:2606.14589, June 2026. Eight-week field study, 22 documented incidents, five-class taxonomy.
- Khan, S. "Token Budgets: An Empirical Catalog of 63 LLM-Agent Budget-Overrun Incidents." arXiv:2606.04056 (cs.SE), June 2026.
- ADE Standard: github.com/ADE-standard/silent-failure
- Cross-reference: [S-2716 · Agent Failure-Interruption Stack](stacks/s2716-the-agent-failure-interruption-stack-when-your-agent-silently-burns-47k-in-a-loop.md) — behavioral angle on the same phenomenon
- Cross-reference: [S-2722 · Bounded Agentic Loop Stack](stacks/s2722-the-bounded-agentic-loop-stack-when-your-agent-will-keep-working-long-after-it-should-have-stopped.md) — loop bounds as entropy containment
- Cross-reference: [S-2682 · LLM Gateway Failure Atlas](stacks/s2682-the-llm-gateway-failure-atlas-when-your-proxy-looks-healthy-but-everything-is-broken.md) — infrastructure-layer silent failures
