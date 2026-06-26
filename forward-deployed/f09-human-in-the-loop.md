# F-09 · Human in the Loop

Putting a person at the right checkpoints in an autonomous agent — the safety mechanism the rest of the book keeps pointing to ([F-01](f01-shipping-ai.md), [F-06](f06-agent-sandboxing.md), [S-15](../stacks/s15-browser-computer-use-agents.md), [S-19](../stacks/s19-agent-loop.md)). Controlled autonomy, not full autonomy.

## Forces
- Full autonomy is premature for high-stakes actions; a wrong irreversible step can't be undone
- Too many approvals kill the efficiency that made the agent worth building
- The model's own confidence is an unreliable trigger — it's systematically overconfident
- The human side fails too: approval fatigue and automation bias turn reviewers into rubber stamps

## The move

- **Match three modes to risk.** *Pre-action approval* (human signs off before the agent acts) for irreversible/high-impact moves; *risk/confidence escalation* (runs autonomously, halts only when a risk signal fires) for the middle; *post-action review* (acts, then logs for audit/sampling) for cheap, reversible work. Most production systems run all three.
- **Encode the non-negotiable list up front.** Production deploys, external communications, payments over a threshold, data deletion, and privilege changes always need human sign-off — regardless of claimed confidence. The *designer* sets these boundaries; never let the agent decide its own.
- **Don't trust the confidence number alone.** RLHF models are miscalibrated (a claimed 90% can be ~75% actual), and error compounds across a chain. Layer signals — risk tier, irreversibility, financial cap, out-of-distribution detection — on top of confidence.
- **Never deadlock on a human.** Every pending approval needs a timeout that falls back to a safe default, an alternate reviewer, or a queue. Persist durable state so the loop ([S-19](../stacks/s19-agent-loop.md)) pauses and resumes cleanly.
- **Design for the reviewer, not just the agent.** Escalate only high-value decisions, with real context, or fatigue collapses the whole control. In the EU, [Article 14](https://artificialintelligenceact.eu/article/14/) makes demonstrable human oversight a *design* requirement for high-risk systems (August 2026 enforcement).

## Receipt
> The three approval modes (pre-action / escalation / post-action) and the always-approve action categories are the 2026 consensus across HITL design writeups. EU AI Act [Article 14](https://artificialintelligenceact.eu/article/14/) is primary: human oversight is a design requirement scaled to autonomy, requiring the ability to understand, intervene, and halt; high-risk-system enforcement lands August 2026. The "claimed 90% ≈ ~75% actual" miscalibration and chain-compounding figures are illustrative from production-overconfidence analyses — directional, not measured constants; the "$100 / 30-minute" thresholds are one protocol's defaults, not a standard. Verified 2026-06-25; not independently reproduced here.

## See also
[S-19](../stacks/s19-agent-loop.md) · [F-15](f15-durable-execution.md) · [F-01](f01-shipping-ai.md) · [F-04](f04-guardrails.md) · [F-06](f06-agent-sandboxing.md)

## Go deeper
Keywords: `human in the loop` · `HITL` · `human on the loop` · `approval gate` · `escalation` · `confidence calibration` · `automation bias` · `EU AI Act Article 14` · `kill switch`
