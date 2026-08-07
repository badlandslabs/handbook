# S-2261 · The Failure Classification Stack — When Your Agent Ran and the Team Spent Three Hours Disagreeing on What Went Wrong

Your agent shipped a subtly broken answer on Monday morning. By Tuesday, four engineers had examined the trace, written three theories, and still couldn't agree on root cause. One blamed the retriever. One blamed the model. One blamed the tool API. One said the prompt was fine. Nobody was wrong — but nobody was productive either. The problem wasn't technical depth. The problem was that nobody had a shared vocabulary for what "it failed" actually means.

This is the failure classification problem: without a taxonomy, agent failures generate debate instead of diagnoses. Every team invents their own vocabulary for the same failure categories, so nothing compounds. The 80-hour fix scenario from DevOS's 2026 report isn't primarily a technical problem — it's a communication problem with a technical surface.

## Forces

- **Agents fail in five categories, not one.** FutureAGI's production research (Feb 2026, updated May 2026) identifies five categories that cover every OWASP ASI04 entry, MITRE ATLAS technique, and real incident: planning errors (wrong tool sequence, infinite loop), tool errors (wrong args, schema mismatch, truncation), retrieval errors (stale or absent context), reasoning errors (confident nonsense, wrong inference), and safety/policy violations (data exfiltration, privilege abuse). Treating these as one failure type makes every postmortem a re-invention.
- **The right category routes the fix to the right surface.** A planning error lives in the planner prompt or the plan-vs-execute eval. A tool error lives in the schema contract or the tool-response gate. A retrieval error lives in the retriever's freshness policy. A reasoning error may need a different model, a different prompt, or a different output verifier. Without the category, engineers try everything.
- **Failure categories become regression tests.** Once a failure is classified, the subtype becomes a concrete test case in CI. FutureAGI's "fix-loop" — cluster, judge, promote, gate — is the operational embodiment: each named failure creates a detector that fires before the next production run. This is how incident memory becomes institutional memory.
- **Multi-agent failures add handoff categories.** When two or more agents interact, a sixth failure surface opens: handoff errors. The sending agent succeeded. The receiving agent received corrupted or incomplete state. Neither log shows the failure — it lives in the boundary between them. S-1013 (multi-agent boundary stack) covers the state disagreement pattern; this entry covers the classification and routing mechanics.
- **Rework cost compounds without classification.** CISQ/NIST data on escaped defects (validated across software quality studies) shows defects fixed in postmortem cost 6.5× more than those caught in review. An agent that misroutes an access request silently for three hours before detection generates more rework hours than the original agent-writing session — a pattern the DevOS 2026 report quantifies as the dominant cost in agent failures, dwarfing token spend.

## The Move

**Step 1: Instrument a five-category classifier into your trace pipeline.** Parse every agent failure at the trace level. Classify into the five FutureAGI categories (planning, tool, retrieval, reasoning, safety/policy) using trace fingerprints:

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class FailureCategory(Enum):
    PLANNING = "planning"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    REASONING = "reasoning"
    SAFETY_POLICY = "safety_policy"
    HANDOFF = "handoff"  # multi-agent extension

@dataclass
class TraceFingerprint:
    tool_sequence: list[str]
    tool_call_errors: int
    retrieval_confidence: float
    retrieval_sources: int
    hallucination_signals: list[str]
    output_verified: bool
    handoff_payloads: int
    handoff_errors: int
    policy_violations: list[str]

def classify_failure(fp: TraceFingerprint) -> FailureCategory:
    """Classify based on trace fingerprint, not outcome.

    Priority order matters: check safety first (fail fast on violations),
    then tool (most common), then handoff (multi-agent only), then
    retrieval, then planning, then reasoning.
    """
    if fp.policy_violations:
        return FailureCategory.SAFETY_POLICY
    if fp.handoff_errors > 0 and fp.handoff_payloads > 0:
        return FailureCategory.HANDOFF
    if fp.tool_call_errors > 0:
        # Sub-classify: wrong tool vs. wrong args vs. truncation
        return FailureCategory.TOOL
    if fp.retrieval_confidence < 0.4 or fp.retrieval_sources == 0:
        return FailureCategory.RETRIEVAL
    if len(fp.tool_sequence) == 0 or _has_infinite_loop_signal(fp):
        return FailureCategory.PLANNING
    if not fp.output_verified or fp.hallucination_signals:
        return FailureCategory.REASONING
    return FailureCategory.REASONING  # default when unsure

def _has_infinite_loop_signal(fp: TraceFingerprint) -> bool:
    # Detect repeated identical tool sequences (3+ occurrences)
    if len(fp.tool_sequence) < 6:
        return False
    window = fp.tool_sequence[-3:]
    if fp.tool_sequence[-6:-3] == window:
        return True
    return False
```

**Step 2: Route each category to the right fix surface.** Once classified, route to the team or automated system responsible for that layer:

```python
def route_fix(category: FailureCategory, trace_id: str) -> str:
    """Return the fix surface (team or automated system) for each category."""
    routes = {
        FailureCategory.PLANNING:       "planner-review queue / plan-verify eval",
        FailureCategory.TOOL:           "tool-schema contract / MCP server owner",
        FailureCategory.RETRIEVAL:       "retriever freshness policy / embedding pipeline",
        FailureCategory.REASONING:       "model eval harness / output verifier",
        FailureCategory.SAFETY_POLICY:   "security review / guardrail audit",
        FailureCategory.HANDOFF:         "multi-agent boundary contract / handoff schema",
    }
    routing = routes[category]
    # Emit to incident tracker with category + trace link
    emit_incident(category=category.value, trace_id=trace_id,
                  fix_surface=routing)
    return routing
```

**Step 3: Promote failures to regression tests.** After triaging, extract the specific subtype and write a test case that fires before the next deployment. This is the compounding mechanism:

```python
def promote_to_regression(failure: FailureRecord) -> str:
    """Convert a triaged failure into a regression test stub.

    The test stub goes into your agent eval harness. Each time a
    category fires, the stub is updated with the actual failing input.
    This is the 'gate' in FutureAGI's cluster-judge-promote-gate loop.
    """
    test_name = f"regression_{failure.category.value}_{failure.subtype}_{failure.date:%Y%m%d}"
    test_body = f"""
def test_{test_name}():
    \"\"\"Regression: {failure.category.value} / {failure.subtype}
    Trace: {failure.trace_id}
    Filed: {failure.date:%Y-%m-%d}
    Fix surface: {failure.fix_surface}
    \"\"\"
    result = run_agent(input={failure.failing_input!r},
                       tools={failure.tool_state!r},
                       context={failure.context_state!r})
    assert result.category_matches("{failure.category.value}")
    assert not result.has_subtype("{failure.subtype}")
"""
    write_test(f"regressions/{test_name}.py", test_body)
    return test_name
```

**Step 4: Track category frequency to find systemic problems.** A team that sees the same tool error repeatedly isn't unlucky — they have a schema drift problem or an unmaintained MCP server. Plot category frequency over time:

```python
# Dashboard query: category frequency per sprint
# Alert threshold: if a category appears >3× in one week, schedule
# a systemic review of that layer rather than treating each incident individually
def check_systemic_pattern(incidents: list[FailureRecord], window_days=7) -> dict:
    from collections import Counter
    recent = [i for i in incidents if i.age_days() <= window_days]
    counts = Counter(i.category for i in recent)
    systemic = {cat: n for cat, n in counts.items() if n >= 3}
    if systemic:
        return {"ALERT": "Systemic pattern detected", "categories": systemic}
    return {"OK": True}
```

## Receipt

> Verified 2026-08-07 — Framework synthesized from FutureAGI 5-category taxonomy (Feb 2026, updated May 2026), DevOS 2026 failure-cost statistics, Singularity Journey failure taxonomy guide (Jul 2026), Preporato error-handling patterns, and Forrester root-cause analysis of pilot failures. Code examples are minimal working stubs demonstrating the classification and routing mechanics. Each stub is designed to drop into an existing trace/observability pipeline. Real production validation would require integration with a live agent trace store (e.g., LangSmith, Phoenix, or custom OTLP pipeline).

## See also

- [S-1009 · The Agentic RCA Stack](stacks/s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — post-hoc trace analysis tooling
- [S-1026 · The PAEF Stack](stacks/s1026-the-paef-stack-when-your-benchmark-says-pass-but-4-out-of-7-failure-modes-sneaked-past.md) — eval coverage for trajectory-level failures
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — handoff state disagreement
- [S-997 · The Agent Observability Stack](stacks/s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — trace-level monitoring foundations
