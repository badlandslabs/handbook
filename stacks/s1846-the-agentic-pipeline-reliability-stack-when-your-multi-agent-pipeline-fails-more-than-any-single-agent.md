# S-1846 · The Agentic Pipeline Reliability Stack — When Your Multi-Agent Pipeline Fails More Than Any Single Agent

Four specialized agents. Each tested individually at 85% reliability. The pipeline connects them in sequence: triage → research → draft → review. You expect ~85% overall. You get 52%. No single agent crashed. No tool failed. The pipeline is doing exactly what it was designed to do. This is the pipeline reliability gap — and it is not a model problem.

## Situation

You have a production agent pipeline: a triage agent routes incoming requests, a research agent fetches and synthesizes data, a drafting agent produces structured output, and a review agent validates quality before delivery. Each agent passes its unit tests. Each tool call succeeds. And yet, running them in sequence produces catastrophic failure rates that none of the isolated components predict.

This is not a prompting problem. It is an architectural one. The pipeline reliability gap is the gap between what each agent can do independently and what the system of agents can do together. Closing it requires treating the *connections* between agents as first-class engineering concerns — with the same rigor you apply to the agents themselves.

## Forces

- **Per-call failure compounds at pipeline scale.** At 15% per-call failure (production median for tool-use agents, AgentMarketCap, 2026), four sequential calls produce a 52% failure rate before retry logic: `(1 - 0.15)⁴ = 0.52`. Benchmarks test one agent. Pipelines test the system.
- **Validation lag is invisible.** Agents execute ahead of validation by design — it's what makes them fast. But this means every downstream agent builds on unchecked assumptions. A wrong retrieval doesn't raise an error; it produces a confident synthesis that reads plausibly.
- **Partial failures have ambiguous signatures.** A tool call that returns valid JSON with semantically wrong content looks identical to a success from the orchestrator's perspective. The model has no error code for "correct structure, wrong answer."
- **Retries don't help when the failure is in the input.** If the research agent's output is wrong, retrying the draft agent produces a more polished wrong answer. Retry with the same bad context compounds the problem.
- **Isolation makes debugging worse, not better.** Breaking the pipeline into specialized agents improves modularity and reduces cognitive load. It also means the point of failure is always one layer upstream from where you notice it.

## The move

Separate execution from validation at every pipeline boundary. Treat each handoff as a contract, each contract as testable, and each test as a gate.

### 1. Hardened Pipeline Gates

Every agent-to-agent handoff runs through a validation gate before the downstream agent starts. The gate is not part of either agent — it is infrastructure:

```python
class PipelineGate:
    def __init__(self, upstream: Agent, downstream: Agent, validator: Callable):
        self.upstream = upstream
        self.downstream = downstream
        self.validator = validator  # schema check, semantic check, or both

    def execute(self, input_state: dict) -> dict:
        raw_output = self.upstream.run(input_state)
        validation_result = self.validator(raw_output)

        if not validation_result.is_acceptable:
            return self._handle_rejection(raw_output, validation_result)

        # Pass validated output to downstream
        return self.downstream.run(validation_result.validated_output)

    def _handle_rejection(self, raw_output: dict, result: ValidationResult):
        # Route back to upstream with specific rejection signal
        return self.upstream.revise(raw_output, result.rejection_reason)
```

The gate implements three behaviors: pass through on success, reject with a specific signal on failure, and route to revision on partial success. Critically, the gate has its own timeout separate from both agents — a validation that hangs indefinitely is itself a failure mode.

### 2. Three-Tier Validation per Gate

Not all validation costs the same. Match the validation depth to the downstream stakes:

- **Schema gate (cheap):** Does the output conform to the expected structure? JSON schema validation adds microseconds and catches the most common failure mode: the agent returns a valid object with the wrong fields.
- **Semantic gate (moderate):** Does the output make sense given the input? A lightweight LLM call — or a rules-based heuristic — checks factual consistency at the claim level. "The report cites a date from the future" or "the cited figure contradicts the source document" are catchable.
- **Execution gate (expensive):** Can the downstream agent actually use this output? Run a dry-run or smoke test — pass the output through the downstream agent's first step and verify it produces a valid next-step input. Expensive, but catches the failures that schema and semantic gates miss.

In practice, most gates need only the schema tier. Reserve execution gates for high-stakes handoffs (draft → approval, research → external synthesis).

### 3. Checkpointing with Structural Snapshots

Pipeline reliability requires resumability. When a gate rejects output and the upstream agent revises, you need to restart from the checkpoint — not from scratch:

```python
@dataclass
class PipelineCheckpoint:
    stage: str                    # "triage" | "research" | "draft" | "review"
    input_state: dict             # Original input to this stage
    validated_output: dict        # Last validated output from this stage
    revision_count: int           # How many times this stage has revised
    accumulated_context: list     # Pruned history for context efficiency

MAX_REVISIONS = 3
MAX_PIPELINE_STAGES = 6

def run_pipeline_with_checkpoints(stages: list[PipelineGate], input_state: dict):
    checkpoints = {}
    current_state = input_state

    for i, gate in enumerate(stages):
        checkpoint_key = f"stage_{i}_{gate.upstream.name}"
        revision = 0

        while revision < MAX_REVISIONS:
            result = gate.execute(current_state)

            if result.success:
                checkpoints[checkpoint_key] = PipelineCheckpoint(
                    stage=gate.upstream.name,
                    input_state=current_state,
                    validated_output=result.output,
                    revision_count=revision,
                    accumulated_context=prune_context(result.trace, max_entries=50)
                )
                current_state = result.output
                break
            else:
                revision += 1
                # Revise from last validated checkpoint, not raw output
                last_checkpoint = checkpoints.get(checkpoint_key)
                revision_base = last_checkpoint.validated_output if last_checkpoint else current_state
                current_state = gate.upstream.revise(revision_base, result.rejection_reason)

        if revision == MAX_REVISIONS:
            raise PipelineExhaustedError(
                f"Stage {gate.upstream.name} exceeded {MAX_REVISIONS} revisions. "
                f"Last checkpoint: {checkpoints.get(checkpoint_key)}"
            )

    return current_state
```

The key insight: revision always bases on the last *validated* output, not the last failed attempt. This prevents revision loops from compounding on bad intermediate states.

### 4. Failure Budget Governance

Pipeline reliability is not about eliminating all failures — it is about bounding the blast radius. A failure budget governs how many failures a pipeline stage tolerates before the pipeline itself halts:

```python
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timedelta

@dataclass
class StageBudget:
    name: str
    window: timedelta = timedelta(hours=1)
    max_failures: int = 3
    recent_failures: deque = field(default_factory=lambda: deque(maxlen=100))

    def record(self, success: bool):
        if not success:
            self.recent_failures.append(datetime.utcnow())

    def is_healthy(self) -> bool:
        cutoff = datetime.utcnow() - self.window
        recent = sum(1 for t in self.recent_failures if t > cutoff)
        return recent < self.max_failures

    def failure_rate(self) -> float:
        if not self.recent_failures:
            return 0.0
        cutoff = datetime.utcnow() - self.window
        recent = [t for t in self.recent_failures if t > cutoff]
        return len(recent) / self.window.total_seconds() * 3600  # failures per hour
```

Each pipeline stage has its own budget. When a stage's failure rate exceeds its budget, the pipeline pauses and surfaces a diagnostic report — not a crash, not a retry loop, a structured halt with enough context to triage.

## Tradeoffs

- **Validation adds latency.** Every gate adds a round-trip. In low-latency pipelines, this is painful. The mitigation: make validation async where possible, or make it a background check that flags failures rather than blocking progress. Accept that you are trading raw throughput for reliability.
- **Validation models can be wrong too.** A validator that rejects correct outputs (false positive) or passes incorrect ones (false negative) undermines the reliability you're building. Tune validators on your specific domain outputs, not generic heuristics.
- **Revisions are not free.** Each revision pass through an LLM costs tokens. Budget for 2-3x the cost of a single-pass pipeline when designing the economics.
- **Gates create coupling.** A gate that understands both the upstream and downstream schema creates a dependency between them. Treat the gate interface as an API contract — stable and versioned.

## Receipt

> Receipt pending — 2026-07-30. Pattern derived from: AgentMarketCap (Apr 2026) on 12-18% production tool-call failure rates and compounding arithmetic; Brandon Lincoln Hendricks (BLH Research, 2026) on circuit breakers for AI agent reliability and multi-agent communication patterns; Lyceum Technology Magazine (Jun 2026) on agentic cost multiplier and inference optimization; github.com/hailports/self-healing-agent reference loop for autonomous retry, checkpoint/resume, and budget governor patterns; CSA AI Safety Initiative (Jul 2026) on MCP governance and tool poisoning defenses. Key formula: `(1 - p_failure)ⁿ = pipeline success rate` — at 15% per-call failure, 4 stages yield 52% pipeline success.

## See also

- [S-767 · The Tool-Call Hallucination Plateau](s767-the-tool-call-hallucination-plateau.md) — the per-call failure rate that makes pipeline compounding inevitable
- [S-1012 · The Agent Failure Recovery Stack](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — recovery mechanisms that run away when gates fail to catch failures early
- [S-1052 · The Cascade Stack](s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — when wrong facts propagate instead of wrong tool calls
- [S-1841 · The Execution Receipt Stack](s1841-the-execution-receipt-stack-when-your-agent-claims-success-and-proves-nothing.md) — proving what actually executed vs. what the agent believed it executed
