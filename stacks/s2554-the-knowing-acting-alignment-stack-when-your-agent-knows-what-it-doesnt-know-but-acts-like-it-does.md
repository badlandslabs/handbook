# S-2554 · The Knowing-Acting Alignment Stack — When Your Agent Knows What It Doesn't Know But Acts Like It Does

Your agent handles a user request: "What's the weather in Tokyo right now?" It responds confidently with a weather description. There was no tool call. The training data is from 2024. The answer is wrong, but the agent produced it without hesitation. This is not hallucination — the model knows what it knows. It is a *knowing-acting misalignment*: the agent's metacognitive judgment (knowing whether it needs a tool) is decoupled from its execution (the tool call that would confirm the answer). The knowing-acting alignment stack is the set of patterns that close this gap — making an agent's self-knowledge predictive of its behavior, not just its text.

## Forces

- **Standard agent benchmarks measure pass rates, not knowing-acting alignment.** AgentBench, GAIA, and WebArena score task completion. They don't measure whether the agent knew it should reach for a tool before it acted on parametric memory. An agent can score 89% and still systematically bypass necessary tools.
- **LLMs are better at knowing than at acting on knowing.** KAPRO (Knowing-Acting Quadrant PRObe, Li et al., 2026) shows that frontier models correctly predict tool necessity ~70% of the time in isolation — but only act on that prediction ~50% of the time in execution. The metacognitive judgment exists; it doesn't drive the behavior.
- **Tool over-calling is as expensive as tool under-calling.** A conservative agent that calls a weather API for every question creates cost and latency without accuracy benefit. The goal is predictive tool use — calling tools when needed, not calling them blindly.
- **The knowing-acting gap compounds in multi-step tasks.** A 10-step agent that misjudges tool necessity at step 2 will spend steps 3-9 building on a wrong foundation. The error isn't a single wrong answer — it's a cascade that a metacognitive checkpoint could have aborted.

## The Move

**1. Probe for knowing-acting alignment before evaluating pass rate.**
Use KAPRO-style metacognitive probes to measure whether the agent can predict tool necessity before tool use. The KAPRO framework separates the Knowing quadrant (can the agent predict when a tool is needed?) from the Acting quadrant (does it call the tool?). Run these as separate eval dimensions — pass rate is insufficient.

```python
from dataclasses import dataclass
from enum import Enum

class KAQuadrant(Enum):
    KNOWS_NEEDS_TOOL   = "knows_needs_tool"      # Correct metacognitive judgment
    KNOWS_NO_TOOL      = "knows_no_tool"         # Correctly skips tool
    ACTS_WITH_TOOL      = "acts_with_tool"        # Tool called in execution
    ACTS_WITHOUT_TOOL  = "acts_without_tool"      # Tool not called in execution

@dataclass
class KAPROResult:
    task_id: str
    tool_required: bool

    # Knowing: what the agent predicted before acting
    predicted_need_tool: bool

    # Acting: what the agent actually did
    called_tool: bool

    @property
    def quadrant(self) -> KAQuadrant:
        if self.tool_required and self.predicted_need_tool and self.called_tool:
            return KAQuadrant.KNOWS_NEEDS_TOOL  # Ideal: correct judgment, correct action
        if not self.tool_required and not self.predicted_need_tool and not self.called_tool:
            return KAQuadrant.KNOWS_NO_TOOL       # Ideal: correct skip
        if not self.tool_required and self.called_tool:
            return KAQuadrant.ACTS_WITH_TOOL      # Over-call: wasted tool
        # tool_required=True but did not call, OR predicted correctly but didn't act
        return KAQuadrant.ACTS_WITHOUT_TOOL       # Under-call: parametric hallucination risk

# Run metacognitive probe before execution
def kapro_probe(agent, task: str) -> KAPROResult:
    # Ask: "Before using any tools, do you know this answer from training?"
    probe_prompt = f"""
Task: {task}
Before calling any tools, answer:
1. Do you already know the answer from your training data? (yes/no)
2. Is a live tool call required for accuracy? (yes/no)
Then execute the task normally.
"""
    probe_response = agent.ask(probe_prompt)  # Separate call, not part of task execution
    prediction = parse_tool_prediction(probe_response)  # {needs_tool: bool}

    actual_call = agent.execute_task(task)  # Real execution

    return KAPROResult(
        task_id=task,
        tool_required=prediction["ground_truth_tool_needed"],
        predicted_need_tool=prediction["needs_tool"],
        called_tool=actual_call.tool_was_called,
    )

# Aggregate alignment score across task set
def alignment_score(results: list[KAPROResult]) -> dict:
    quadrants = [r.quadrant for r in results]
    knowing_correct = quadrants.count(KAQuadrant.KNOWS_NEEDS_TOOL)
    knowing_correct += quadrants.count(KAQuadrant.KNOWS_NO_TOOL)
    acting_correct = quadrants.count(KAQuadrant.KNOWS_NEEDS_TOOL)
    acting_correct += quadrants.count(KAQuadrant.KNOWS_NO_TOOL)

    return {
        "knowing_accuracy": knowing_correct / len(results),   # Metacognitive accuracy
        "acting_accuracy": acting_correct / len(results),     # Behavioral accuracy
        "alignment_gap": knowing_correct / len(results) - acting_correct / len(results),
        "overcall_rate": quadrants.count(KAQuadrant.ACTS_WITH_TOOL) / len(results),
        "undercall_rate": quadrants.count(KAQuadrant.ACTS_WITHOUT_TOOL) / len(results),
    }
    # A healthy agent: alignment_gap < 0.10, undercall_rate < 0.05
```

**2. Instrument a knowing-acting gate into the agent loop.**
Insert a lightweight metacognitive checkpoint before tool execution. The agent predicts tool necessity — if the prediction confidence is below threshold and the task involves real-time facts, force a tool call regardless of the model's inclination to answer from memory.

```python
class KnowingActingGate:
    def __init__(self, agent, knowing_threshold=0.7, force_tool_types=None):
        self.agent = agent
        self.knowing_threshold = knowing_threshold
        self.force_tool_types = force_tool_types or {"search", "api", "database", "web"}

    def run(self, task: str) -> str:
        # Step 1: Metacognitive probe (separate, no cost计入 in main loop)
        probe = self.agent.probe(f"Do you need a live tool for: {task}?")
        needs_tool_prob = probe.confidence  # 0.0 - 1.0

        # Step 2: Predict
        will_use_tool = needs_tool_prob >= self.knowing_threshold
        tool_type = self._classify_tool_need(task)

        # Step 3: Gate decision
        forced_tool = (
            tool_type in self.force_tool_types
            and needs_tool_prob < self.knowing_threshold
        )

        if will_use_tool or forced_tool:
            return self.agent.execute_with_tools(task, required=forced_tool)
        else:
            return self.agent.execute_from_memory(task)

    def _classify_tool_need(self, task: str) -> str:
        # Lightweight classifier: real-time → tool required
        real_time_signals = ["current", "now", "today", "live", "latest", "price", "weather"]
        return "tool" if any(s in task.lower() for s in real_time_signals) else "none"
```

**3. Track the KAPRO dashboard in production, not just in eval.**
The knowing-acting gap isn't a one-time calibration — it's a production signal. Monitor undercall rate per task type, especially for queries involving recency, geography, or specificity. Alert when undercall rate exceeds 5% for a given tool category.

**4. Use KAS (Knowing-Action Consistency) as your primary health metric.**
KAPRO introduces KAS = P(acts_with_tool | knows_needs_tool) + P(acts_without_tool | knows_no_tool) / 2. A KAS score near 1.0 means the agent's self-knowledge drives its behavior. Scores below 0.7 signal systematic misalignment requiring prompt or architecture changes.

## Receipt

> Receipt pending — 2026-08-13 — KAPRO framework (arXiv:2606.20661, Li et al., June 2026) establishes the knowing-acting taxonomy. KAS metric defined in the paper. Code pattern above is an architectural reconstruction — production implementation requires integration with your eval harness and trace collection pipeline. Run KAPRO probes on your agent's task distribution to establish baseline knowing/acting accuracy before applying the gate.

## See also

- [S-1291 · The Failure Ceiling](stacks/s1291-the-failure-ceiling-when-your-agent-cant-tell-its-stuck-and-the-system-has-no-brake.md) — agents that can't detect their own stuck state; knowing-acting gap in the failure domain
- [S-1602 · The Metacognitive Handoff Stack](stacks/s1602-the-metacognitive-handoff-stack-when-your-agent-knows-its-about-to-fail-and-asks-for-help-before-it-destroys-value.md) — metacognition for uncertainty; extends the knowing framework to failure prediction
- [S-1773 · The Capability Trust Layer](stacks/s1773-the-capability-trust-layer-stack-when-your-agent-network-trusts-languages-not-facts.md) — capability self-description in multi-agent networks; the knowing problem at the ecosystem level
