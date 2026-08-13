# S-2561 · The ETCLOVG Harness Layering Stack: When Your Trace Says Failed but You Cannot Find Where

Your agent failed. You have the full trace — every tool call, every LLM response, every step. You scan it twice. You cannot find where it went wrong. This is not a reading problem. It is a **harness anatomy problem**: you are looking at the wrong layers.

When an LLM agent fails in production, the failure lives in one of seven harness layers. Treating the harness as a monolith — the way most teams do — means you diagnose symptom by symptom and fix in circles. The ETCLOVG taxonomy (Execution, Tooling, Context, Lifecycle, Observability, Verification, Governance) gives you a map.

## Forces

- **The harness is where every real failure hides.** Models are evaluated in single-pass benchmarks. Production agents run multi-step loops through tool interfaces, stateful environments, and governance policies. The gap between benchmark and production lives in the harness, not the model.
- **"It failed" is not a diagnosis.** Failed traces show you that something went wrong. They do not show you which layer caused it. A tool that returns silently corrupted JSON, a context window that quietly drops the first half of a conversation, a termination policy that never fires — all look like "the agent failed."
- **Layer confusion makes fixes backfire.** A team adds a verification layer to fix a context problem. A governance patch breaks an observability hook. Without layer-level attribution, you are guessing which wrench to throw at which pipe.
- **170+ open-source tools map to these layers — yet most teams treat the harness as a black box.** A 2026 survey mapped over 170 agent-harness projects across the seven layers. The tooling exists. The mental model to use it systematically does not.

## The move

### The seven layers (ETCLOVG)

Map every piece of code outside your model prompt to one of these seven layers. When a failure occurs, narrow your search.

| Layer | What it owns | Common failure mode |
|---|---|---|
| **Execution** | Safe, isolated, reproducible environments (VMs, containers, sandboxes) | Environment state leakage between runs; privilege escalation via sandbox escape |
| **Tooling** | Tool descriptions, schemas, invocation interfaces, MCP/A2A protocols | Tool schema drift; mismatched parameter names; hallucinated tool calls |
| **Context** | What gets sent to the LLM: history, documents, retrieved results, system prompt | Silent context truncation; outdated retrieved facts treated as current; context pollution from prior turns |
| **Lifecycle** | Step sequencing, loop management, termination criteria | Infinite loops; premature exit; missing retry loops on recoverable errors |
| **Observability** | Tracing, logging, metric emission, span structure | Silent failures with 200-OK logs; observability hooks fire after the data you need |
| **Verification** | Output validators, LLM-as-judge gates, type checks, schema enforcement | Weak gates that pass bad outputs; expensive synchronous checks that slow critical paths |
| **Governance** | Safety policies, budget limits, compliance rules, kill switches | Overly permissive policies that let dangerous actions through; fail-open governance |

### Three-step diagnosis protocol

When a trace fails, run this before touching anything else:

**Step 1 — Trace to HTIR.** Convert the raw trace into **Harness-aware Trace Intermediate Representation (HTIR)**: a normalized log that annotates each trace step with which ETCLOVG layer owns it. This is not just a formatting exercise — it forces you to assign ownership. A step that spans two layers (e.g., a tool call whose output feeds a context update) gets annotated with both.

**Step 2 — Pinpoint the implicated layer.** For each failed trace, attribute the failure to one or more specific ETCLOVG layers. Common attributions:
- Tool returns wrong type → **Tooling**
- Agent acts on stale data → **Context**
- Agent loops forever → **Lifecycle**
- No log entry for the failure → **Observability**
- Dangerous action passes through → **Governance**
- Corrupted state between runs → **Execution**
- Output looks right but is semantically wrong → **Verification**

**Step 3 — Scoped repair, layer by layer.** Apply the smallest fix to the implicated layer only. Do not patch the prompt to compensate for a tool schema error. Do not add a governance rule to compensate for a missing verification gate. Each layer has its own repair operator; using the wrong one produces invisible coupling.

### Consolidation before repair

Single failed executions are noise. Before writing a fix, consolidate diagnoses across N runs (N ≥ 5 for production agents). Group by implicated ETCLOVG layer, then merge records within each group that share the same root cause. The result is a **flaw record**: a recurring pattern, not a one-off glitch.

### Validation gate

After applying a fix, run the patched harness against the original failing task + a regression suite before shipping. The goal is zero regressions across all previously-passing cases, not just the one you just fixed.

```python
# Minimal HTIR annotation sketch
def annotate_trace_step(step, layers):
    """Annotate each trace step with ETCLOVG layer ownership."""
    return {
        "step_id": step["id"],
        "layer": layers.get(step["type"], "unknown"),
        "evidence": step["output"],
        "implicated": _diagnose_layer(step)
    }

def diagnose_failed_trace(trace, threshold=5):
    """Consolidate failed traces into layer-level flaw records."""
    records = [annotate_trace_step(s, LAYER_MAP) for s in trace["steps"]]
    by_layer = group_by_layer(records)
    return {
        layer: merge_root_causes(records)
        for layer, records in by_layer.items()
    }
```

## Receipt
> Verified 2026-08-13 — arXiv 2606.06324v2 (June 4, 2026; revised July 2, 2026): "From Failed Trajectories to Reliable LLM Agents: Diagnosing and Repairing Harness Flaws." TrueFoundry ETCLOVG survey (2026). Tested on: SWE-Bench (+15.2–50.0% held-out improvement), Terminal-Bench, GAIA, AppWorld. HTIR + layer attribution reduced broad prompt-only fixes by 73% in benchmark runs.

## See also
- [S-996 · The Harness Matters More Stack](/stacks/s996-the-harness-matters-more-stack-when-your-model-isnt-the-problem.md) — the production gap problem this taxonomy solves
- [S-1013 · The Trace Replay Harness](/stacks/s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — reproducing failures before layer-level diagnosis
- [S-1018 · The Component-Level Attribution Stack](/stacks/s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-OK.md) — attribution across independent components
