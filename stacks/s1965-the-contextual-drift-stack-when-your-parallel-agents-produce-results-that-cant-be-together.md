# S-1965 · The Contextual Drift Stack — When Your Parallel Agents Produce Results That Can't Be Together

*When three agents run in parallel on sub-tasks of the same goal. Agent A sees version 3.2 of the shared spec. Agent B sees 3.1. Agent C was given the original 3.0 and built its entire implementation around assumptions that A and B already invalidated. All three produce correct, well-reasoned outputs. The final composed system has three incompatible mental models baked in at the architecture level. This is contextual drift: not a tool failure, not a capability failure, not a communication failure — a shared-state coherence failure.*

## Forces

- **Parallel decomposition severs shared context.** When you split a task across N agents for speed, you give each agent a viewport into the shared state. Those viewports start identical and diverge over time as each agent reads, writes, and infers at different rates.
- **Agents propagate inferences, not just data.** An agent doesn't just read the spec — it forms beliefs about what the spec *means*, which other agents don't see. These inferred commitments compound silently.
- **"Correct" is scoped to the viewport.** An agent can be right about everything in its context window and still produce output that contradicts the global state. The agent has no access to the aggregate view that would reveal the conflict.
- **Version markers are not semantic markers.** A shared spec with version numbers doesn't prevent divergence if agents are also pulling from live tool state, memory stores, and RAG results — none of which carry version tags.
- **Detection happens at composition, not during execution.** The moment you try to merge outputs — merge code, merge data schemas, merge decisions — you discover the drift. By then, hours of agent work may need to be discarded.

## The move

**1. Explicit viewport contracts before decomposition.**
Before launching parallel agents, write a *viewport contract* for each: what parts of the shared state this agent may read, what it may write, and what it must treat as immutable during this run. A viewport contract is not a prompt instruction — it is a machine-readable artifact (JSON schema) that the orchestration layer enforces.

```python
# Viewport contract enforced by the orchestrator
viewport = {
    "agent_id": "agent_b",
    "read": ["spec.md@3.2", "shared_context.json"],
    "write": ["src/b_agent/output.py"],
    "immutable": ["shared_context.json"],  # read-only, no writes
    "freeze_tag": "run_2026_08_01_v3",   # all agents pin to same snapshot
    "max_inference_round": 5,
}

# Orchestrator enforces: agent B cannot read spec@3.1 or write to shared_context
```

**2. Snapshot the shared state at decomposition time.**
Every piece of shared state that agents will read — specs, context files, memory stores, RAG indexes, tool schemas — gets a snapshot tag at the moment of decomposition. All agents in the run operate against tagged snapshots, not live state. Writes go to the live state but are held for a merge-gate phase.

**3. The merge gate: verify coherence before committing.**
After parallel agents complete, run a *coherence check* before merging outputs. The coherence check asks a judge LLM: "Given agent A's output and agent B's output, are there any implicit contradictions when composed?" Include both outputs in the judge context. Flag contradictions for human review or agent-level re-coordination.

```python
import anthropic

client = anthropic.Anthropic()

def coherence_check(outputs: list[dict], shared_context_tag: str) -> dict:
    """
    Run coherence check on parallel agent outputs before merge.
    Returns {'coherent': bool, 'conflicts': list[Conflict], 'recommendation': str}
    """
    coherence_prompt = f"""You are a system integration reviewer.
Two agents completed sub-tasks in parallel. Their outputs must be composed.
Review for implicit contradictions when these outputs are combined.
Look for: incompatible assumptions about shared state, schema mismatches,
conflicting decisions based on different versions of the same source material,
and any sign that each agent was operating from a different mental model.

SHARED STATE SNAPSHOT TAG: {shared_context_tag}

AGENT OUTPUTS:
{chr(10).join(f'--- Agent: {o["agent_id"]} ---\\n{o["output"]}' for o in outputs)}

Respond with:
1. COHERENT: yes/no
2. CONFLICTS: list of specific contradictions found
3. RECOMMENDATION: merge, re-coordinate, or escalate
"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": coherence_prompt}]
    )
    return parse_coherence_response(response.content[0].text)
```

**4. The re-coordinate loop (fallback).**
If the coherence check finds conflicts, do not manually merge. Return all outputs + conflict descriptions to a coordinating agent with the instruction: "Re-coordinate these sub-tasks. Resolve the identified conflicts by issuing revised instructions to the relevant agents, then re-run only the conflicting sub-tasks."

**5. Shared inference log.**
Every agent emits an *inference log* alongside its output: a structured list of key assumptions and derived commitments it formed during execution. The merge gate reads the inference logs to catch drift that hasn't yet surfaced in the outputs themselves.

## Receipt

> Verified 2026-08-01 — Patterns drawn from: (1) multi-agent context drift research (arxiv:2605.10695, agent synchronization failures in concurrent planning systems), (2) A2A protocol task state machine analysis (terminal state asymmetry between agents), (3) production reports of parallel agent systems requiring post-hoc "integration rewrites" that consumed more time than the original parallel work saved. No single integrated open-source tool implements all five layers of this stack; the closest is a custom orchestration layer combining Pydantic viewport contracts + snapshot tagging + a coherence-check LLM call. Teams at Cloudflare and Clay report building internal versions of this.

## See also

- [S-1389 · The Reliability Compounding Stack](stacks/s1389-the-reliability-compounding-stack-when-your-multi-agent-pipeline-fails-65-percent-of-the-time.md) — sequential failure multiplication (this entry covers compositional divergence, not sequential failure)
- [S-1613 · The Multi-Agent Handoff Eval Stack](stacks/s1613-the-multi-agent-handoff-eval-stack-when-every-agent-passes-its-test-but-your-system-fails.md) — per-agent eval that misses system-level composition
- [S-1466 · The Semantic Cache Blind Spot](stacks/s1466-the-semantic-cache-blind-spot-when-identical-queries-return-different-answers.md) — cache inconsistency as a related divergence problem
- [S-281 · The A2A Context Fidelity Stack](stacks/s281-the-a2a-context-fidelity-stack-when-your-agent-hands-off-a-task-and-the-receiver-loses-the-thread.md) — A2A handoff fidelity (this entry is broader: covers parallel decomposition, not sequential handoffs)
