# S-1566 · The Continuous Evaluation Pipeline Stack — When Your Agent Isn't as Good as It Was Last Tuesday

Your agent scored 94% on your eval suite last week. It scored 94% yesterday. But last Tuesday it correctly routed all 847 invoice disputes. Today it is systematically mishandling anything over $5,000. Your benchmark says nothing is wrong. Your users disagree. This is the core epistemic failure of agentic systems: benchmarks answer "is the agent good?" while ignoring the more consequential question — "is it still as good as it was?"

By 2026, the data is unambiguous. AgentStatus's 30-day study across 6,200+ production agents found 88% experienced measurable correctness drift within a single month. Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation, not model capability gaps. The agentic CI problem is not solved by running evals once before deploy. It requires a **continuous evaluation pipeline** — production traces feeding regression tests, CI gates blocking regressions before they ship, and automated alerting when behavioral signals diverge.

## Forces

- **Static evals measure nothing about change over time.** A 94% pass rate tells you the agent handles most cases well today. It tells you nothing about whether it handled them equally well last Tuesday. Longitudinal data — the same eval run against the same agent over time — is the missing dimension. Zylos Research documented this precisely: a Stanford/Berkeley study showed GPT-4's accuracy on a specific task dropping from 84% to 51% between March and June 2023 with no version change communicated. The model name was identical. The behavior was not.
- **Production failures are the highest-fidelity test data you have.** Arthur's research (June 2026) frames this cleanly: synthetic test suites cover what engineers imagined. Production failures reveal the long tail — ambiguous phrasings, malformed inputs, unexpected tool sequences — that no engineer would have invented. Every production failure is a regression test case waiting to be born.
- **Datadog's 2026 State of AI Engineering found 40% of production AI failures are semantic** — wrong answers returning HTTP 200 — invisible to traditional APM. Your infrastructure telemetry is green while your agent silently degrades.
- **Graduated capability evals should become regression gates.** Anthropic's evaluation methodology formalizes this: tasks that once answered "can we do this at all?" should "graduate" to a regression suite answering "can we still do this reliably?" This graduation is not automatic. It requires infrastructure.
- **The feedback loop is the product.** The operational discipline that distinguishes teams running agents reliably from those debugging silent failures is not the agent itself — it is the pipeline around it: failure → trace → test case → golden dataset → CI gate → automated rollback.

## The Move

Build a continuous evaluation pipeline with four connected stages:

### Stage 1 — Automatic Trace Capture from Production

Instrument every production session with structured trace export. Capture the full trajectory: input prompt, tool call sequence, outputs, and outcome label (success/failure where determinable). Tag sessions with metadata — task type, user segment, model version, tool schema hash — to enable segmented drift analysis.

```python
# Minimal trace capture middleware
import json
from datetime import datetime, timezone

class EvalTracer:
    def __init__(self, dataset_path: str, min_failure_rate: float = 0.01):
        self.dataset_path = dataset_path
        self.min_failure_rate = min_failure_rate

    def capture(self, session: AgentSession, outcome: str) -> None:
        trace = {
            "session_id": session.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_type": session.task_type,
            "model_version": session.model,
            "tool_schema_hash": session.tool_manifest_hash,
            "trajectory": session.trajectory,  # list of {step, tool, input, output}
            "outcome": outcome,  # "success" | "failure" | "unknown"
        }
        # Write to append-only trace log for async processing
        with open(self.dataset_path, "a") as f:
            f.write(json.dumps(trace) + "\n")

# Usage in agent loop
tracer = EvalTracer("/var/agent-traces/evals.rawl")

async def run_session(input: str, task_type: str) -> AgentResult:
    session = AgentSession(task_type=task_type)
    result = await agent.run(session, input)

    # Infer outcome from verifiable signals
    outcome = infer_outcome(result)  # DB write confirmed, API response validated, etc.
    tracer.capture(session, outcome)

    return result
```

### Stage 2 — Failure → Test Case Pipeline

Process the append-only trace log in a background job. Filter for sessions where outcome = "failure." For each, extract the input, the full trajectory, and the known-bad output. Add to a **regression candidate pool.** Deduplicate near-identical inputs (Jaccard similarity on normalized input text). Run LLM-as-judge on unlabeled sessions to surface ambiguous failures that didn't self-report.

```python
from collections import defaultdict
import hashlib

class RegressionDatasetBuilder:
    def __init__(self, trace_log: str, dataset_path: str, similarity_threshold: float = 0.85):
        self.trace_log = trace_log
        self.dataset_path = dataset_path
        self.similarity_threshold = similarity_threshold
        self.seen_hashes: dict[str, str] = {}  # hash → canonical_input

    def process(self) -> int:
        added = 0
        with open(self.trace_log) as f:
            for line in f:
                trace = json.loads(line)
                if trace["outcome"] != "failure":
                    continue

                input_hash = self._input_hash(trace["trajectory"][0]["input"])
                if input_hash in self.seen_hashes:
                    continue  # already in dataset

                self.seen_hashes[input_hash] = trace["trajectory"][0]["input"]
                test_case = {
                    "id": input_hash,
                    "input": trace["trajectory"][0]["input"],
                    "task_type": trace["task_type"],
                    "expected_trajectory": trace["trajectory"],
                    "discovered_at": trace["timestamp"],
                    "model_version": trace["model_version"],
                }
                self._append_test_case(test_case)
                added += 1

        return added

    def _input_hash(self, text: str) -> str:
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
```

### Stage 3 — CI Gate with Behavioral SLOs

Add the regression suite to your CI pipeline. Run it against every pull request and on a nightly schedule against main. Block merges if the regression pass rate drops below your SLO threshold. Use **segmented scoring** — if the regression failure is concentrated in a specific task type or model version, surface that signal rather than just a single pass/fail number.

```yaml
# .github/workflows/agent-eval.yml
name: Agent Regression Gate

on:
  pull_request:
  schedule:
    - cron: "0 2 * * *"  # nightly on main

jobs:
  regression-eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run regression suite
        env:
          AGENT_EVAL_ENDPOINT: ${{ secrets.AGENT_EVAL_ENDPOINT }}
        run: |
          python -m agent_eval.runner \
            --suite ./tests/regression/ \
            --slo-threshold 0.92 \
            --segment-by task_type \
            --output ./eval-results.json

      - name: Check SLO
        run: |
          python -c "
          import json, sys
          results = json.load(open('eval-results.json'))
          overall = results['overall_pass_rate']
          slo = results['slo_threshold']
          print(f'Overall pass rate: {overall:.1%}')
          for seg in results['segments']:
              print(f'  [{seg[\"task_type\"]}] {seg[\"pass_rate\"]:.1%} (n={seg[\"count\"]})')
          if overall < slo:
              print(f'REGRESSION DETECTED: {overall:.1%} < SLO {slo:.1%}')
              sys.exit(1)
          print('SLO MET — safe to ship')
          "

      - name: Upload regression artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-results-${{ github.run_id }}
          path: eval-results.json
```

### Stage 4 — Automated Behavioral Alert and Rollback Trigger

When nightly regression scores drop below threshold, fire an alert with the specific regression signal (which task type, which model version, how much drop). For agents with an automated rollback capability, trigger a staged response: alert → halt new sessions → rollback to last known good version → page on-call.

The **golden version set** — the known-good model + prompt + tool schema combinations — is the operational artifact that makes rollback possible. Maintain it as a first-class artifact alongside your code. Tag every successful regression run with its full environment fingerprint.

```python
class BehavioralAlert:
    def __init__(self, golden_set_path: str, rollback_endpoint: str):
        self.golden_set_path = golden_set_path
        self.rollback_endpoint = rollback_endpoint

    def evaluate_and_act(self, eval_results: dict) -> None:
        overall = eval_results["overall_pass_rate"]
        slo = eval_results["slo_threshold"]
        regression = eval_results.get("segments", [])

        if overall >= slo:
            return  # healthy

        # Identify the most degraded segment
        worst = min(regression, key=lambda s: s["pass_rate"])
        drop = slo - worst["pass_rate"]

        print(f"[ALERT] Regression detected: {worst['task_type']} "
              f"dropped {drop:.1%} (now {worst['pass_rate']:.1%}, SLO {slo:.1%})")

        # Halt new sessions for degraded task type
        self._halt_task_type(worst["task_type"])

        # Rollback to golden version for this task type
        golden = self._load_golden(worst["task_type"])
        if golden and drop > 0.05:  # >5% drop triggers rollback
            self._rollback(worst["task_type"], golden)
            print(f"[ROLLBACK] Reverted {worst['task_type']} to {golden['version_tag']}")
```

> Receipt pending — [2026-07-24] — Code examples are structural sketches demonstrating the four-stage pipeline architecture. A production receipt would require running this against a live agent with a seeded regression dataset and observing the CI gate fire on an induced regression.

## See also
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — scaffold infrastructure for agent health monitoring
- [S-1033 · The Behavioral Version Stack](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — versioning the four independently-evolving layers of an agent
- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — coordination drift in multi-agent systems
