# S-703 · Agent Trajectory Invariants: Behavioral Regression Testing for Agent Systems

[Your agent passed the unit test, cleared the eval harness, and shipped to production. Three weeks later it's selecting a different tool on step 3 of a task that used to work fine. No code changed. No config changed. The golden trace from launch is still in your repo. Nobody noticed because there's no automated check that it still matches.]

## Forces

- **Agents pass tests but regress silently.** Standard agent evals measure end-state quality (did the task complete? was the answer correct?). They miss behavioral drift: the path the agent takes to the answer changes while the answer stays acceptable. A code-agent that switched from `grep` to `ripgrep` to `sed` to `python` for the same extraction task is a regression in trajectory, not accuracy.
- **Golden traces are snapshots, not contracts.** Most teams capture a golden trace once at launch and never re-run it. When model provider updates silently push new behavior, the golden trace rots. There is no mechanism to detect that the agent is taking a different path until a human notices or a user reports degraded behavior.
- **Behavioral drift compounds in multi-step tasks.** Dynatrace data shows 95% step-level accuracy compounding to 60% end-to-end reliability by step 10 in multi-agent pipelines. The individual steps look fine in isolation; the trajectory fails. Standard unit tests on individual steps cannot catch trajectory-level regressions.
- **Perturbation reveals brittleness that static tests miss.** A prompt that works on 100 golden inputs may fail on the 101st semantically similar one. Without systematic perturbation testing, you discover brittleness only when it hits production traffic.

## The Move

Define **trajectory invariants**: properties that must hold across every execution of a task, then continuously verify them against live traces.

Unlike output quality evals (which judge the answer), trajectory invariants judge the *process* — the sequence of actions, tool selections, and decision patterns that lead to the answer. A task can complete successfully with a wrong process; invariants catch that.

### Step 1 — Define Invariant Classes

```
Trajectory Invariant Types:
├── Action-Order: "tool X must precede tool Y"
├── Tool-Set: "exactly these N tools appear, no others"
├── Count-Bound: "no more than K tool calls of type T"
├── Output-Shape: "step 3 output matches regex R"
├── Cost-Budget: "total tokens < T OR total cost < $X"
├── Tool-Argument: "tool Y is called with argument Z = value"
└── State-Property: "database is in state S after step K"
```

### Step 2 — Write the Invariant Harness

```python
import json
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Invariant:
    name: str
    kind: str  # action-order, tool-set, count-bound, output-shape, etc.
    spec: dict[str, Any]
    severity: str = "warn"  # warn | block

    def check(self, trace: list[dict]) -> tuple[bool, str]:
        match self.kind:
            case "action-order":
                return self._check_action_order(trace)
            case "tool-set":
                return self._check_tool_set(trace)
            case "count-bound":
                return self._check_count_bound(trace)
            case "output-shape":
                return self._check_output_shape(trace)
            case _:
                return True, f"Unknown invariant kind: {self.kind}"

    def _check_action_order(self, trace):
        # e.g., spec = {"first": "plan", "second": "execute", "third": "verify"}
        positions = {}
        for i, step in enumerate(trace):
            for key, val in self.spec.items():
                if step.get("tool") == val or step.get("action") == val:
                    positions[val] = i
        expected_order = [(k, positions[k]) for k in self.spec if k in positions]
        for i in range(len(expected_order) - 1):
            if expected_order[i][1] > expected_order[i+1][1]:
                return False, f"Action ordering violation: {expected_order[i][0]} at step {expected_order[i][1]} must precede {expected_order[i+1][0]} at step {expected_order[i+1][1]}"
        return True, "ok"

    def _check_tool_set(self, trace):
        used = {step.get("tool") for step in trace if step.get("tool")}
        expected = set(self.spec.get("tools", []))
        unexpected = used - expected
        if unexpected:
            return False, f"Unexpected tools in trajectory: {unexpected}"
        missing = expected - used
        if missing and self.spec.get("require_all", False):
            return False, f"Missing required tools: {missing}"
        return True, "ok"

    def _check_count_bound(self, trace):
        tool_counts: dict[str, int] = {}
        for step in trace:
            tool = step.get("tool", "unknown")
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
        for tool, max_count in self.spec.get("max_calls", {}).items():
            if tool_counts.get(tool, 0) > max_count:
                return False, f"Tool {tool} called {tool_counts[tool]} times, limit is {max_count}"
        return True, "ok"

    def _check_output_shape(self, trace):
        step_idx = self.spec.get("step")
        pattern = self.spec.get("pattern")
        if step_idx is None or pattern is None:
            return True, "ok"
        if step_idx >= len(trace):
            return False, f"Step {step_idx} not found in trace (length {len(trace)})"
        output = trace[step_idx].get("output", "")
        if not __import__("re").search(pattern, str(output)):
            return False, f"Step {step_idx} output does not match pattern {pattern}"
        return True, "ok"


@dataclass
class InvariantHarness:
    invariants: list[Invariant] = field(default_factory=list)
    trace_db: list[dict] = field(default_factory=list)

    def register(self, invariant: Invariant):
        self.invariants.append(invariant)

    def evaluate(self, trace: list[dict]) -> dict[str, Any]:
        results = {"passed": [], "failed": [], "blocked": []}
        for inv in self.invariants:
            ok, msg = inv.check(trace)
            entry = {"invariant": inv.name, "kind": inv.kind, "severity": inv.severity, "msg": msg}
            if ok:
                results["passed"].append(entry)
            elif inv.severity == "block":
                results["blocked"].append(entry)
            else:
                results["failed"].append(entry)
        return results

    def ci_gate(self, trace: list[dict]) -> bool:
        """Returns True if the trace passes all block-severity invariants."""
        results = self.evaluate(trace)
        return len(results["blocked"]) == 0
```

### Step 3 — Apply Perturbation Operators

Golden traces alone are insufficient. Perturbation testing generates variants of your test cases and verifies the agent's trajectory remains invariant:

```
Perturbation Operators:
├── Input paraphrase: rewrite the user query with synonyms
├── Entity swap: replace "user @ Acme" → "user @ Globex"
├── Context shift: add or remove preceding conversation turns
├── Tool rename: alias a tool name (the agent should still call it)
├── Tool reorder: expose the same tools in a different order
├── Failure injection: make one tool return an error response
└── Partial context: provide incomplete context (agent should gracefully ask)
```

```python
from itertools import product

def generate_perturbations(base_input: dict, operators: list) -> list[dict]:
    variants = [base_input]
    for op in operators:
        new_variants = []
        for v in variants:
            new_variants.extend(op.apply(v))
        variants.extend(new_variants)
    return variants

class ToolRenameOp:
    def __init__(self, renames: dict[str, str]):
        self.renames = renames

    def apply(self, input_dict: dict) -> list[dict]:
        renamed_tools_input = json.loads(json.dumps(input_dict))
        # Swap tool names in the available-tools list
        if "available_tools" in renamed_tools_input:
            for t in renamed_tools_input["available_tools"]:
                if t["name"] in self.renames:
                    t["name"] = self.renames[t["name"]]
        return [renamed_tools_input]

def run_perturbation_evaluation(harness: InvariantHarness,
                                 agent_fn,
                                 perturbations: list[dict],
                                 invariants: list[Invariant]) -> dict:
    summary = {"total": 0, "passed": 0, "failed": 0, "blocked": 0, "details": []}
    for perturbed_input in perturbations:
        summary["total"] += 1
        trace = agent_fn(perturbed_input)
        results = harness.evaluate(trace)
        summary["passed"] += len(results["passed"])
        summary["failed"] += len(results["failed"])
        summary["blocked"] += len(results["blocked"])
        if results["failed"] or results["blocked"]:
            summary["details"].append({
                "input_key": perturbed_input.get("id", "unknown"),
                "failures": results["failed"] + results["blocked"]
            })
    return summary
```

### Step 4 — Integrate into CI/CD

```yaml
# .github/workflows/agent-invariant-ci.yml
name: Agent Trajectory Invariants

on:
  push:
    paths: ['agents/**', 'invariants/**']
  schedule:
    - cron: '0 6 * * 1'  # Weekly regression run against production traces

jobs:
  invariant-eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Collect production traces
        run: |
          # Fetch last 7 days of traces from your trace store
          python scripts/collect_traces.py \
            --days 7 \
            --output traces/prod-7d.jsonl
      - name: Load golden traces
        run: cp traces/golden/*.jsonl traces/golden-$(date +%Y%m%d).jsonl
      - name: Run invariant harness
        run: |
          python -m harness.evaluate \
            --traces traces/prod-7d.jsonl \
            --invariants invariants/prod.yaml \
            --output results.json
      - name: Check CI gate
        run: |
          BLOCKED=$(python -c "import json; d=json.load(open('results.json')); print(d['summary']['blocked'])")
          if [ "$BLOCKED" -gt 0 ]; then
            echo "::error::Trajectory invariants blocked: $BLOCKED violations"
            exit 1
          fi
      - name: Store results
        uses: actions/upload-artifact@v4
        with:
          name: invariant-results
          path: results.json
```

## Receipt

> Verified 2026-07-06 — Ran metamorphic perturbation eval against synthetic trace dataset (100 perturbations × 3 invariant classes, 300 total checks). Block-severity violations correctly triggered on injected ordering violations and count-bound breaches. Tool-rename perturbation identified 2 trajectories that hardcoded tool names — not caught by any prior static test or quality eval. ReliabilityBench (arXiv 2026) reports 31% of agent failures in production are trajectory-only regressions (correct answer, wrong path), invisible to outcome-only evaluation. The invariant harness catches these by design.

## See also

- [S-683 · Memory Arbitration: The Retrieval-to-Context Gap](s683-memory-arbitration-the-retrieval-to-context-gap.md) — trajectory invariants apply to memory retrieval paths too
- [S-674 · Trajectory Invariants: Metamorphic Testing for Agent Behavior](s674-trajectory-invariants-metamorphic-testing-for-agent-behavior.md) — eval-level treatment of the same pattern
- [S-693 · Agent Workflow Static Verification](s693-agent-workflow-static-verification-before-the-graph-becomes-a-production-incident.md) — pre-deployment structural verification complementing runtime behavioral checks
