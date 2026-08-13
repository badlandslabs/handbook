# S-2573 · The Context Garbage Collection Stack — When Your Agent Kills the URL It Still Needs

Your agent ran for 80 turns. It found the bug report on GitHub, read the relevant file paths, wrote a fix, and pushed a PR. Then it pasted the wrong URL in the Slack message — the link pointed to the old ticket, not the new PR. You check the context window: 40% full. The tool output containing the PR URL was pruned at turn 52 because it was the oldest thing that looked like a string longer than 20 characters. Nobody told the pruning logic that this string was a dependency of the next action. It just looked old. This is not a context-window problem. It is a **context lifecycle problem**.

## Forces

- **Text-based eviction is blind to structure.** Chronological pruning, token-count thresholds, and LRU are designed for memory arrays. Agent context contains typed references — URLs, file paths, variable names, plan IDs — that may be needed dozens of turns after their first appearance. Dropping them because they are old is like garbage-collecting a pointer because its heap object is old.
- **Summarization destroys evidence, not just noise.** When context pressure builds, the standard response is self-summary: the agent rewrites the history into a compressed narrative. This preserves the *story* of what happened but destroys the *locators* — the exact URLs, paths, and identifiers that the next action depends on. The agent can explain what it did but cannot reference what it produced.
- **Tool outputs are oversized and oddly structured.** A `grep` result, a directory listing, a curl response — these are often 5–20× larger than the single line the agent actually needs. But the garbage collector cannot know which line that is without semantic understanding.
- **The agent cannot introspect its own dependency graph.** The model does not maintain an explicit record of "I will need X again." Its attention mechanism creates implicit dependencies, but the harness has no access to them. Eviction decisions are made without knowing what will break.

## The move

Treat agent context as a collection of typed runtime objects with tracked lifecycles, not as a flat text buffer to be trimmed.

### 1. Objectify the context

Segment raw context into typed objects at ingestion time:

```python
class ContextObject:
    id: str
    type: Literal["user_turn", "tool_result", "plan", "skill_state", "artifact"]
    created_at: int          # turn index
    size_tokens: int
    references: set[str]     # IDs this object mentions
    referenced_by: set[str]  # IDs that depend on this object
    foldable: bool           # can be replaced by a summary?
    prunable: bool           # safe to drop entirely?
    recovery_hint: str       # how to re-fetch if needed
```

Each tool result is wrapped at output time. The wrapper captures: what identifiers appeared (URLs, paths, IDs), which prior objects this output depends on, and what recovery action could re-fetch the same information.

### 2. Track inter-object references

```python
def build_dependency_graph(objects: list[ContextObject]) -> dict[str, set[str]]:
    graph = {obj.id: set() for obj in objects}
    for obj in objects:
        for ref in obj.references:
            if ref in graph:
                graph[obj.id].add(ref)
    return graph

def compute_reachability(graph: dict[str, set[str]], from_id: str) -> set[str]:
    """Objects reachable from a future action through the dependency chain."""
    visited = set()
    queue = [from_id]
    while queue:
        current = queue.pop(0)
        for dependent in graph.get(current, []):
            if dependent not in visited:
                visited.add(dependent)
                queue.append(dependent)
    return visited
```

Before any eviction, compute whether the candidate object is transitively referenced by any pending or likely future action. An object is *dead* only when it has zero inbound references and zero forward reachability to unexecuted plan steps.

### 3. Three eviction primitives — not one

| Primitive | Trigger | Mechanism | Recovery |
|-----------|---------|-----------|----------|
| **Mask** | Object is referenced but oversized | Replace raw output with `{type: "tool_result", ref: "obj_id", summary: "..."}` | Restore full object on read-by-reference |
| **Fold** | Object is repetitive + referenced | Collapse N sequential tool results of the same type into a summary with a count and the last item preserved | Restore from summary + count |
| **Prune** | Object is dead (no forward reachability) | Remove from context entirely | Re-fetch via recovery_hint on access |

Mask and fold preserve the object in a sidecar store; prune removes it. The model never sees the full sidecar — it sees a compact reference card.

### 4. Side-channel planner for eviction decisions

The main agent loop is too busy to optimize its own context. Use a lightweight side-channel model:

```python
def propose_eviction(context_objects: list[ContextObject],
                     pending_plan: list[str],
                     budget_tokens: int) -> list[EvictionAction]:
    prompt = f"""Current context: {total_tokens(context_objects)} tokens.
    Budget: {budget_tokens} tokens. Pending plan steps: {pending_plan}.
    Objects: {format_object_summary(context_objects)}.
    Propose mask/fold/prune actions. Return JSON list."""
    response = llm.parse(prompt, schema=EvictionActionList)
    return response.actions
```

This planner sees the full object graph and plan, so it can make dependency-aware decisions. The Xiaohongshu team showed that three different planner backbones achieved 91–95% no-impact rates on production traces using this approach — compared to 78–87% for heuristic baselines.

### 5. Safe commit boundaries

Never evict mid-task. A safe commit boundary fires after:

```python
def is_safe_commit_point(context_objects: list[ContextObject]) -> bool:
    # No tool call is in-flight
    # All pending plan steps have outputs in context
    # No object has referenced_by that hasn't been satisfied
    active = [o for o in context_objects if o.status == "pending"]
    return len(active) == 0 and all(
        context_objects[ref].status == "complete"
        for o in context_objects
        for ref in o.references
    )
```

Post-commit, fold the completed task's context into a single `TaskArtifact` object and reset to baseline.

### 6. Production token reduction

Xiaohongshu (3.2M users, 761M LLM calls/month) reports:
- **10–15% average daytime token reduction** (online A/B)
- **~20% peak reduction** during high-activity sessions
- **43.95% prefix pruning** on hard multi-session tasks with no-impact rate of **84.85%**
- On easier production traces: **91–95% no-impact rate** across planner backbones

The key difference: heuristic pruning had a 30–45% no-impact gap because it blindly preserved old content that was actually dead, while Self-GC preserved old content because it was *actually referenced*.

## Receipt

> Verified 2026-08-13 — Researched Self-GC (arXiv:2607.00692, Hao et al., Xiaohongshu, July 2026). The paper documents production deployment at Xiaohongshu scale. Three planner backbones tested: 91–95% no-impact on production traces vs 78–87% for baselines. Online A/B: 10–15% average token reduction, ~20% peak. Core insight confirmed: treating context as typed objects with dependency tracking enables 3–4× better eviction precision than text-based heuristics. Self-GC pattern (indexed objects + side-channel planner + fold/mask/prune + safe commit boundaries) is novel relative to existing handbook entries on context rot (S-2388), structured eviction (S-2063), and context lifecycle (S-1432) — those entries cover the failure symptom and generic mitigation; this entry covers the specific structured-object + dependency-graph mechanism with production numbers.

## See also

- [S-2388 · The Context Rot Stack](/stacks/s2388-the-context-rot-stack-when-your-agent-slowly-forgets-what-you-already-told-it.md) — attention degradation at long context length (the "why" — this entry is the "how")
- [S-2063 · The Structured Eviction Stack](/stacks/s2063-the-structured-eviction-stack-when-your-agent-buries-critical-context-in-noise.md) — importance-weighted eviction without dependency tracking
- [S-1432 · The Context Lifecycle Stack](/stacks/s1432-the-context-lifecycle-stack-when-your-agent-starts-forgotting-plans-it-wrote-twenty-steps-ago.md) — plan lifecycle management within the session
- [S-2571 · The Circuit Breaker Stack](/stacks/s2571-the-circuit-breaker-stack-when-nothing-stops-a-failing-agent.md) — enforcement guards that complement lifecycle management
