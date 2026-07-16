# S-1026 · The PAEF Stack — When Your Benchmark Says Pass but 4 Out of 7 Failure Modes Sneaked Past

Your agent scores 94% on your test suite. Three weeks into production, you discover it has been misrouting access requests, hallucinating tool calls it never actually made, and failing silently on 18% of tasks. The benchmark caught none of this — because the benchmark was measuring the wrong things. This is not an eval coverage problem. It is a **measurement-validity problem**: standard metrics are blind to the failure modes that matter most in production agentic systems.

## Forces

- **Episodic benchmarks evaluate isolated decisions; production compounds them.** A single good decision in step 3 can be followed by a cascade of errors in steps 4–8. Lab benchmarks score each step independently and miss the propagation. ROUGE, BERTScore, accuracy, and AUROC — the four workhorses of LLM evaluation — were designed for static text comparison, not trajectory evaluation. They detect neither error propagation nor cascading failures.
- **Standard metrics miss 4 of 7 production failure modes entirely.** In a 2026 empirical study (Pandey, arXiv:2605.01604) across billion-event-scale systems, ROUGE, BERTScore, Accuracy, and AUROC failed to detect hallucinated tool calls, silent completion claims, tool failure cascades, and capability-state drift. The other 3 modes (compounding decision errors, overcommitment failures, and explainability attribution errors) were detected only with significant lag — multiple evaluation cycles after the failure had already caused harm.
- **A single benchmark score is a point-in-time snapshot; production systems drift continuously.** Model weight updates, prompt template changes, data distribution shifts, and user behavior evolution all change what "correct" means over time. A 94% score from last month does not describe the system you have today.
- **Production stakes are real and irreversible.** A wrong answer on a benchmark is a penalty point. A wrong access decision in production is a compliance violation. A hallucinated tool call in production is a phantom action that downstream systems treat as real. The failure threshold in production is categorically different from the lab.
- **LLM-as-judge has its own calibration problem.** The judge model can fail in ways that correlate with the thing being judged — a model prone to verbosity will score verbose agent outputs higher. Without kappa-adjusted inter-rater reliability, you do not know whether your judge is measuring quality or itself.

## The Move

Use the **Production Agentic Evaluation Framework (PAEF)** — a five-dimension continuous evaluation system that targets the failure modes standard metrics cannot see. The framework treats agent evaluation as a continuous monitoring problem, not a periodic test problem.

### The Five PAEF Dimensions

1. **Trajectory Integrity** — Does the agent's action sequence match what it claims happened? Compare logged tool calls against actual tool outcomes. Detect hallucinated calls (agent claims it called `send_email` but the mail server log shows no delivery), skipped steps (agent reports task complete but required verification step was never invoked), and silent fallbacks (agent silently degraded to cached/stale values and reported success).
2. **Failure Cascade Propagation** — Does a failure in one step contaminate subsequent steps? Instrument every tool call with a status tag (SUCCESS, FAIL, PARTIAL, TIMEOUT). Track the conditional probability of failure in step N+1 given failure in step N. A cascade ratio > 0.3 means your error recovery is failing.
3. **Output Distribution Drift** — Has the agent's output distribution shifted without accuracy changing? Track per-dimension output statistics (response length distribution, sentiment distribution, tool call frequency distribution, error rate distribution) using population stability index (PSI). A PSI > 0.2 on any dimension triggers an investigation even if accuracy is unchanged — this catches capability-state drift before it becomes a correctness problem.
4. **Semantic Correctness Under Tool Failure** — Does the agent handle tool failures gracefully and accurately? Inject controlled tool failures (5%, 15%, 30% failure rate) into evaluation runs. Score the agent's recovery behavior: does it (a) report failure honestly, (b) attempt appropriate retry, (c) fall back to a defensible partial answer, or (d) hallucinate a success? Categories (a) and (c) are acceptable; (b) and (d) are failures.
5. **Inter-Rater Reliability of the Judge** — Can your evaluation judge reliably distinguish good from bad? Run all evaluations with two independent judges. Report Cohen's kappa alongside the score. A kappa < 0.6 means your evaluation is unreliable regardless of the score — you are measuring judge noise, not agent quality.

### The Seven Production Failure Modes (What PAEF Detects That Standard Metrics Miss)

| # | Failure Mode | Standard Metric Detection | PAEF Detection |
|---|-------------|-------------------------|----------------|
| 1 | Hallucinated Tool Calls | ROUGE/BERTScore: misses silently — output looks fine | Trajectory Integrity: compares claim vs. log |
| 2 | Silent Completion Claims | Accuracy: false 100% on phantom completion | Trajectory Integrity: explicit completion verification |
| 3 | Tool Failure Cascades | AUROC: detected only after 3+ cycles lag | Failure Cascade Propagation: real-time cascade ratio |
| 4 | Capability-State Drift | Accuracy: gradual drift invisible as snapshot | Output Distribution Drift: PSI on output dimensions |
| 5 | Compounding Decision Errors | All standard metrics: lag > 2 cycles | Trajectory Integrity + Cascade Propagation |
| 6 | Overcommitment Failure | ROUGE: misses semantic overreach | Semantic Correctness: partial-credit scoring |
| 7 | Explainability Attribution Error | All standard metrics: invisible | Inter-Rater Reliability: judge calibration |

### Shadow Mode: Enable Before You Enforce

Before routing PAEF scores to any automated gate, run in shadow mode for 7 days: log trajectory integrity violations, cascade ratios, and PSI values without blocking or alerting. This establishes your baseline — every system has a baseline rate of hallucinated calls and cascade events. Blocking on raw PAEF scores without a baseline produces false alarms that train your team to ignore the monitoring.

```python
# Minimal PAEF instrumentation (shadow mode)
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np
import json

@dataclass
class ToolEvent:
    step: int
    tool_name: str
    claimed: bool   # agent says it called this tool
    actual: bool   # tool actually executed
    status: str    # SUCCESS | FAIL | PARTIAL | TIMEOUT
    latency_ms: float

class PAEFMonitor:
    def __init__(self, psi_threshold: float = 0.2, cascade_threshold: float = 0.3):
        self.psi_threshold = psi_threshold
        self.cascade_threshold = cascade_threshold
        self.events: list[ToolEvent] = []
        self.output_distributions: dict[str, list[float]] = defaultdict(list)

    def record(self, event: ToolEvent, output_length: float | None = None):
        self.events.append(event)
        if output_length is not None:
            self.output_distributions["response_length"].append(output_length)

    def trajectory_integrity(self) -> dict:
        """Detect hallucinated calls and silent completion claims."""
        hallucinated = sum(1 for e in self.events if e.claimed and not e.actual)
        silent = sum(1 for e in self.events if e.actual and e.status != "SUCCESS" and e.claimed)
        total = len(self.events) or 1
        return {
            "hallucinated_call_rate": hallucinated / total,
            "silent_failure_rate": silent / total,
            "PASS": hallucinated == 0 and silent == 0
        }

    def cascade_ratio(self) -> dict:
        """Measure whether failures propagate to the next step."""
        failures = [e for e in self.events if e.status != "SUCCESS"]
        if len(failures) < 2:
            return {"cascade_ratio": 0.0, "PASS": True}
        cascading = sum(
            1 for i in range(len(failures) - 1)
            if failures[i + 1].step == failures[i].step + 1
        )
        ratio = cascading / (len(failures) - 1)
        return {"cascade_ratio": ratio, "PASS": ratio < self.cascade_threshold}

    def psi_drift(self, current_window: list[float], baseline: list[float]) -> dict:
        """Population Stability Index on any output dimension."""
        def psi(buckets: np.ndarray, expected: np.ndarray, actual: np.ndarray) -> float:
            expected += 1e-6; actual += 1e-6  # avoid div/0
            return float(np.sum((actual - expected) * np.log(actual / expected)))
        bins = np.linspace(min(baseline + current_window), max(baseline + current_window), 11)
        expected = np.histogram(baseline, bins=bins)[0] / len(baseline)
        actual = np.histogram(current_window, bins=bins)[0] / len(current_window)
        psi_val = psi(bins[:-1], expected, actual)
        return {"psi": psi_val, "drifted": psi_val > self.psi_threshold}

    def report(self, baseline_output_lengths: list[float] | None = None) -> dict:
        ti = self.trajectory_integrity()
        cr = self.cascade_ratio()
        report = {
            "trajectory_integrity": ti,
            "cascade_ratio": cr,
            "total_events": len(self.events),
        }
        if baseline_output_lengths:
            dist = self.output_distributions.get("response_length", [])
            if len(dist) >= 30:
                report["output_drift"] = self.psi_drift(dist, baseline_output_lengths)
        return report
```

### The Kappa Gate: Never Deploy Without Judge Reliability

Before acting on any PAEF score, check kappa:

```python
def kappa_gate(judge1_scores: list[int], judge2_scores: list[int], min_kappa: float = 0.6) -> dict:
    from collections import Counter
    n = len(judge1_scores)
    Po = sum(a == b for a, b in zip(judge1_scores, judge2_scores)) / n
    labels = set(judge1_scores + judge2_scores)
    Pe = sum(
        (sum(s == l for s in judge1_scores) / n) * (sum(s == l for s in judge2_scores) / n)
        for l in labels
    )
    kappa = (Po - Pe) / (1 - Pe) if (1 - Pe) != 0 else 1.0
    return {
        "kappa": round(kappa, 3),
        "reliable": kappa >= min_kappa,
        "action": "trust_scores" if kappa >= min_kappa else "recalibrate_judge"
    }
```

A kappa < 0.6 means the judge cannot reliably distinguish a passing run from a failing one. Recalibrate the judge prompt, try a stronger model as judge, or switch to deterministic output validation for that dimension.

## See also

- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — eval system architecture; PAEF is the production-layer complement
- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — drift detection; PAEF's Output Distribution Drift dimension formalizes this
- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — semantic failure detection; PAEF's Trajectory Integrity catches the same ghost completions
