# [S-2222] · The Ambiguity Trust Gap Stack — When Your Agent Doesn't Know What It Doesn't Know

Your agent surfaces a confident plan for a task you gave in three words. It has no idea whether those three words meant the right thing. It also has no idea that asking for clarification — the responsible, human-like thing to do — will make it dramatically more vulnerable to a prompt injection hiding in the same context. The gap between what your agent is uncertain about and what it shows you is the ambiguity trust gap.

## Forces

- **RLHF makes calibration worse, not better.** Alignment training rewards confident-sounding outputs, not accurate confidence signals. Post-RLHF models are systematically overconfident about both their understanding of the goal and their ability to execute it.
- **Single scalar confidence conflates two distinct problems.** "I'm 70% confident" could mean "this is hard but I understand what you want" or "I have no idea what you mean but I'm going to act anyway." These demand completely different responses — more effort vs. clarification.
- **Clarification is a double-edged sword.** The safer path — asking the user to disambiguate — widens the attack surface. An agent in a clarification state has elevated susceptibility to prompt injection embedded in the same context.
- **Black-box API deployments can't use the textbook solutions.** Trained uncertainty estimators, multi-sampling, and logprob-based methods require access that hosted models don't expose.

## The Move

Split the single confidence signal into two orthogonal axes, then gate every downstream decision on both.

### 1. Decompose Uncertainty into Two Signals

| Signal | Semantics | Response |
|--------|-----------|----------|
| **Request Uncertainty** `u_t ∈ [0,1]` | Goal underspecification: are the parameters clear? | Defer, clarify, or abstain |
| **Action Confidence** `c_t ∈ [0,1]` | Task difficulty: can I execute given a clear goal? | Proceed, slow down, or escalate |

Anchored scale for request uncertainty: `0.0 = fully specified`, `0.5 = at least one param missing`, `1.0 = multiple interpretations possible`. Do NOT use the raw model output as the anchor — the model calibrates to the anchors, so pick conservative values.

### 2. Build the Clarification Gate

```python
def should_clarify(u_t: float, c_t: float, mode: str = "safe") -> str:
    # Mode: "safe" (production) vs "fast" (internal tasks)
    threshold = 0.4 if mode == "safe" else 0.7

    if u_t >= threshold:
        return "CLARIFY"   # Goal unclear — stop and ask
    elif c_t < 0.3:
        return "ESCALATE"  # Task too hard — human needed
    elif c_t < 0.6:
        return "SLOW_DOWN" # Increase deliberation steps
    else:
        return "PROCEED"

# ASPI security wrapper: sandboxed clarification state
# When CLARIFY is triggered, enter restricted execution mode
clarification_context = {
    "state": "clarification",
    "tools": ["read_only_memory", "formulate_question"],  # NO side-effect tools
    "max_attempts": 1,
    "injection_filter": True,  # re-validate context for injection patterns
}
```

### 3. Propagate Uncertainty Through the Trajectory

Store both signals in memory alongside each action. Subsequent steps can reason about accumulated uncertainty without additional API calls.

```python
trajectory = [
    {
        "step": 0,
        "request_uncertainty": 0.6,   # "set up my server" — ambiguous
        "action_confidence": 0.8,
        "decision": "CLARIFY",
        "clarification": "Which cloud provider, region, and instance type?"
    },
    {
        "step": 1,
        "request_uncertainty": 0.1,   # clarified — specific now
        "action_confidence": 0.75,
        "decision": "PROCEED",
        "accumulated_uncertainty": 0.1 * 0.75
    }
]
```

### 4. ASPI Hardening: Treat Clarification as Elevated-Risk State

The ASPI benchmark (arXiv:2605.17324, Scale AI / BU / UIUC, May 2026) shows that agents in a clarification-seeking state have measurably higher susceptibility to prompt injection. The mitigation is not to suppress clarification — it's to isolate the state:

- **Separate the clarification context window** from the main task context. The injection payload in the user's original query should not be present when the model generates a clarification question.
- **Re-validate tool returns** in clarification state. The attacker model (hidden in retrieved content) responds differently when the agent signals uncertainty.
- **Hard timeout on clarification loops.** If the agent asks the same clarification twice, escalate rather than re-engage.

### 5. Source the Signals Without Extra API Calls

For black-box deployments (most production setups), use prompt-based decomposition:

```
You are estimating two quantities for the user's request.
Request Uncertainty u: Is the goal fully specified, or are there
ambiguous parameters (scope, format, constraints, recipient)?
  0.0 = fully specified, 0.5 = one param missing, 1.0 = unclear
Action Confidence c: Given a clear goal, how confident are you
that you can execute this correctly?
  0.0 = no idea, 0.5 = uncertain, 1.0 = highly confident
Return ONLY: u=<value>, c=<value>
```

Evaluate this in a zero-shot, separate API call before task execution. Cost: ~100-200 tokens per decision point. Compare to the cost of a confused execution or a security incident.

## Receipt

> Verified 2026-08-06 — Ideas Bank exhausted. Fresh research cycle. Key sources:
> - arXiv:2606.19559 (Matsnev, Jun 2026): uncertainty decomposition into request uncertainty `u_t` and action confidence `c_t` with anchored scale methodology. Code: github.com/PE51K/udcs-in-llm-agents.
> - arXiv:2605.17324 (Madhushani Sehwag et al., Scale AI / BU / UIUC, May 2026): ASPI benchmark (728 scenarios) demonstrating 728/728 × higher prompt injection susceptibility in clarification state. Controlled for matched execution conditions.
> - ACL 2026 Long Paper (Oh et al., UW-Madison / CMU / Berkeley / UPenn, ACL 2026, pp.16219–16250): UQ in LLM agents — argues UQ research must shift from single-turn QA to interactive multi-step settings.
> - Zylos Research (Apr 2026): RLHF systematically degrades calibration; post-aligned models are 20-40% overconfident on out-of-domain inputs.
> - BrowseConf (web agents, 2025): confidence-based compute allocation improves success rate; UAM (uncertainty-aware memory) propagates signals through trajectory without extra calls.
>
> Deduplication: S-1087 (Supervisor Guardian) covers external monitoring but not uncertainty decomposition. S-1132 (Semantic Intent Divergence) covers intent disagreement, not goal ambiguity quantification. S-1143 (Failure Tax) covers failure awareness, not the two-signal decomposition. S-2214 (Semantic Drift) covers memory-layer drift, not uncertainty decomposition. No existing entry covers the request uncertainty / action confidence decomposition + ASPI clarification vulnerability intersection.

## See also
- [S-1087 · The Supervisor Guardian Stack](/stacks/s1087-the-supervisor-guardian-stack-when-your-agent-needs-an-external-brain-to-stop-it-from-destroying-itself.md) — external monitoring when internal signals fail
- [S-1143 · The Failure Tax Stack](/stacks/s1143-the-failure-tax-stack-when-agents-break-and-dont-know-it.md) — when agents don't know they failed
- [S-1132 · The Semantic Intent Divergence Stack](/stacks/s1132-the-semantic-intent-divergence-stack-when-your-agents-all-succeed-but-disagree-on-what-success-means.md) — multi-agent intent misalignment
