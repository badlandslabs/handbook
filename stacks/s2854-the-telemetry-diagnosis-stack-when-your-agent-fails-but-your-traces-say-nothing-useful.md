# S-2854 · The Telemetry Diagnosis Stack — When Your Agent Fails but Your Traces Say Nothing Useful

Your agent ran 50,000 steps last night. Zero span errors. Datadog is green. But 8% of sessions completed with wrong output — a tool returned partial JSON, an API was silently rate-limited at step 4, and the guardrail was bypassed at step 7. Your traces tell you execution happened. They tell you nothing about what went wrong, where, or why. This is the telemetry diagnosis gap: the layer between "I have logs" and "I know what broke."

## Forces

- **Traces log structure, not semantics.** A tool call that returned wrong data, a rate-limited HTTP 429, and a model that stopped mid-reasoning all produce identical span sequences. Traces answer "was there a call?" — not "was it correct?"
- **Fault type and fault location are different problems.** A context overflow and a tool misrouting produce similar symptoms (the agent stops making progress) but require different fixes. Most tooling can detect that something failed, not what kind of failure it was.
- **Baseline detection requires aligned references.** The most powerful diagnosis signal — same-input comparison against a known-good execution — requires having run the same input fault-free, which most teams never captured.
- **The diagnosis problem is harder than the fault itself.** AgentChaosBench (arXiv:2608.14680, University of Toronto, August 2026) shows that even frontier models achieve only 13.6–24.8% top-1 accuracy at identifying fault type from raw telemetry — and fault-type-plus-location drops to 22%.

## The move

The diagnosis stack has three layers. Together they close the gap between "something failed" and "here's the fault type and location."

### Layer 1 — Fault-Classified Instrumentation

Tag every execution boundary with a semantic classification layer above raw spans. Not just `tool.call`, but `tool.call[database.query]` with an expected output schema. Not just `llm.call`, but `llm.call[reasoning.answer]` with a type contract. The classification doesn't prevent failure — it makes failure legible.

```python
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Any
import time

class FaultType(Enum):
    NO_FAULT          = auto()
    TOOL_FAILURE      = auto()      # tool returned error/exception
    TOOL_LATENCY      = auto()      # tool exceeded SLA threshold
    TOOL_CORRUPTION   = auto()      # tool returned malformed/wrong-type output
    TOOL_MISROUTING   = auto()      # wrong tool called, or right tool wrong args
    CONTEXT_OVERFLOW  = auto()      # context window limit hit mid-execution
    GUARDRAIL_BYPASS  = auto()      # disallowed content passed through
    RATE_LIMIT        = auto()      # upstream API throttled
    AGENT_MISROUTING  = auto()      # agent handed to wrong agent or dead-end
    MODEL_DEGRADATION = auto()      # model output quality below baseline

@dataclass
class ExecutionSpan:
    step_id: str
    component: str           # "agent" | "tool:db" | "guardrail" | "mcp:a2a"
    operation: str            # "query" | "write" | "escalate"
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    fault_type: FaultType = FaultType.NO_FAULT
    fault_confidence: float = 0.0
    metadata: dict = field(default_factory=dict)

    def check_latency(self, sla_ms: float = 2000) -> None:
        if self.ended_at:
            elapsed = (self.ended_at - self.started_at) * 1000
            if elapsed > sla_ms:
                self.fault_type = FaultType.TOOL_LATENCY
                self.fault_confidence = min(elapsed / sla_ms, 1.0)
                self.metadata["latency_ms"] = elapsed

    def check_output_contract(self, expected_type: type, actual: Any) -> None:
        if not isinstance(actual, expected_type) and actual is not None:
            self.fault_type = FaultType.TOOL_CORRUPTION
            self.fault_confidence = 0.85
            self.metadata["expected_type"] = str(expected_type)
            self.metadata["actual_type"] = type(actual).__name__
```

### Layer 2 — Aligned Reference Traces

The single highest-signal diagnostic technique: run the same input through a shadow "golden" agent (known-good configuration) and compare execution traces. Deviations in tool call sequences, response latencies, and output structures flag the fault location.

AgentChaosBench found that aligned references improved Context Overflow recall by up to 40 percentage points versus unaligned detection — because the reference trace shows what *should* have happened at each step.

```python
from typing import Callable, Any
from difflib import unified_diff
import json

class AlignedReferenceComparator:
    """
    Run production input through both the live agent and a shadow
    golden agent. Differences in execution traces reveal fault location.
    """
    def __init__(self, golden_agent: Callable):
        self.golden = golden_agent

    def compare(
        self,
        input_payload: dict,
        live_trace: list[ExecutionSpan],
        golden_trace: list[ExecutionSpan],
    ) -> list[dict]:
        """
        Returns a list of fault-location annotations:
        {step_id, fault_type, confidence, deviation_detail}
        """
        faults = []

        # 1. Sequence divergence: live agent called different tools
        live_ops = [s.operation for s in live_trace]
        golden_ops = [s.operation for s in golden_trace]
        if live_ops != golden_ops:
            # Find first divergence
            for i, (lo, go) in enumerate(zip(live_ops, golden_ops)):
                if lo != go:
                    faults.append({
                        "step_id": live_trace[i].step_id,
                        "fault_type": FaultType.AGENT_MISROUTING,
                        "confidence": 0.90,
                        "deviation_detail": f"expected tool '{go}', got '{lo}'",
                    })
                    break

        # 2. Latency anomaly: tool that was fast in golden is slow in live
        golden_latency = {s.step_id: (s.ended_at - s.started_at)
                          for s in golden_trace if s.ended_at}
        for span in live_trace:
            if span.ended_at and span.step_id in golden_latency:
                live_lat = span.ended_at - span.started_at
                ref_lat = golden_latency[span.step_id]
                if live_lat > ref_lat * 3:  # 3× slower than reference
                    faults.append({
                        "step_id": span.step_id,
                        "fault_type": FaultType.TOOL_LATENCY,
                        "confidence": min(live_lat / (ref_lat * 10), 0.95),
                        "deviation_detail": f"live={live_lat*1000:.0f}ms vs golden={ref_lat*1000:.0f}ms",
                    })

        # 3. Output structure mismatch
        for live_span, gold_span in zip(live_trace, golden_trace):
            if live_span.fault_type != FaultType.NO_FAULT:
                faults.append({
                    "step_id": live_span.step_id,
                    "fault_type": live_span.fault_type,
                    "confidence": live_span.fault_confidence,
                    "deviation_detail": live_span.metadata,
                })

        return faults

    def generate_diff(self, live_trace: list[ExecutionSpan],
                      golden_trace: list[ExecutionSpan]) -> str:
        """Human-readable trace diff for post-mortem."""
        live_repr = json.dumps([
            {"step": s.step_id, "component": s.component, "op": s.operation,
             "fault": s.fault_type.name}
            for s in live_trace
        ], indent=2)
        gold_repr = json.dumps([
            {"step": s.step_id, "component": s.component, "op": s.operation,
             "fault": s.fault_type.name}
            for s in golden_trace
        ], indent=2)
        return "\n".join(unified_diff(
            gold_repr.splitlines(), live_repr.splitlines(),
            fromfile="golden", tofile="live", lineterm=""
        ))
```

### Layer 3 — Joint Diagnosis Pipeline

Combine Layer 1 instrumentation with an LLM-based triage model that takes the full enriched trace and produces `(fault_type, fault_location, confidence)` — but treat it as triage, not ground truth. AgentChaosBench showed that 24.8% accuracy with the best frontier model means the classifier is useful for prioritizing human review, not for automated remediation decisions.

```python
from openai import OpenAI

class TelemetryDiagnosisPipeline:
    """
    Joint fault-type + fault-location classifier over enriched traces.
    Treat output as triage priority — not automated remediation trigger.
    """
    def __init__(self, triage_model: str = "gpt-4o"):
        self.client = OpenAI()
        self.triage_model = triage_model

    def diagnose(self, execution_trace: list[ExecutionSpan],
                 golden_trace: list[ExecutionSpan] | None = None) -> dict:
        # Build enriched context from instrumented spans
        span_context = self._build_span_context(execution_trace)
        fault_summary = self._summarize_instrumented_faults(execution_trace)

        prompt = f"""You are diagnosing a production AI agent execution trace.
A fault has been detected. Your job is to identify:
1. FAULT_TYPE: one of [TOOL_FAILURE, TOOL_LATENCY, TOOL_CORRUPTION, 
   TOOL_MISROUTING, CONTEXT_OVERFLOW, GUARDRAIL_BYPASS, RATE_LIMIT, 
   AGENT_MISROUTING, MODEL_DEGRADATION, NO_FAULT]
2. FAULT_STEP: the step_id where the fault originated
3. ROOT_CAUSE: one-sentence explanation of what caused this fault

Current fault signals from instrumentation:
{fault_summary}

Execution trace (step_id → component → operation):
{span_context}

If a golden (reference) trace is available, differences are diagnostic.
Return your diagnosis in this format:
FAULT_TYPE: <type>
FAULT_STEP: <step_id>
ROOT_CAUSE: <one sentence>
CONFIDENCE: <low|medium|high>"""

        response = self.client.chat.completions.create(
            model=self.triage_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return self._parse_diagnosis(response.choices[0].message.content)

    def _build_span_context(self, trace: list[ExecutionSpan]) -> str:
        return "\n".join(
            f"  {s.step_id} | {s.component} | {s.operation} | "
            f"fault={s.fault_type.name} (conf={s.fault_confidence:.2f})"
            for s in trace
        )

    def _summarize_instrumented_faults(self, trace: list[ExecutionSpan]) -> str:
        faults = [s for s in trace if s.fault_type != FaultType.NO_FAULT]
        if not faults:
            return "  No instrumentation faults detected."
        return "\n".join(
            f"  - {s.step_id}: {s.fault_type.name} "
            f"(conf={s.fault_confidence:.2f}) — {s.metadata}"
            for s in faults
        )

    def _parse_diagnosis(self, raw: str) -> dict:
        result = {}
        for line in raw.split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                result[key.strip().lower()] = val.strip()
        return result
```

## Receipt

> Verified 2026-08-19 — AgentChaosBench (arXiv:2608.14680, August 2026, University of Toronto) provides the empirical foundation. Key findings: 5 heterogeneous agentic systems (SQL Assistant, Customer Support Bot, Code Review Agent, Meeting Scheduler, Web Scraper), 10 fault types, 250 faulty + 25 control traces. Local detectors (≤14B parameters) achieve 13.6–19.2% top-1 fault-type accuracy; frontier DeepSeek-v4-pro reaches 24.8%. Joint fault-type + location tops out at 22%. Aligned fault-free references improve Context Overflow recall by up to 40pp. GitHub: github.com/kevinzck8k/agentic-fault-diagnosis. Tian Pan's "Context Window Cliff" (April 14, 2026) documents the three distinct failure signatures of context overflow (hard truncation, soft eviction, degraded middle). Zylos Research "Agent Self-Healing" (May 6, 2026) provides the fault taxonomy and failure-mode classification.

## See also

- [S-2228 · The Reflex Stack](stacks/s2228-the-reflex-stack-when-your-traces-are-green-but-your-agent-is-looping.md) — behavioral classification of traces
- [S-2669 · The Reliability Surface Stack](stacks/s2669-the-reliability-surface-stack-when-your-agent-scores-97-percent-and-fails-one-third-of-the-time-in-production.md) — why single-run pass rates miss production failure
- [S-2082 · The Fault Injection Stack](stacks/s2082-the-fault-injection-stack-when-your-agent-works-in-staging-and-fails-in-production.md) — controlled fault injection for agent reliability testing
