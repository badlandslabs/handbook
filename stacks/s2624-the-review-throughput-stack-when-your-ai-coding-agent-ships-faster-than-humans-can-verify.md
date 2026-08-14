# S-2624 · The Review-Throughput Stack — When Your AI Coding Agent Ships Faster Than Humans Can Verify

Your agent generated 47 pull requests last sprint. Your team reviewed 12. The rest sit in a queue that grows faster than anyone can clear it. Every engineer has the same story: AI didn't break coding. It broke the review step that stood between code and production. The bottleneck moved, and most teams didn't notice until the backlog was already unmanageable.

## Forces

- **Review capacity is human-bounded and non-negotiable.** A senior engineer can review roughly 3–5 PRs per day with full attention. A coding agent can generate 20–50 PRs per day with the same model. The mismatch is structural, not temporary. Adding more agents makes it worse.

- **Not all changes carry equal risk.** A one-line dependency update carries different blast radius than a rewrite of the authentication module. Treating every PR as equally review-worthy is the wrong abstraction — it was designed for a world where humans wrote most of the code.

- **Agents can self-review faster than they can be reviewed by humans.** An agent with access to a test harness, a linter, and its own change diff can generate a first-pass review faster than a human can open the PR. The question is what "trustworthy self-review" looks like, and how to calibrate it.

- **Review queue congestion has real costs.** Stale PRs accumulate merge conflicts, diverge from trunk, and require re-review when finally merged. The "shipping velocity" gain from agents is partially eaten by review latency — sometimes entirely.

## The Move

Build a three-layer review-throughput stack: **risk classification → automated first-pass → human escalation for high-risk changes**.

### Layer 1 — Risk Classification

Classify each PR at creation time using a lightweight model call against the change metadata:

```python
# Risk classification based on change surface
def classify_pr_risk(pr_diff: str, pr_context: dict) -> str:
    """
    Returns: LOW | MEDIUM | HIGH
    """
    high_risk_signals = [
        pr_context.get("files_touched", []) - ALLOWED_SAFE_PATHS,
        any(p in pr_diff for p in SECURITY_SURFACES),   # auth/, payment/, /
        len(pr_diff) > 500,                              # large rewrite
        pr_context.get("new_dependencies", []),         # dependency changes
    ]

    if any(high_risk_signals):
        return "HIGH"    # Human review required — no exceptions
    elif len(pr_diff) > 100 or pr_context.get("touches_config", False):
        return "MEDIUM"  # LLM-assisted review + human spot-check
    else:
        return "LOW"     # Agent self-review only

ALLOWED_SAFE_PATHS = {"tests/", "docs/", "chore/", "deps/"}
SECURITY_SURFACES = ["auth/", "payment/", "credential", "permission", "access_"]
```

This runs as a CI gate before the PR is even opened. LOW and MEDIUM changes proceed on their respective tracks; HIGH changes queue for human review with an SLA.

### Layer 2 — Agent Self-Review for LOW/MEDIUM

Agent self-review is not "the agent approves its own PR." It is a structured second-pass using separate tooling from the authoring agent:

```python
def agent_self_review(pr_number: int, confidence_threshold: float = 0.85):
    """
    Structured self-review using separate model/instance from authoring agent.
    """
    diff = gh.get_pr_diff(pr_number)
    tests = test_suite.run(diff)          # Existing test suite
    lints = linter.run(diff)              # Static analysis
    breaking = api_compat.check(diff)     # API compatibility check

    review_signals = {
        "test_coverage_delta": coverage_delta(diff),
        "lint_error_count": len(lints),
        "breaking_change_risk": breaking.risk_score,
        "complexity_delta": cyclomatic_delta(diff),
    }

    # Generate structured review comment
    review_body = llm_judge_review(
        diff=diff,
        signals=review_signals,
        instructions=REVIEW_PROMPT,       # "Criticize this change. Be specific."
    )

    gh.post_pr_comment(pr_number, review_body)

    # Self-merge if confidence threshold met
    if review_signals["breaking_change_risk"] < 0.1:
        gh.add_label(pr_number, "auto-review:pass")
        if classify_pr_risk(diff, {}) == "LOW":
            gh.merge(pr_number, auto_merge=True)
            log.info(f"PR #{pr_number} auto-merged via self-review")
```

The key discipline: the reviewing agent must be a different instance or model from the authoring agent. Self-review with the same model and context is the equivalent of proofreading your own writing — you catch typos, not logic errors.

### Layer 3 — Human Escalation for HIGH

HIGH-risk PRs go to a prioritized review queue with a clear ownership model:

```yaml
# .github/review-policy.yml
review_policy:
  HIGH_risk:
    required_reviewers: 2
    required_labels: ["security-sign-off", "architecture-sign-off"]
    max_queue_age_hours: 4
    escalate_after_hours: 8

  MEDIUM_risk:
    required_reviewers: 1
    required_labels: []
    max_queue_age_hours: 24
    auto_escalate_if: ["coverage_drop > 5%", "breaking_change"]

  LOW_risk:
    auto_review: true
    auto_merge: true
    post_merge_notify: ["#agent-prs"]
```

### The Calibration Loop

Risk thresholds drift as the codebase changes. Treat the classification model as a production system with its own evaluation loop:

```python
# Quarterly calibration: check false negatives (high-risk PRs that slipped to LOW)
def calibrate_thresholds(golden_dataset: list[PRCase]):
    results = [
        classify_pr_risk(case.diff, case.context) == case.true_risk
        for case in golden_dataset
    ]
    precision = precision_score(golden_dataset, results)
    if precision < 0.90:
        alert("Risk classifier precision below 90% — recalibrate needed")
        log_golden_dataset_misses(golden_dataset, results)
```

Track the **review bottleneck ratio**: `PRs_generated / PRs_reviewed_per_week`. If it exceeds 3:1, the review backlog is growing faster than it can be cleared. The response is not more human reviewers — it is more automation on the LOW/MEDIUM path.

## Receipt

> Verified 2026-08-14 — Code example is a reference architecture pattern consistent with:
> - Moderne blog (Jul 6, 2026): risk-based PR routing, fast path for low-risk changes
> - Reddit r/LocalLLaMA discussion (Jun 2026): "If AI increases code volume by 10×, human review becomes a fatal bottleneck"
> - Agent eval docs (Jun 2026): trajectory-level failure classification
>
> Receipt pending — code not executed against a live repo.

## See also

- [S-2618 · The Agent Eval Stack](s2618-the-agent-eval-stack-when-you-ship-on-vibes-and-discover-regressions-in-production.md) — trajectory-level grading that makes automated review feasible
- [S-2615 · The Three-Layer Agent Reliability Stack](s2615-the-three-layer-agent-reliability-stack-when-your-model-is-smart-but-your-system-still-fails.md) — eval vs. guardrail vs. harness separation
- [S-2623 · The Agent Evaluation Surface Stack](s2623-the-agent-evaluation-surface-stack-when-a-green-dashboard-hides-corrupted-records.md) — why dashboards miss the right layer of failure
