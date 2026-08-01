# S-1951 · The Trace-Harness Attribution Stack — When Failure Lives in the Trace but the Fix Lives in the Harness

Your agent failed. The trace shows exactly which tool call went wrong, which step drifted, which context was retrieved. You have the evidence. So why does fixing it take three days of guessing? Because the failure lives in the trace, but the fix lives in the harness — and the two are structurally disconnected.

This is the trace-harness attribution problem: LLM agents depend on harnesses (runtime infrastructure for tools, context, orchestration, verification, and governance), but when a trajectory fails, there's no principled way to map the failure evidence in the trace back to the harness layer that caused it. Teams either patch the wrong layer or write overly broad changes that fix one failure and break three others.

## Forces

- **Traces are evidence; harnesses are code.** Execution traces capture runtime behavior in natural language — a tool was called with the wrong parameters, the wrong tool was selected, the context was stale. Harness implementations are defined in static artifacts — prompt templates, tool definitions, routing logic, verification functions. These two views have no explicit alignment, so diagnosis stays qualitative.
- **The most common fix is the most wrong fix.** When teams can't attribute failures precisely, they reach for the bluntest instrument: a prompt change. This addresses the symptom (the model chose wrong) without addressing the cause (the harness didn't constrain or guide the choice correctly). It also introduces regression risk — the same prompt serves other tasks.
- **Scoped repairs require layered diagnosis.** A failure can originate in any harness layer: context delivery, tool interface design, verification logic, or orchestration routing. Getting the layer wrong means the repair won't hold. Getting it right requires treating failed trajectories as structured evidence, not just post-mortem artifacts.
- **Harness modifications accumulate invisible debt.** Without attribution, teams make harness changes reactively. After 50 such changes, the harness has 50 micro-couplings to specific task behaviors — it's now overfit to its eval suite and fragile to distribution shift. The harness needs the same systematic diagnosis that production services get from SRE teams.

## The move

**Build a trace-to-harness attribution layer.** The idea (from HarnessFix, arXiv:2606.06324, Chen et al., Chinese Academy of Sciences, Jun 2026) is to compile execution traces and harness code into a shared intermediate representation (HTIR: Harness-aware Trace Intermediate Representation) that explicitly links each trajectory step to the harness artifact that governed it. Failures can then be attributed to specific harness layers with provenance and control-flow context.

The attribution taxonomy has four layers:

| Layer | What it governs | Common failure mode |
|---|---|---|
| **Context** | Memory retrieval, prompt assembly, token budget | Stale or missing context causes mis-reasoning |
| **Tool Interface** | Tool descriptions, parameter schemas, selection routing | Ambiguous tool names → wrong tool; bad params → tool error |
| **Verification** | Step-level checks, output validation, rollback triggers | Missing verification → bad state propagates silently |
| **Orchestration** | Next-step routing, loop termination, task decomposition | Wrong routing → agent loops or gives up |

The repair workflow:
1. **Collect failed trajectories** — run agent on eval set, isolate failures
2. **Compile to HTIR** — normalize trace + harness code into linked IR
3. **Attribute failures** — map each failed step to responsible harness layer
4. **Consolidate into flaw records** — recurring attributions become actionable issues
5. **Generate scoped repair** — layer-specific patch with regression guard

```python
# Minimal trace-harness attribution sketch
from dataclasses import dataclass
from typing import Optional

@dataclass
class TrajectoryStep:
    step_id: int
    action: str          # "tool_call", "reason", "retrieve", "verify"
    target: str          # which tool/context/verification
    outcome: str         # "success", "failure", "drift"
    harness_ref: Optional[str] = None  # which harness artifact governed this

@dataclass
class HarnessLayer:
    name: str            # "context" | "tool_interface" | "verification" | "orchestration"
    artifact: str       # file or prompt resource that governs this layer
    flaw_signature: str  # pattern that indicates this layer is responsible

# Attribution: link each failed step to the harness layer that governed it
def attribute_failure(step: TrajectoryStep, harness_defs: dict) -> HarnessLayer:
    if step.action == "retrieve":
        return harness_defs["context"]
    elif step.action == "tool_call":
        return harness_defs["tool_interface"]
    elif step.action == "verify":
        return harness_defs["verification"]
    elif step.action == "route":
        return harness_defs["orchestration"]
    else:
        return harness_defs["unknown"]  # must be diagnosed manually

# Flaw record: deduplicate recurring attribution patterns
class FlawRecord:
    def __init__(self, layer: HarnessLayer, signature: str, frequency: int):
        self.layer = layer
        self.signature = signature
        self.frequency = frequency  # how many trajectories share this flaw
        self.repair_scope: list[str] = []

    def scoped_repair(self) -> list[str]:
        """Return specific harness changes to address this flaw class."""
        if self.layer.name == "tool_interface":
            return ["normalize_tool_descriptions()",
                    "add_parameter_constraints()",
                    "add_tool_example_shots()"]
        elif self.layer.name == "context":
            return ["refresh_memory_ttl()",
                    "increase_retrieval_recency_weight()"]
        elif self.layer.name == "verification":
            return ["add_step_verification_gate()",
                    "add_rollback_trigger()"]
        elif self.layer.name == "orchestration":
            return ["tighten_routing_prompt()",
                    "add_loop_bound()"]
        return []

# Benchmark: HarnessFix results (arXiv:2606.06324)
RESULTS = {
    "SWE-Bench Verified": {"before": 45.0, "after": 57.0, "delta": "+12.0pp"},
    "Terminal-Bench 2.0 Verified": {"before": 38.2, "after": 58.3, "delta": "+20.1pp"},
    "GAIA": {"before": 41.0, "after": 55.0, "delta": "+14.0pp"},
    "AppWorld": {"before": 33.0, "after": 49.8, "delta": "+16.8pp"},
}
```

**Start simpler if you don't have HTIR.** Even without formal IR compilation, you can get 80% of the value:

- **Tag every trace step with its governing harness artifact.** Add a `harness_ref` field to your trace schema. Every tool call → tool definition file. Every context fetch → memory prompt. Every verification → verification function name.
- **Build a failure attribution log.** After each incident, classify the failed trajectory step by layer. After 20 incidents, you'll see which layer dominates your failure budget.
- **Apply targeted fixes by layer.** Context failures → improve retrieval prompts. Tool failures → tighten descriptions and parameter schemas. Verification failures → add step-level gates. Don't reach for a prompt change when the tool interface is the culprit.
- **Write regression tests per layer.** When you fix a tool interface failure, add a test case that specifically exercises that tool's description/parameter edge cases. This prevents overfitting the harness to the eval set.

## Receipt

> Verified 2026-08-01 — Primary source: HarnessFix (arXiv:2606.06324v1, Chen et al., Institute of Software CAS, Jun 2026, revised Jul 2026). SWE-Bench Verified: 45.0% → 57.0% (+12pp). Terminal-Bench 2.0: 38.2% → 58.3% (+20.1pp). GAIA: 41.0% → 55.0% (+14pp). AppWorld: 33.0% → 49.8% (+16.8pp). The paper introduces HTIR, a Harness-aware Trace Intermediate Representation that links trajectory steps to harness artifacts. Benchmark harness available at researcher's GitHub (check arXiv page). Real-world practitioner applicability: the four-layer taxonomy and the `harness_ref` tagging approach are implementable with any existing tracing system (OpenTelemetry + a mapping table) without waiting for formal IR tooling.

## See also

- [S-1000 · The Eval Gap Stack](stacks/s1000-the-eval-gap-stack-when-your-eval-suite-passes-but-production-fails.md) — the eval suite problem that trace attribution feeds into
- [S-997 · The Agent Observability Stack](stacks/s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — trace-as-post-mortem misses the verification-in-trace pattern this entry addresses
- [S-1239 · The Runtime Verification Loop](stacks/s1239-the-runtime-verification-loop-inline-agent-step-verification-at-production-scale.md) — the verification layer in the four-layer taxonomy
- [S-1005 · AI SRE](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — SRE discipline for attributing failures to system layers, applied to the agent stack
