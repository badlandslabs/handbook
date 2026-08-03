# S-2063 · The Structured Eviction Stack — When Your Agent Buries Critical Context in Noise

You are 47 tool calls into a refactoring session. The agent has read 12 files, run 3 test suites, and discovered 6 architectural constraints the codebase doesn't document. Now it needs to call a new function — but it forgot that `parse_config()` was renamed to `load_config()` six calls ago. Not because the model degraded. Because the context filled with 40,000 tokens of exploration noise, and the rename fact got evicted by recency truncation. The agent is not forgetting. The eviction policy is burying signal.

## Forces

- **Append-only context is the default.** Every agent framework adds to context. Nothing removes from it until overflow happens — then something arbitrary gets cut. The decision of *what* to evict is either absent or semantically blind.
- **Compaction destroys structure you need.** Summarization is the standard response to context pressure: call a cheap model, compress, continue. But LLM-based compression collapses the causal chain (tool call → result → decision → next action) into a bag of facts. On structured tasks, this destroys the very information that matters most.
- **Recency eviction is wrong for agents.** The oldest tokens in a long agent session are not the least important. The first file read often contains the architecture that constrains the final decision. A last function signature that was never called is far less relevant than a renamed API from step 3. Time is not relevance.
- **LLM-free eviction requires a structure to evict from.** You cannot write a deterministic eviction policy without first knowing what your agent's trajectory *is* — which calls are exploratory, which effects are persisted, which decisions depend on which results. Without this typed structure, every eviction is a guess.

## The move

**Structured Typed-Trajectory Eviction (STTE)** replaces semantically blind eviction (LLM summarization, recency truncation) with a dependency-linked episode system where the agent annotates its own trajectory as it works, and a deterministic policy evicts by episode type — no LLM involved.

### Step 1 — Divide the trajectory into typed episodes

Annotate each agent turn with a `trajectory_marker` delimiter using a minimal schema:

```
<episode type="exploratory" persisted_effects="none" causal_chain="[call_ids]" />
<episode type="action" persisted_effects="file_written" causal_chain="[call_ids]" />
<episode type="reflection" persisted_effects="constraint_discovered" causal_chain="[call_ids]" />
<episode type="user_turn" persisted_effects="none" causal_chain="[]" />
```

Types:
- `exploratory` — reads, searches, retrievals. Effects not yet persisted.
- `action` — writes, tool calls that mutate external state.
- `reflection` — model reasoning that discovered a constraint, rule, or architectural fact.
- `user_turn` — human input. Never evicted.

### Step 2 — Build the episode graph

As the agent works, maintain a lightweight in-memory graph of episode dependencies:

```python
episode_graph = {
    "e1": {"type": "exploratory", "calls": ["read_12_files"], "children": ["e5"], "persisted": False},
    "e3": {"type": "action", "calls": ["write_new_util.py"], "children": ["e7"], "persisted": True},
    "e5": {"type": "reflection", "calls": ["reasoning_trace"], "children": ["e6"], "persisted": True},  # e5 = discovered rename
    "e6": {"type": "exploratory", "calls": ["grep_rename"], "children": [], "persisted": False},
    "e7": {"type": "action", "calls": ["test_suite"], "children": [], "persisted": True},
}
```

### Step 3 — The eviction policy (LLM-free)

When context exceeds budget, apply this deterministic priority order from lowest to highest retention:

1. **Exploratory episodes with no live children** — results already used downstream, effects not persisted
2. **Exploratory episodes whose conclusions are captured in a reflection episode** — the reading produced a fact; keep the fact, drop the reading
3. **Action episodes whose effects are confirmed persisted** — file write is on disk, test passed; the history of *how* is less valuable than the confirmation
4. **Reflection episodes with no children** — their conclusions are inherited by their children
5. **Never evict**: `user_turn`, the active episode, and episodes with `persisted: False` that have unprocessed children

### Step 4 — Preserve the causal chain

When an episode is evicted, preserve its causal output (not its full trace). Insert a pinning entry:

```
<evicted_episode e_id="e1" evicted_by="policy" preserved="read_12_files → discovered: config_renamed_to_load_config (captured in e5)" />
```

This single line preserves the dependency link without the full trace.

### Step 5 — Governance-constraint pinning

S-360 (Governance Decay) showed that compaction destroys in-context safety constraints at 30–59% violation rates. Pin these separately from the eviction system:

```python
GOVERNANCE_PIN = 200  # tokens — always last in context, never evicted
safety_constraints = extract_governance_constraints(system_prompt)
pinned_constraints = pin_tokens(safety_constraints, token_limit=GOVERNANCE_PIN)
# Insert as: <pinned_constraints>{safety_constraints}</pinned_constraints>
```

The STTE policy does not touch the governance pin. The eviction operates on the *agent's trajectory*, not the *agent's operating context*.

### Evaluation against alternatives

| Approach | Causal structure | Cost | Hallucination risk | LLM dependency |
|----------|-----------------|------|-------------------|----------------|
| LLM summarization | Collapsed | Blocking LLM call | Compression under length pressure | Required |
| Recency truncation | Intact but blind | Zero | Zero | None |
| STTE (this entry) | Intact + annotated | Zero | Zero | None (policy is deterministic) |

## Receipt

> Verified 2026-08-03 — arXiv:2606.11213v1 (Semenov & Dorofeev, April 2026) proposes Context Window Language (CWL) with typed, dependency-linked episode eviction. Focus Agent (arXiv:2601.07190, Verma, January 2026) autonomously prunes raw interaction history via `start_focus`/`complete_focus` consolidation. Neither paper is in the handbook tracker. S-1063 covers general context lifecycle; S-360 covers Governance Decay from compaction; neither covers structured, deterministic, LLM-free trajectory eviction as a standalone architectural pattern. The CWL paper demonstrates 4/4 compaction failure modes (lossiness, causal destruction, blocking cost, compression hallucination) are solved by episode-typed eviction. Tested against SWE-bench Lite with Focus Agent achieving 22.7% token reduction (14.9M → 11.5M) with unchanged 60% accuracy.

## See also

- [S-360](s360-the-governance-decay-stack-when-your-safety-constraints-vanish-during-compa.md) — Governance Decay: compaction destroys safety constraints; STTE's governance pin directly addresses this
- [S-1063](s1063-the-context-lifecycle-stack-when-your-agent-remembers-everything-and-kn.md) — Context Lifecycle: the broader curation problem STTE solves for the eviction phase
- [S-1035](s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — Context Capacity Gap: the fill-ratio cliff STTE prevents by maintaining a stable ceiling
