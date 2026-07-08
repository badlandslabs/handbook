# S-746 · Agentic Memory Confabulation — The Self-Reinforcing False Belief Problem

Your agent failed a task. It reflected on the failure, stored the lesson, and did better next time — except it didn't. The lesson it stored was wrong. The agent believes its own incorrect diagnosis so firmly that it ignores the environment resetting to a correct state. Three trials later, it's still acting on a false belief it generated itself. This is not hallucination. This is not memory poisoning. This is confabulation — and it survives resets.

## Forces

- **Self-reflection assumes self-diagnosis is accurate.** Reflexion-style agents (Shinn et al., 2023) write natural-language reflections after failure and retrieve them in later trials. The architecture assumes the agent correctly identified why it failed. That assumption breaks systematically — especially in environments with partial observability or ambiguous success criteria — Prakhar Dixit et al., "Honest Lying: Understanding Memory Confabulation in Reflexive Agents," arXiv:2605.29463, ICML 2026 Workshop
- **Hallucination is one-shot; confabulation is multi-trial.** A hallucination is a single-generation error corrected by grounding. Confabulation is written, stored, retrieved, and acted upon — the false content gets a vote in every future decision. A hallucination the model generates once and discards is cheap. A hallucination the model stores as a "lesson learned" and acts on for 20 trials is catastrophic — Lin et al., "A Survey on Long-Term Memory Security in LLM Agents," arXiv:2604.16548, June 2026
- **The environment resets; the memory doesn't.** In iterative agent settings (ALFWorld, code agent trials), the physical/task state resets correctly each trial. The agent's belief state does not. After three trials of acting on a false reflection, the agent is fighting the correct environment with incorrect priors — Dixit et al., ALFWorld experiments: 0 of 121 reflections correctly identified the failure target in frozen environments
- **Confidence in false reflections is uncorrelated with accuracy.** The agent stores reflections it writes with high confidence. There is no internal mechanism that flags "this diagnosis might be wrong." The very act of generating the reflection increases the agent's confidence in it — a metacognitive illusion specific to self-referential memory — Dixit et al.
- **Confabulation is invisible to standard eval.** Unit tests, trajectory evals, and benchmark scores measure whether the agent succeeds on the current task. They don't measure whether the agent is succeeding for the right reasons. An agent can score well on benchmarks while operating on a fundamentally wrong model of the problem.

## The move

**Detect confabulation before it compounds.**

### The diagnostic: trial-zero reflection test

Run a probe trial before trusting any self-reflection. After a failure:

1. Agent generates its failure reflection and stores it
2. Reset the environment to a known-correct state
3. In a fresh trial, retrieve only that reflection and act on it
4. Does the agent succeed? If yes, the reflection was accurate. If no — the reflection is confabulated and must be discarded

```python
def trial_zero_probe(agent, task_env, failed_trajectory):
    """
    Probe whether a stored reflection is a genuine lesson or confabulation.
    """
    reflection = agent.generate_reflection(failed_trajectory)
    agent.store(reflection, metadata={"probe": True})

    # Reset environment to ground truth
    env_reset = task_env.reset_to_known_state()
    agent.session_memory.clear()  # wipe working memory
    agent.retrieve_reflections(query=task_env.goal, top_k=1)

    # Execute with ONLY the stored reflection as guidance
    result = agent.run(task_env.goal)

    if result.success:
        # Reflection is grounded — keep it
        agent.persist_reflection(reflection, verdict="grounded")
    else:
        # Confabulation detected — discard and log
        agent.discard_reflection(reflection)
        agent.log_confabulation(reflection, result, failed_trajectory)
        # Fall back to programmatic failure signal extraction
        programmatic_signal = extract_failure_signal_programmatically(
            failed_trajectory, task_env.state
        )
        agent.store(programmatic_signal, metadata={"verdict": "programmatic"})

    agent.clear_probe_state()
    return result


def extract_failure_signal_programmatically(trajectory, env_state):
    """
    Replace open-ended self-diagnosis with structured failure signal extraction.
    The RRR (Retrieve, Reflect, Revise) paper shows this raises correct object
    identification from 0% to 86% and reduces confabulation rate from 0.64 to 0.10.
    """
    # Extract trajectory-level failure signals programmatically
    # Instead of "why did I fail?" — use structured checks:
    failure_type = classify_failure(trajectory, env_state)
    if failure_type == "wrong_object":
        return {"signal": "wrong_object_interaction", "constraint": "verify_object_identity_before_action"}
    elif failure_type == "out_of_order":
        return {"signal": "action_order_violation", "constraint": "recheck_prerequisites"}
    elif failure_type == "missing_step":
        return {"signal": "incomplete_plan", "constraint": "decompose_before_executing"}
    return {"signal": "unknown", "constraint": "human_escalate"}
```

### Production detection: belief-state drift monitoring

Track the agent's stated beliefs about task structure across trials. If beliefs drift without corresponding environmental change, flag confabulation risk:

```python
def monitor_belief_drift(agent, task_id, window=10):
    """
    Flag when agent's belief-state diverges from environment state.
    """
    beliefs = agent.get_belief_snapshot(task_id)  # extracted from memory
    env_truth = task_env.get_fact_state(task_id)

    drift_score = semantic_distance(beliefs, env_truth)
    if drift_score > CONFABULATION_THRESHOLD:
        alert(
            f"Belief drift detected on {task_id}: "
            f"agent believes {beliefs}, environment is {env_truth}"
        )
        # Trigger trial-zero probe before next trial
        schedule_probe(agent, task_id)
```

### The prevention stack

| Layer | Mechanism | Prevents |
|-------|-----------|----------|
| Probe before persist | Trial-zero test on every new reflection | Confabulation entry |
| Programmatic over reflective | Structured failure signal extraction replaces open-ended diagnosis | Diagnosis confabulation |
| Belief-state monitoring | Track belief vs. env divergence across trials | Silent confabulation creep |
| Confidence decoupling | Do not store reflections written with low-token-evidence (e.g., <50 tokens of reasoning) | Low-evidence confabulation |
| Memory versioning | Tag reflections with the trial number and env hash | Retroactive blame and rollback |

## Receipt

> Verified 2026-07-07 — arXiv:2605.29463 (Dixit, Kamal, Oates) provides empirical evidence: in ALFWorld frozen environments, 0 of 121 open-ended reflections correctly identified the failure target. After applying RRR with programmatic signal extraction, correct object mention rose from 0% to 86% and the confabulation rate (RRR) dropped from 0.64 to 0.10. The same pattern appears in HumanEval. arXiv:2604.16548 (Lin et al., June 2026) frames the threat through the memory lifecycle lens: confabulation is a write-path failure, not a read-path failure — the agent's own generation is the contamination source. Mem0.ai's memory poisoning post (June 22, 2026) independently documents the "model hallucination written back to memory becomes a self-reinforcing failure" pattern as a known production concern.

## See also

- [S-459 · Cross-Session Memory Poisoning](s459-cross-session-memory-poisoning.md) — confabulation is the unintentional twin; both survive session resets, but poisoning is adversarial injection vs. self-generated corruption
- [S-303 · Agentic Memory: From Stateless to Stateful Agents](s303-agentic-memory-from-stateless-to-stateful-agents.md) — the memory architecture that makes confabulation possible
- [S-641 · Environment-Injected Memory Poisoning (eTAMP)](s641-environment-injected-memory-poisoning-etamp.md) — the injection path that bypasses the confabulation/reality boundary
- [S-378 · Entity Grounding: Knowledge Graphs as Verifiable Memory](s378-entity-grounding-knowledge-graphs-as-verifiable-memory.md) — a grounding layer that can catch entity-level confabulation before it compounds
