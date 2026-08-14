# S-2652 · The Session-Aware Agentic Routing Stack — When Your Model Router Breaks Your Agent Halfway Through a Task

Your routing layer is saving 40% on inference costs. Your agent's task success rate is also 40% — and nobody connected the two. The router switched the model mid-session and the agent lost its working state, restarted a tool loop, or got a response from a model that had no memory of the conversation. Routing works fine in single-turn settings. In multi-turn agent sessions, it is a continuity weapon.

## Forces

- **Single-turn routing is locally optimal but session-hostile.** A router that picks the cheapest capable model per turn can switch models 3–6 times in a 20-step agent session. Each switch drops prefix cache (the new model re-encodes the prior context from scratch) and may introduce capability discontinuities — the new model lacks the prior model's context-accumulated beliefs about the task state.
- **Tool loops are the primary casualty.** A model that switches mid-loop re-enters with a different interpretation of the loop state. Haiku doesn't know Sonnet decided to try a different API. It re-reads the tool outputs and may restart the same failing call — silently, with no indication that the loop is broken.
- **Prefix cache is per-model, not per-session.** vLLM's SAAR research (June 2026) found that switching models inside a session invalidates prefix cache for that session's context. A Sonnet→Haiku switch means the new model's first forward pass re-encodes everything from scratch. The cost savings from routing are partially eaten by repeated full-context encoding.
- **Capability tiers have different tool-call behaviors.** Haiku 4.5, GPT-4o-mini, and Sonnet 4.6 produce different tool call formats, different retry behaviors, and different instruction-following fidelities on complex tool chains. A routing decision that is correct for simple Q&A can break a tool-calling agent without warning.
- **Routing audits are single-turn; failure is multi-turn.** Standard routing evals (MMLU, HumanEval) measure per-call quality. They miss the compound failure that appears only across 10+ turns: accumulating state corruption, deadlocked tool loops, and escalating context waste from repeated re-encoding.

## The move

**1. Classify sessions, not just requests.** Before routing, tag each incoming request: is this a fresh single-turn query or a continuation of an existing agent session? Agent sessions get session-aware routing policies — they can still route between tiers but with continuity constraints.

**2. Impose hard no-switch boundaries.** Define states where model switching is prohibited: inside a tool loop (same tool called 2+ times consecutively), inside a multi-step API transaction, inside a partial write operation. These are continuity-critical zones. SAAR (vLLM, June 2026) formalizes this as "continuity gates" — session memory that remembers what the agent is in the middle of.

```python
CONTINUITY_GATES = {
    "in_tool_loop": 2,       # no switch if same tool called N+ times
    "in_api_transaction": True,   # no switch during open transaction
    "in_partial_write": True,    # no switch during in-progress writes
    "has_tool_state": True,      # no switch if agent holds tool-generated state
}

def can_switch_model(session_ctx, candidate_model):
    if session_ctx.get("tool_loop_count", 0) >= CONTINUITY_GATES["in_tool_loop"]:
        return False
    if session_ctx.get("api_transaction_open"):
        return False
    if session_ctx.get("partial_write_pending"):
        return False
    # Only switch if model is safe for current capability requirement
    return model_meets_tier_requirement(candidate_model, session_ctx.required_tier)
```

**3. Route on task complexity, not just cost.** RouteLLM (LMSYS/Berkeley) and Agent-as-a-Router (arXiv:2606.22902, June 2026) both show that complexity-aware routing outperforms cost-based routing for agentic tasks. Use a lightweight classifier (query length, estimated step count, tool count) to tier tasks before dispatch.

```python
def classify_task_complexity(request):
    features = [
        len(request.messages),
        count_tool_names(request),
        estimate_turns(request),        # heuristic: tool count × branching factor
        has_multi_tool_dependency(request),  # does output of one feed into another?
    ]
    score = route_model.predict_complexity(features)
    if score < 0.3: return "nano"    # GPT-4o-mini, Haiku
    elif score < 0.6: return "mid"   # Sonnet, GPT-4o
    else: return "frontier"           # Opus, GPT-5
```

**4. Implement switch costing that includes re-encoding.** The true cost of a model switch = inference cost of new model + (re-encode tokens × new model cost). For a 50K-token session context, switching to Haiku saves on inference but pays full encode cost on the new model. SAAR found that prefix-cache-aware switch pricing eliminated 79.29% of wasteful switches in production.

**5. Add continuity observability.** Track model-switch events per session, correlate with task failure rates, and alert on switch clusters (3+ switches in a 10-turn session). The symptom of bad routing is not "model switched" — it's "agent re-ran the same tool call" or "task completion time 3× baseline."

**6. Test routing changes against agent sessions, not just prompts.** Any routing policy change requires an agentic test suite: multi-turn tool-calling scenarios, 20+ turn sessions, partial-failure recovery paths. Single-turn benchmark parity is insufficient.

## Receipt

> Verified 2026-08-14 — Pattern validated against: (1) vLLM SAAR paper (2026-06-02) — 21,600 deterministic turns, 79.29% switch reduction, 0 continuity violations; (2) Agent-as-a-Router (arXiv:2606.22902, June 2026) — agentic routing outperforms static classification routing on multi-step coding tasks; (3) Topaz framework (arXiv:2604.03527, Georgia Tech, April 2026) — explainable routing taxonomy for agentic workflows; (4) Zylos Research model routing survey (2026-03-02) — 40-85% cost reduction from dynamic routing with agentic-aware policies. Composite: 9.40.

## See also

- [S-06 · Model Routing](s06-model-routing.md) — the static routing foundation; this entry extends it for agentic sessions
- [S-2651 · The Context Forgetting Stack](s2651-the-context-forgetting-stack-when-your-agent-loses-everything-between-sessions.md) — session state loss is one consequence of routing-induced model switches
- [S-1000 · The Context Exhaustion Stack](s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — re-encoding on model switch accelerates context exhaustion
- [S-2650 · The Agentic Spend Attribution Stack](s2650-the-agentic-spend-attribution-stack-when-the-invoice-lands-but-nobody-knows-why.md) — routing cost attribution needs per-session switch accounting
