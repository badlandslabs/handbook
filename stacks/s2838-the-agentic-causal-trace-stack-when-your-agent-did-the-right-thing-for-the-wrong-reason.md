# S-2838 · The Agentic Causal Trace Stack — When Your Agent Did the Right Thing for the Wrong Reason

When your agent succeeds on a task, you assume the reasoning that got there was sound. It wasn't. And you won't know until the context shifts slightly and the same flawed reasoning produces a confident, catastrophic failure.

## Forces

- **Success masks bad process.** Existing attribution research focuses on failure — identifying where the agent broke after it produced a bad outcome. But the more dangerous case is the agent that reaches correct answers through unreliable reasoning, then fails silently when the context shifts.
- **Correct outcomes ≠ correct reasoning.** arXiv:2601.15075 (Qian et al., Shanghai AI Lab / Renmin U. / NUS, Feb 2026) establishes that agents frequently exhibit *internal causal misalignment* — correct actions driven by flawed internal states (incorrect beliefs, misaligned goals, spurious correlations). The outcome is right; the mechanism is wrong.
- **The why matters more than the what for drift detection.** If you only log what the agent did, you can't detect the reasoning drift that precedes behavioral drift. You need to reconstruct the internal causal chain, not just the tool call sequence.
- **Hierarchical reasoning makes attribution harder.** Modern agents use multi-step planning, self-reflection, and tool-use reasoning loops. Blaming a single step for an eventual failure misses the upstream causal fork where a misaligned belief took root.

## The Move

### Causal Attribution vs. Failure Attribution

Failure attribution (S-1018) answers: *which component broke?* Causal attribution answers: *why did the agent make this decision, given its internal state at that moment?* The distinction matters because a correctly-functioning agent can still act for wrong reasons.

### The AgentDoG Framework

Qian et al. (2026) propose **AgentDoG** — a hierarchical framework for general agentic attribution that identifies internal causal drivers regardless of task outcome. The core architecture:

```
Action → Internal State Trace → Causal Fork Identification → Attribution Report
```

Key components:
- **Behavior decomposition** — separate the externally observable action from the internal reasoning state that produced it
- **Counterfactual reasoning** — if the agent had held a different belief at this step, would the action have changed? If yes, that belief is causal
- **Hierarchical attribution** — attribute causality up through planning layers, not just tool-call layers

```python
# Simplified causal trace extraction
def extract_causal_trace(agent_trace):
    """
    agent_trace: list of (step, reasoning_state, action, outcome)
    Returns: list of (causal_fork, attributed_reasoning, confidence)
    """
    causal_forks = []
    for i, (step, reasoning, action, outcome) in enumerate(agent_trace):
        # Counterfactual check: would action change if reasoning_state changed?
        counterfactual_reasoning = generate_alternative_reasoning(reasoning)
        counterfactual_action = simulate_agent_action(counterfactual_reasoning)

        if counterfactual_action != action:
            causal_forks.append({
                'step': step,
                'driver': reasoning,  # the actual causal driver
                'counterfactual_driver': counterfactual_reasoning,
                'confidence': measure_causal_strength(reasoning, action)
            })
    return causal_forks
```

### What to Log Beyond Tool Calls

Standard agent traces log: step number, tool calls, tool results, final output.

Add:
- **Reasoning state snapshots** — the model's generated reasoning before each tool call (requires `thinking` traces or CoT logging)
- **Belief anchors** — key facts the agent cited as justification for the action
- **Causal fork flags** — moments where the agent's reasoning cited a source or assumption that, if wrong, would invalidate the action

### Detection: The Silent Drift Pattern

```
Run 1: Task A → correct output
Run 2: Task A' (slight context shift) → same reasoning pattern → WRONG output
```

The agent's reasoning was always brittle — it produced correct outputs by coincidence on Run 1. Causal trace analysis would have flagged the reasoning as low-confidence or belief-anchored on a fragile premise.

### Integration with Existing Stacks

| Stack | Connection Point |
|-------|-----------------|
| S-1018 (Component Attribution) | S-1018 finds which component broke; causal trace finds *why the reasoning that drove it was flawed* |
| S-1009 (RCA) | RCA post-mortem needs causal trace data as input — without it, you're guessing |
| S-1047 (Dead Letter Queue) | Dead-letter entries should include causal fork flags for triage prioritization |
| S-1029 (Eval Harness) | Eval harnesses that log only pass/fail miss the silent-correct-but-wrong-reasoning case |

## Receipt

> Verified 2026-08-18 — arXiv:2601.15075 (AgentDoG, Qian et al., Feb 2026) provides the primary framework. Core claim: existing attribution focuses on failed trajectories; causal attribution applies regardless of outcome. GitHub: AI45Lab/AgentDoG (Llama-3.1-70B-Instruct backbone). Key insight from paper: the internal causal misalignment problem — correct actions from incorrect internal states — is not captured by any existing evaluation benchmark.

## See also
[S-1018](s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-OK.md) · [S-1009](s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) · [S-1047](s1047-the-agentic-dead-letter-queue-when-your-agent-fails-mid-task-and-the-task-just-disappears.md)
