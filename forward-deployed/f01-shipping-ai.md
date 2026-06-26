# F-01 · Shipping AI

Getting an AI feature from "it works in my demo" to production with real users, real data, and real stakes.

## Forces
- Demos are cherry-picked; production is everything else
- Model outputs are probabilistic — the same input can yield different outputs
- Users trust AI outputs implicitly until something goes wrong, then they distrust everything
- Rollback is harder than rollback for deterministic code: you can't undo a bad AI email sent to 10,000 users

## The move

**The production checklist:**

### Before launch
- [ ] Define what "correct" looks like — write an eval suite before writing the feature
- [ ] Run the feature against 100 real examples (not demo inputs) and measure failure rate
- [ ] Set hard guardrails: max tokens, timeout, retry budget, fallback behavior when model is down
- [ ] Log every call (see [W-04](../workspace/w04-observability.md))
- [ ] Human review gate for high-stakes outputs (emails, contracts, financial advice)
- [ ] Communicate AI involvement to users — transparency reduces backlash on failure

### Rollout strategy
- Start with internal users or a small percentage of traffic
- Shadow mode: run the AI in parallel with the existing system, compare outputs without exposing AI output to users
- Canary: expose AI output to 1–5% of users, monitor error rate and user feedback before expanding
- Full rollout: only after canary metrics are acceptable

### When to add human-in-the-loop
- Any output that triggers an irreversible action (payment, message send, deletion)
- Regulated domains: medical, legal, financial
- Low-confidence outputs — add a confidence threshold below which the system escalates to human

## Receipt
> Receipt pending — 2026-06-25. Checklist synthesized from production deployment patterns common in the field. Verify against your specific regulatory and operational context.

## See also
[F-02](f02-evaluation-at-scale.md) · [F-03](f03-failure-modes.md) · [W-04](../workspace/w04-observability.md)

## Go deeper
Keywords: `shadow mode deployment` · `canary release` · `LLM eval` · `human-in-the-loop` · `AI governance` · `EU AI Act Article 14`
