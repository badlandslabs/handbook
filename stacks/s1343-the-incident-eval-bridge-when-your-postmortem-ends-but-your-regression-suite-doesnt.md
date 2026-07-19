# S-1343 · The Incident-Eval Bridge — When Your Postmortem Ends But Your Regression Suite Doesn't

The incident is closed. The rollback worked. The postmortem doc is written. Three weeks later, the same failure mode surfaces again on a different input — because nobody added it to the eval suite. Every production failure that doesn't produce a regression case is a failure waiting to repeat.

The Incident-Eval Bridge is the practice of converting confirmed production failures into structured eval cases as part of incident closure. It closes the loop between what your agent did wrong and what your eval suite tests for.

## Forces

- **Every closed incident is an untested failure mode.** Axis Intelligence (Apr 2026) documented 187 verified production incidents; 38% had no detection mechanism at all. But even the incidents that were caught often weren't converted into evals — the team patched the symptom and moved on.
- **The postmortem ends; the regression suite doesn't.** Incident timelines compress under pressure. The instinct is to close the ticket and return to feature work. Without a forced bridge to the eval suite, this instinct wins every time.
- **One confirmed case is worth more than 100 synthetic ones.** Real production inputs reveal failure modes that synthetic cases never surface. The question is whether you're capturing them before they're buried in incident history.
- **Eval additions require the same discipline as code.** A loose "add this to the eval suite" request in a postmortem action item never gets executed. The bridge must be structural — a step in the incident process, not a suggestion.

## The Move

The bridge has three components:

**1. Capture at containment.**
The moment a failure is confirmed, extract the triggering input and the wrong output. Store them as a candidate eval pair before the system state changes. Don't wait for postmortem — by then, logs may be aged out and context is lost.

```python
# Add to incident response runbook at containment step
def capture_incident_eval_pair(
    incident_id: str,
    trigger_input: str,
    wrong_output: str,
    correct_output: str | None = None,  # may be unknown at containment
    failure_category: str = "unknown",
) -> str:
    """Capture a production failure as an eval case during incident containment."""
    case = EvalCase(
        id=f"regression-{incident_id}",
        input=trigger_input,
        expected=correct_output,  # labeler fills this during postmortem
        tags=["regression", "incident", failure_category],
        source="incident-containment",
        incident_id=incident_id,
        captured_at=datetime.utcnow().isoformat(),
        status="pending-label",
    )
    eval_store.add(case)
    return case.id
```

**2. Label during postmortem.**
The postmortem meeting must include a step: "What is the correct behavior for this input?" The action item isn't "consider adding to eval suite" — it's "label this case and mark it regression-ready." Assign ownership to whoever is writing the postmortem.

```python
# In postmortem workflow — final step before closing
def finalize_regression_case(
    case_id: str,
    correct_output: str,
    failure_type: FailureType,
    related_cases: list[str] | None = None,
):
    """Complete the eval case with ground truth from postmortem."""
    case = eval_store.get(case_id)
    case.expected = correct_output
    case.failure_type = failure_type
    case.tags.append("regression-ready")
    case.status = "active"
    case.related = related_cases or []

    # Auto-link to similar existing cases (same failure type, related tool)
    if related_cases:
        for related_id in related_cases:
            eval_store.link(case_id, related_id, relation="same-failure-class")

    # Flag for CI gate on next deploy
    ci_gate.add_regression_case(case_id)
```

**3. Gate on every deploy.**
The regression case enters the CI eval gate immediately. It must pass before the next deployment of the affected agent. This closes the loop: same failure mode cannot ship silently again.

```yaml
# CI eval gate — regression cases have highest priority
eval_gates:
  regression_cases:
    - source: incident-eval-bridge
      priority: P0  # blocks deploy
      threshold: pass_rate >= 1.0  # zero tolerance for known failures
      timeout: 5m
  canary_eval:
    - source: production-eval-pipeline
      priority: P1
      threshold: pass_rate >= 0.90
      timeout: 30m
```

**The timing constraint:**
Cases captured at containment are marked `pending-label` and enter CI only after postmortem labels them. A case without ground truth is stored but gated off until the label is available. This prevents unverified cases from creating false regressions.

## Receipt

> Verified 2026-07-19 — Synthesized from: Axis Intelligence LLM Production Incident Tracker (187 cases, 38% undetected; Apr 2026), ValueStreamAI AI Incident Response Runbook (MTTD 4.5 days; May 2026), Cordum AI Agent Incident Response Runbook (replay-safe recovery; Apr 2026), and handbook entries F-42 (AI Incident Response), S-246 (Production Eval Pipeline), S-1342 (Evaluation Gap Stack), S-1014 (Evaluating Agents in Production), and F-196 (Streaming Production Evaluation) which collectively cover detection, response, and eval but leave the feedback bridge implicit rather than structural.

## See also

- [S-246 · The Production Eval Pipeline](s246-production-eval-pipeline-the-four-stage-loop.md) — the four-stage eval system this bridge feeds into
- [F-42 · AI Incident Response](f42-ai-incident-response.md) — the runbook this bridge extends with an eval obligation
- [S-1342 · The Evaluation Gap Stack](s1342-the-evaluation-gap-stack-when-your-agent-scores-94-but-fails-in-production.md) — why output-scoring evals miss what the bridge captures
- [S-1014 · Evaluating Agents in Production](s1014-evaluating-agents-in-production-where-simplicity-beats-complexity.md) — production eval mechanics
- [F-196 · Streaming Production Evaluation](f196-streaming-production-evaluation.md) — "use production failures as eval seeds" (this entry makes that structural)
