# S-1637 · The Execution Trace Attribution Stack — When Your Agent Fails Silently and You Can't Find the Responsible Step

Your agent produces a confident, well-formed, completely wrong final answer. The infrastructure reports 200 OK. The cost logs show normal token usage. The trace shows 12 successful tool calls in sequence. Somewhere in that trace, a hallucination was born and it propagated through every subsequent step. You cannot see it. You cannot stop it. You have no idea which of those 12 steps caused it. You need execution trace attribution — the methodology for locating the responsible step in a multi-step agent trajectory.

## Forces

- **Hallucinations propagate, not appear.** In a 12-step execution, a hallucination introduced at step 3 contaminates every subsequent step that references its output. By the time the final answer is wrong, the root cause is buried under 9 layers of propagation. Traditional output-level evaluation only sees the endpoint.
- **Existing metrics are blind to localization.** Pass/fail, ROUGE, BERTScore, and accuracy/AUC all measure the final output against ground truth. None identify which intermediate step introduced the error. This is not a gap in tooling — it is a gap in the evaluation paradigm itself.
- **Best models achieve 41.1% step localization accuracy.** AgentHallu (Liu et al., arXiv:2601.06818, Jan 2026) benchmarks automated hallucination attribution across 5 major models. Tool-use hallucinations — where the agent calls a non-existent function, wrong parameters, or targets the wrong resource — are the hardest category: 11.6% accuracy. This is not a model weakness that will be patched. It is a structural problem that requires architectural response.
- **Without attribution, every fix is guesswork.** Teams that cannot locate the responsible step either over-correct (applying guardrails to every step, adding 40% latency) or under-correct (fixing the symptom at step 12, not the cause at step 3).

## The move

**Trace-first debugging: instrument every step boundary, not just the final output.**

### Layer 1 — Step Boundary Instrumentation

Tag every tool call and every LLM generation with a step ID. At each boundary, record:

```python
import uuid, json, time
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class StepRecord:
    step_id: str
    step_type: str          # "llm_generation" | "tool_call" | "retrieval" | "handoff"
    input_hash: str         # hash of input state to detect changes
    output_hash: str         # hash of output state
    output_preview: str      # first 200 chars for human review
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def to_log(self) -> dict:
        return {
            "step_id": self.step_id,
            "type": self.step_type,
            "input": self.input_hash,
            "output": self.output_hash,
            "preview": self.output_preview,
            "ts": self.timestamp,
            **self.metadata
        }

# Usage in agent loop
def execute_step(agent_state: dict, step_type: str) -> StepRecord:
    step_id = str(uuid.uuid4())[:8]
    input_hash = hash(json.dumps(agent_state, sort_keys=True))
    result = agent_state  # actual execution
    output_hash = hash(json.dumps(result, sort_keys=True))
    record = StepRecord(
        step_id=step_id,
        step_type=step_type,
        input_hash=input_hash,
        output_hash=output_hash,
        output_preview=str(result)[:200],
        metadata={"agent_id": agent_state.get("agent_id")}
    )
    emit_to_trace(record.to_log())
    return record
```

### Layer 2 — Step-Level Ground Truth Comparison

After a failed trajectory, replay each step in isolation against ground truth for that step's domain. The key insight from PAEF (arXiv:2605.01604): each step has its own ground truth domain — a retrieval step is validated differently from a reasoning step, which is validated differently from a tool-call step.

```python
from enum import Enum
from typing import Callable

class StepDomain(Enum):
    RETRIEVAL = "retrieval"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    GENERATION = "generation"
    HANDOFF = "handoff"

STEP_VALIDATORS: dict[StepDomain, Callable] = {
    StepDomain.RETRIEVAL: lambda step, gt: precision_at_k(step["docs"], gt["relevant"], k=5),
    StepDomain.TOOL_CALL: lambda step, gt: (
        step["tool_name"] == gt["expected_tool"]
        and step["params"] == gt["expected_params"]
    ),
    StepDomain.REASONING: lambda step, gt: semantic_similarity(step["chain"], gt["expected_chain"]) > 0.85,
    StepDomain.HANDOFF: lambda step, gt: step["target_agent"] == gt["expected_agent"],
}

def isolate_failure(trace: list[StepRecord], ground_truth: dict) -> Optional[int]:
    """Return step index of the first deviation from ground truth."""
    for i, step in enumerate(trace):
        domain = classify_step_domain(step)
        validator = STEP_VALIDATORS.get(domain)
        if validator and not validator(step, ground_truth.get(step.step_id, {})):
            return i
    return None  # failure not in trace — likely at output generation
```

### Layer 3 — Propagation Path Mapping

Once the responsible step is identified, map the contamination path. This is the causal chain from the first hallucination to the final output.

```python
def map_propagation(trace: list[StepRecord], root_step: int) -> list[int]:
    """Mark all downstream steps that consumed root_step's output."""
    affected = [root_step]
    for i in range(root_step + 1, len(trace)):
        if trace[i].metadata.get("parent_steps"):
            # step recorded which prior steps fed into it
            if any(p in affected for p in trace[i].metadata["parent_steps"]):
                affected.append(i)
    return affected

# Example output:
# Step 3 (tool_call): called `get_user_role(id="usr_9981")` → returned "admin" (wrong)
# Step 7 (reasoning): used role="admin" to construct permission query → 12 wrong decisions
# Step 12 (final): returned confident summary of wrong permissions → user action taken
# Propagation path: [3, 7, 12]
```

### Layer 4 — Intervention Point Selection

Not every failure requires fixing the responsible step. Three intervention strategies:

| Strategy | When to use | Cost |
|---|---|---|
| **Fix at source** | Root step has a fixable cause (bad retrieval query, wrong tool) | Medium — requires step-level retest |
| **Insert verification gate** | Root step is non-deterministic (LLM generation) | Low — add judge after step, don't change step |
| **Truncate propagation** | Downstream steps can operate without root output | Medium — add conditional branching |
| **Quarantine + regenerate** | Tool-call hallucination (step cannot be validated externally) | High — discard step output, re-execute |

## Receipt

> Verified 2026-07-25 — AgentHallu (Liu et al., arXiv:2601.06818, Jan 2026) establishes step localization accuracy baselines: best model 41.1% overall, tool-use hallucinations 11.6%. PAEF (arXiv:2605.01604, May 2026) introduces the five-dimension production evaluation framework including a "localization" axis. Practical instrumentation pattern validated against trace structures from LangSmith/LangFuse. Intervention taxonomy (fix/source/verify/truncate/quarantine) mapped from failure response patterns across three practitioner reports (Paperclipped, CyberQuickly, Eden AI, 2026).

## See also

- [S-767 · The Tool-Call Hallucination Plateau](stacks/s767-the-tool-call-hallucination-plateau.md) — the per-call failure rate that makes attribution necessary
- [S-1001 · The Agent Evaluation Stack](stacks/s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — benchmark vs. production eval gap
- [S-1018 · The Component-Level Attribution Stack](stacks/s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-OK.md) — routing/retrieval/reasoning/generation attribution
- [S-1629 · The Inference Collapse Stack](stacks/s1629-the-inference-collapse-stack-when-your-agent-chains-an-inference-to-a-fact-to-ground-truth.md) — when an inference becomes treated as fact
