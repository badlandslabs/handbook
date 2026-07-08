# S-678 · The Eval-to-Guardrail Feedback Loop

You ran your eval suite. The LLM-as-judge flagged a new failure class: the agent confidently writes destructive database commands when the query mentions "reset," "wipe," or "clear" — even when the user is asking a legitimate question about data cleanup. You fix the prompt. It still happens 8% of the time. The right move isn't another prompt iteration. It's converting this eval finding into a runtime policy: a semantic guardrail that intercepts *destructive* tool calls when the intent is ambiguous. The eval-to-guardrail feedback loop is the discipline of closing that circle — from production failure to eval signal to policy rule to enforcement — systematically, with versioning and rollback.

## Forces

- **Eval findings are stranded in notebooks.** Most teams detect behavioral failures in offline evals, file a bug, and move on. The knowledge never becomes a runtime safeguard. The same failure recurs in production six weeks later.
- **Manual policy authoring doesn't scale.** Writing guardrail rules by hand (regexes, keyword blocks) is brittle and misses semantic nuance. Eval failures are rich, contextual data about what *kind* of dangerous output the agent produces — data that's far more valuable than a human's intuition about what rules to write.
- **The loop has three states that must stay synchronized.** Eval dataset (the failure case), Guardrail policy (the runtime rule), and Runtime behavior (the enforcement result) drift apart over time. An eval failure fixed in the harness but not in the policy means the runtime is still unprotected. A policy without a corresponding eval means you can't regression-test the guardrail itself.
- **Eval and guardrail teams are usually separate.** ML researchers run evals. Backend engineers own guardrails. The feedback loop between them is a handoff that either happens ad-hoc or doesn't happen at all — and it rarely happens automatically.

## The move

### 1. Capture the failure as a structured eval case

When an eval detects a failure class (offline or shadow), extract it into a canonical case:

```
# Structured failure case
{
  "case_id": "destructive-dml-ambiguous-intent-001",
  "trigger": "query contains [reset, wipe, clear] + tool is write/delete",
  "context": "user is asking about data cleanup, not requesting destruction",
  "agent_behavior": "executes with high confidence",
  "severity": "HIGH",
  "correct_behavior": "block execution, request confirmation",
  "eval_source": "offline-eval-q3-2026"
}
```

This structured form becomes the canonical representation that both the eval harness and the guardrail system consume.

### 2. Encode the semantic pattern into a policy rule

Convert the eval finding into a guardrail predicate. The key is semantic-level matching, not keyword matching:

```python
# Eval-driven guardrail: derived from failure case
from guardrails import Guard

guard = Guard().for_parsed_sql(
    # Semantic: destructive operation + ambiguous intent signal
    on_destructive_dml=Action.BLOCK_AND_ESCALATE,
    intent_signals=["reset", "wipe", "clear"],
    escalation_prompt="Confirm destructive operation with user before proceeding"
)

# The guardrail is versioned alongside the eval case
# guard_v1 ← destructive-dml-ambiguous-intent-001
```

The policy version is pinned to the eval case that generated it (`eval_case_ref: destructive-dml-ambiguous-intent-001`).

### 3. Sync versions — eval dataset and guardrail policy are co-deployed

Treat the eval dataset and the guardrail policy as a coupled pair. They ship together:

```bash
# Co-deploy script
EVAL_VERSION="v2026-Q3-047"
POLICY_VERSION="v2026-Q3-047"

# Deploy eval dataset first (no runtime impact)
deploy_eval_dataset --version=$EVAL_VERSION

# Run regression: does new eval dataset still trigger the guardrail?
python -m harness.run --cases=$EVAL_VERSION --expect-blocked=destructive-dml-ambiguous-intent-001
# If PASS: deploy policy
# If FAIL: guardrail not protective enough — update policy before shipping

deploy_guardrail_policy --version=$POLICY_VERSION --source-case=$EVAL_VERSION
```

This prevents the common failure mode where an eval finds a problem, someone writes a policy, but the two are never regression-tested against each other.

### 4. Runtime violations feed back into eval enrichment

When the guardrail trips in production, that event is itself eval data:

```python
# Runtime violation → eval case enrichment
def on_guardrail_trip(guardrail_event):
    case = {
        "case_id": f"guardrail-trip-{guardrail_event.id}",
        "trigger": guardrail_event.intent_signals,
        "agent_behavior": guardrail_event.detected_behavior,
        "guardrail_version": guardrail_event.policy_version,
        "false_positive": guardrail_event.user_confirmed_safe,
        "eval_source": "production-guardrail-trip"
    }
    eval_dataset.add(case)          # Enrich the eval corpus
    if guardrail_event.false_positive:
        eval_dataset.label(case["case_id"], "false-positive")  # Anti-noise signal
```

Production guardrail trips are gold for eval: they're real inputs the model tried to mishandle. False positives are equally valuable — they reveal over-blocking that needs policy relaxation.

### 5. The complete loop

```
┌──────────────────────────────────────────────────────────────┐
│  OFFLINE EVAL           GUARDRAIL POLICY           RUNTIME  │
│  ┌──────────┐           ┌──────────────┐          ┌───────┐ │
│  │ New      │──(derive)→│ Policy rule  │──(deploy)→│ Guard │ │
│  │ failure  │           │ + version    │          │ rail  │ │
│  │ case     │           │ ref          │          │ trips │ │
│  └──────────┘           └──────────────┘          └───┬───┘ │
│       ↑                                            │      │
│       │ (enrich)                              (feedback)  │
│       └────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

Run the full loop on a cadence: weekly eval review → policy derivation → co-deploy → production monitoring → eval enrichment.

## Receipt

> Verified 2026-07-06 — Pattern synthesized from Cleanlab AI Agents in Production 2025 (5.2% of enterprises have closed feedback loops between eval and guardrails), Galileo AI Observability Trends 2026 (eval-to-guardrail lifecycle as a key 2026 architectural pattern), and Kong AI Guardrails engineering blog. Structural example uses guardrails-ai (LGPL) Guard class semantics and MCP eval-driven policy derivation patterns from MCPEval (arXiv:2507.12806).

## See also
- [S-219 · Agent Eval Harness](/stacks/s219-agent-eval-harness.md) — the harness that generates the failure signal
- [S-246 · The Production Eval Pipeline](/stacks/s246-production-eval-pipeline-the-four-stage-loop.md) — four stages where failures surface
- [S-198 · Agent Tool-Call Guardrails](/stacks/s198-agent-tool-call-guardrails.md) — the enforcement endpoint
- [S-541 · Agent Drift Detection](/stacks/s541-agent-drift-detection.md) — monitoring the loop's runtime health
- [S-658 · Golden Trace Set Curation](/stacks/s658-golden-trace-set-curation.md) — feeding quality traces into the eval side
