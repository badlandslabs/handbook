# S-1946 · The MAST Framework Stack — When Your Multi-Agent System Fails But Nobody Can Tell You Why

Your 4-agent pipeline worked in the pilot. Six weeks into production, task success has dropped from 87% to 51%. No model updated. No code changed. You have logs, traces, and error rates — and you still cannot explain why the system fails. The agents are producing plausible outputs while silently breaking in ways your monitoring was never designed to catch. This is the MAST problem: a systematic failure taxonomy for multi-agent systems that most teams encounter empirically and name incorrectly.

## Forces

- **MAS fails 41-86.7% of the time in production.** Berkeley's MAST study (Cemri et al., NeurIPS 2025, arXiv:2503.13657) analyzed 200+ execution traces across 7 frameworks (MetaGPT, ChatDev, HyperAgent, OpenManus, AppWorld, Magentic, AG2). Even ChatDev — a canonical benchmark system — achieves only 33.33% correctness on the ProgramDev benchmark. High failure rates are not a signal of bad agents; they are a structural property of multi-agent coordination.

- **Standard observability catches crashes, not failure modes.** HTTP status codes, latency histograms, and token-count alerts all remained nominal during the 87%→51% degradation described above. The agents executed successfully — they produced wrong answers confidently, terminated early, repeated steps, or handed off incomplete state to the next agent.

- **The failure taxonomy has three layers.** MAST distills 14 distinct failure modes across three conversation stages: Specification Issues (41.77% of failures), Inter-Agent Misalignment (36.94%), and Task Verification (21.30%). Each layer requires a different detection and recovery strategy. Treating all three the same way — "add more logging" — solves none of them.

- **The counterintuitive insight: coordination causes failure, not capability.** Distributed systems classically gain reliability through redundancy. MAS gain capability through coordination but inherit failure modes from the coordination itself. Two capable agents working independently may succeed. Put them in a pipeline and they fail through handoffs, not through their individual reasoning.

## The Move

MAST organizes multi-agent failures into three sequential stages. Design your detection and recovery layer against each.

### Stage 1 — Specification Issues (41.77% of failures, pre-execution)

Agents fail because what they were told to do diverges from what they should do.

**Failure modes:**
- **1.1 Disobey Task Specification (17.14%)** — agent produces output that satisfies the wrong goal. Most common failure. Looks like a hallucination but is actually a goal-misalignment.
- **1.2 Disobey Role Specification (0.50%)** — agent acts outside its assigned role (e.g., the summarizer starts routing tickets).
- **1.3 Step Repetition (13.98%)** — agent loops on a step without progress. Distinct from a crash loop: the agent reports progress each time.
- **1.4 Loss of Conversation History (11.65%)** — agent's context window loses earlier turns, causing it to re-ask questions already answered.
- **1.5 Unaware of Termination Conditions (2.33%)** — agent continues past task completion, producing redundant output or corrupting downstream state.

**Detection pattern:**
```python
# Detect Step Repetition (1.3) — agent re-executing the same action
def detect_step_repetition(trace, threshold=3):
    """Flag when an agent repeats the same tool call N times."""
    action_seq = [step["tool"] for step in trace if step.get("tool")]
    for i in range(len(action_seq) - threshold + 1):
        if len(set(action_seq[i:i+threshold])) == 1:
            return {"mode": "1.3", "repetition_count": threshold,
                    "action": action_seq[i]}
    return None

# Detect Conversation History Loss (1.4) — agent re-asking answered questions
def detect_history_loss(trace):
    """Flag when agent asks a question whose answer exists in prior turns."""
    answered = {}
    for step in trace:
        if step.get("role") == "user" and "?" in step["content"]:
            q = step["content"].lower()
            # Check if a prior assistant turn answered this
            for prior in answered:
                if prior in q or q in prior:
                    return {"mode": "1.4", "question": q, "answered_as": answered[prior]}
        elif step.get("role") == "assistant" and "?" not in step["content"]:
            answered[step["content"].lower()] = step["content"]
    return None
```

**Countermeasure:** Lock task and role specifications in the orchestrator. Use schema-validated handoff contracts (see S-1013, The Multi-Agent Boundary Stack) so agents cannot silently deviate from their defined scope.

### Stage 2 — Inter-Agent Misalignment (36.94% of failures, execution)

Agents fail because they cannot coordinate correctly, even when each individual agent is functioning.

**Failure modes:**
- **2.1 Conversation Reset (7.15%)** — agent restarts the conversation with another agent, losing intermediate state.
- **2.2 Fail to Ask for Clarification (9.82%)** — agent proceeds with ambiguous input rather than requesting clarification, producing downstream errors.
- **2.3 Task Derailment (10.98%)** — agent's focus drifts from the original task during multi-step execution.
- **2.4 Information Withholding (6.82%)** — agent fails to share relevant context with collaborating agents.
- **2.5 Ignored Other Agent's Input (7.82%)** — agent produces output that contradicts or ignores a prior agent's output.
- **2.6 Reasoning-Action Mismatch (3.33%)** — agent's reasoning trace and its actual tool calls diverge (it decides to do X but calls tool for Y).

**Detection pattern:**
```python
# Detect Information Withholding (2.4) and Ignored Input (2.5)
# via handoff audit against declared dependencies
def audit_handoffs(trace, role_deps):
    """Each agent's output must reference context from its declared dependencies."""
    failures = []
    for handoff in trace.handoffs:
        src, dst = handoff["from"], handoff["to"]
        declared_context = role_deps[dst].get("requires_from", {}).get(src, [])
        for required in declared_context:
            if required not in handoff["content"]:
                failures.append({
                    "mode": "2.4",  # or "2.5" if directly contradicted
                    "dst_agent": dst, "src_agent": src,
                    "missing": required
                })
    return failures
```

**Countermeasure:** Implement explicit handoff contracts with required fields. If agent B depends on agent A's output, the orchestrator validates that required fields are present before allowing the handoff. See S-1013 (boundary stack) and S-982 (supervisor pattern).

### Stage 3 — Task Verification (21.30% of failures, post-execution)

Agents fail because they cannot tell whether their output is correct.

**Failure modes:**
- **3.1 Premature Termination (6.66%)** — agent ends the task before completion, often triggered by an earlier error it swallowed.
- **3.2 No or Incomplete Verification (1.66%)** — agent skips the verification step under time pressure or token budget constraints.
- **3.3 Incorrect Verification (9.82%)** — agent verifies its output but the verification criteria are wrong (the check passes but the answer is wrong).

**Detection pattern:**
```python
# Detect Premature Termination (3.1) — check against task contract
def detect_premature_termination(trace, task_contract):
    """Agent declared success but task contract outputs are missing."""
    produced = set(trace.completed_outputs)
    required = set(task_contract["required_outputs"])
    missing = required - produced
    if missing and trace.ended_cleanly:
        return {"mode": "3.1", "missing_outputs": list(missing),
                "declared_success": trace.final_status}
    return None
```

**Countermeasure:** Define task contracts upfront — a formal spec of what constitutes task completion — and validate against them. Do not rely on the agent to judge its own success (see S-976, The Verification Layer Stack).

### The 5-Step MAST Debugging Protocol

| Step | Action |
|------|--------|
| 1 | Establish a single stitched trace across all agents and tool calls |
| 2 | Match the failure to one of the 14 MAST modes (or the Entropy Principle silent failure variants) |
| 3 | Isolate which stage introduced the failure (pre/execution/post) |
| 4 | Apply the stage-specific countermeasure, not a generic retry |
| 5 | Validate the fix against the task contract, not against the agent's self-assessment |

Time estimate: 30-90 minutes per incident with tracing in place. The one-time investment is instrumentation.

## Receipt

> Verified 2026-08-01 — Primary source: MAST paper (arXiv:2503.13657v3, Cemri et al., Berkeley Sky Computing Lab, updated Oct 2025). Empirical data: 200+ traces across 7 frameworks, kappa=0.88 inter-annotator agreement. Distribution: Specification 41.77%, Inter-Agent 36.94%, Verification 21.30%. Entropy Principle paper (arXiv:2606.08162, June 2026) adds complementary silent failure modes: Data Consistency Decay (18.4%), Knowledge Fragmentation (15.7%), Behavior Routing Deficiency (11.9%). MAST LLM-as-judge pipeline: OpenAI o1 calibrated to kappa=0.77 with human experts. Dataset: MAD (Multi-Agent Dialogue) on HuggingFace, 1,242 items. Production context: multi-agent debugging guide (Atlan, July 2026) reports 41-86.7% failure rates across studied MAS.

## See also

- [S-986 · The Coordination Breakdown Pattern](s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — MAS coordination failure (complementary: this entry gives the taxonomy, S-986 gives the recovery strategy)
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — boundary problem (the handoff failure S-1946's Stage 2 addresses)
- [S-976 · The Verification Layer Stack](s976-the-verification-layer-when-your-agent-cant-distinguish-right-from-almost-right.md) — Stage 3 verification failures
- [S-1019 · The Three-Pillar Agent Observability Stack](s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — observability for agents
- [S-417 · Agent Failure Mode Taxonomy and Self-Healing Architecture](s417-agent-failure-mode-taxonomy-and-self-healing-architecture.md) — single-agent failure modes (S-1946 covers the multi-agent extension)
