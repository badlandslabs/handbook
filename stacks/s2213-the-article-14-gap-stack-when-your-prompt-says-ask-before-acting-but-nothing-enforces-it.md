# S-2213 · The Article 14 Gap Stack — When Your Prompt Says "Ask Before Acting" but Nothing Enforces It

Your agent's system prompt includes "always request human approval before executing financial transactions." You have an EU AI Act Article 14 compliance posture — a document. Munich Re's aiSure underwriting team asks for evidence of your oversight capability. You show them the prompt. They decline to cover you. Your agent calls the payment API anyway, because the LLM interpreted "request" as optional, and nothing at the enforcement layer existed to stop it.

This is the Article 14 gap: the EU AI Act requires high-risk AI systems to support genuine human oversight at runtime. Most enterprises have implemented it as a prompt instruction. These are not the same thing.

## Forces

- **Article 14 is not a documentation requirement — it is an architectural one.** The regulation requires deployers to demonstrate that a qualified natural person can, at runtime, understand outputs, recognize automation bias, intervene, override, and halt the system safely. A prompt instruction satisfies none of these. The enforcement must exist outside the model's reasoning path.
- **Prompt-layer HITL degrades under production conditions.** Token pressure, context switching, model version changes, and adversarial inputs all degrade the model's willingness or ability to surface "should I ask?" The layer enforcing the halt must be non-model.
- **82% of enterprises have agent deployments their security teams don't know about.** Before you can demonstrate Article 14 compliance, you need a complete registry of agents. Most organizations don't have one.
- **Insurers are already underwriting on halt-capability evidence.** Munich Re's aiSure product, Zurich's agentic AI coverage, and Lloyd's syndicates all treat runtime halt capability as an underwriting criterion — not a prompt, not a policy doc, but evidence of a tested, auditable stop mechanism.
- **The safe-stop requirement is an operational SLA, not a UI feature.** Article 14(4) requires the ability to shut down the system "safely," meaning: with state preservation, transaction atomicity, and documented decision logs. A Ctrl+C is not compliance.

## The move

**1. Separate the oversight contract from the model.** Human approval gates are infrastructure, not prompts. Implement them as an explicit orchestrator layer that intercepts actions matching risk criteria (financial, data-deletion, external-API call, deployment trigger) and blocks execution until a named, logged approval event occurs.

```
[Agent decides: call_payment(to=vendor, amount=5000)]
  → Orchestrator intercepts (action matches "financial-risk" rule)
  → Action suspended; event written: {action, rationale, risk_class, timestamp}
  → Human reviewer notified via ticketing/slack/email
  → Reviewer approves/rejects → event logged with outcome + reviewer identity
  → Action proceeds or is cancelled, atomically
```

**2. Implement the five Article 14 capabilities as infrastructure, not intentions.**

| Capability | Infrastructure implementation |
|---|---|
| Understand & monitor | Structured decision logs: agent state snapshot at every action boundary, stored outside context window |
| Recognize bias | Automated flagging: deviation from established action pattern triggers review queue |
| Intervene | Real-time handoff: reviewer can pause agent, inject context, redirect task mid-execution |
| Override | Approval/rejection with documented rationale; agent receives the override as a new context signal |
| Safe-stop | Graceful shutdown: preserve conversation state, rollback uncommitted actions, emit post-mortem log |

**3. Build the audit artifact, not just the control.** Article 14 requires that oversight personnel be "qualified" and that their competence be documented. Each approval event must include: reviewer identity, their documented training record, timestamp, action taken, rationale, and the agent's reasoning trace that triggered the gate. This is the evidence package insurers and regulators will request.

**4. Add a halt-capability test to your agent deployment checklist.** Run it quarterly: trigger the risk-action path, attempt halt at each gate, confirm state preservation and log completeness. Treat the result as a compliance artifact, not a test artifact.

**5. Close the shadow IT registry first.** Article 14 compliance is impossible to demonstrate if you don't know which agents exist. Build the registry (S-1041 covers this) before assuming your compliance posture is complete.

## Receipt

> Verified 2026-08-06 — Researched EU AI Act Article 14 enforcement requirements across Zylos Research (2026-05-01), KLA Digital (2026-07-27), agentliability.eu (2026-04-25), Cordum EU AI Act Guide (2026), Gartner 2026 AI Agent Hype Cycle, and 8 additional primary sources. Core claim confirmed: prompt-layer HITL does not satisfy Article 14; runtime enforcement infrastructure is required. Insurer underwriting criteria (Munich Re aiSure Schedule D, Lloyd's aiSure) independently confirm this distinction. Article 14 deadline: Annex III high-risk enforcement now December 2, 2027 under Digital Omnibus; Articles 9/12/13/14 unchanged.

## See also

- [S-1458 · The Policy-Kernel Stack](../stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — policy enforcement vs. policy documentation
- [S-1041 · The Agent Shadow IT Stack](../stacks/s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — discovering and registering agents before compliance is possible
- [S-2212 · The Trajectory Testing Stack](../stacks/s2212-the-trajectory-testing-stack-when-your-agent-passes-the-output-eval-but-fails-in-production.md) — testing the execution path, not just the output
