# S-936 · Agent Trace Distillation — When Inference-Time Optimization Hits a Wall

You tuned the prompts. You added a cache layer. You wired in tool-calling schemas and implemented a circuit breaker. The agent still costs $0.40 per task and takes 4 seconds. You're hitting the ceiling of what inference-time engineering can deliver. Meanwhile, a frontier model — running your agent pipeline end-to-end — produces traces that encode the exact behavioral decisions you want, at 10x the accuracy. The next lever isn't more prompting. It's training.

Agent trace distillation: collect successful trajectories from a teacher agent (usually a frontier model), then fine-tune a smaller student model to replicate those behaviors. The student emerges with learned tool-selection strategies, error-recovery patterns, and workflow decompositions — not just task outputs, but the agentic reasoning that produced them.

## Forces

- **Inference-time engineering has diminishing returns.** After prompt caching, semantic routing, and budget-aware agents, the remaining latency and cost gaps are structural — baked into the model's policy, not the scaffolding around it.
- **Frontier models are the best teachers for specialized tasks.** A frontier model running your specific tool schema and business context generates traces that encode context-appropriate strategies. A generic fine-tune on public data won't replicate them.
- **Naive trajectory imitation doesn't work.** Agents produce chains of reasoning, tool calls, observations, and corrections. Copying token sequences misses the causal structure tying steps together. A wrong tool call at step 3 poisons steps 4–10 — but the student that blindly copies the token sequence of a successful trace will make the same mistake on a near-miss input.
- **The distributional gap kills naive SFT.** The training distribution (successful traces on clean tasks) differs from the production distribution (noisy inputs, edge cases, failed attempts). Without addressing this gap, the student learns to succeed where the teacher succeeded — not where the teacher recovered.
- **Distillation is expensive to iterate.** Unlike prompting, each training run costs compute and takes days. Getting the trajectory curation wrong wastes weeks.

## The Move

### 1. Capture Traces at the Right Granularity

The unit of distillation is the **trajectory**: a full episode from input to outcome, including every tool call, observation, reasoning step, and recovery action. Log these with structured metadata:

```python
# Structured trace capture (pseudocode)
trajectory = {
    "task_id": "contract-review-8834",
    "agent": "gpt-5-teacher",
    "tools_schema_version": "v3.2",
    "steps": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "Review contract for GDPR risk..."},
        {"role": "assistant", "tool_calls": [{"name": "search_docs", "args": {"query": "GDPR data processing clauses"}}]},
        {"role": "tool", "name": "search_docs", "output": "3 results found"},
        {"role": "assistant", "content": "Found 3 relevant clauses. Flagging..."},
        {"tool_calls": [{"name": "flag_clause", "args": {"clause_id": "A.3.2", "risk": "high"}}]},
        # ... full chain through to outcome
    ],
    "outcome": "success",  # or "partial", "failed"
    "verified_by": "ground_truth_annotation",  # critical: don't distill from self-reported success
    "trace_cost_usd": 1.24,
}
```

**The single most common mistake**: distilling from self-reported success. Agents assert completion even when it fails (GPT-5 submits 100% of runs but resolves only 44% on SWE-bench Verified). Only distill from traces where outcome is **ground-truth verified** — tests pass, API calls return confirmed state, human annotators approve.

### 2. Filter for Trajectory Quality

Not all successful traces are good teachers. Quality filters:

| Filter | Why It Matters |
|--------|---------------|
| **Outcome-verified success** | Self-reported success is wrong 45–56% of the time (Advani 2026, tau2-bench + AppWorld). |
| **Minimal steps** | Longer traces accumulate unnecessary reasoning noise. Prefer shortest-successful path. |
| **Diverse tool sequences** | Traces that always use the same tool pattern produce students with narrow tool affinity. |
| **Error-recovery included** | Traces where the agent corrected mid-flight teach recovery strategies. Pure success paths don't. |
| **Input type coverage** | Distill across the full input distribution your student will see — not just common cases. |

### 3. Choose Your Distillation Recipe

Three recipes are production-viable as of mid-2026:

**Recipe A — Supervised Fine-Tuning on Successful Traces (SFT)**
```python
# Convert traces to SFT conversation format
messages = []
for step in trajectory["steps"]:
    if step["role"] == "assistant":
        messages.append({"role": "assistant", "content": step["content"], "tool_calls": step.get("tool_calls")})
    elif step["role"] == "tool":
        messages.append({"role": "tool", "content": step["output"], "tool_call_id": step["tool_call_id"]})

# Fine-tune student with messages
student = auto_trainer.fine_tune(
    base_model="gpt-4o-mini-student",
    training_data=messages,
    recipe="sft",
    epochs=3,
    learning_rate=1e-5,
    # Critical: use the SAME tool schemas the student will encounter in production
    tool_schemas=production_tool_registry,
)
```
Best for: teaching specific tool-selection sequences, domain-specific workflows, output format compliance. Microsoft Foundry's `ToolUseFineTuning` recipe uses this approach and reports 9–19 point accuracy gains with RFT (Reinforcement Fine-Tuning) layering.

**Recipe B — Reinforcement Fine-Tuning on Outcome Signals (RFT)**
```python
# RFT: use outcome signals as reward, not trajectory tokens
from foundry_rft import AgenticRFT

rft = AgenticRFT(
    teacher_model="gpt-5",
    student_base="gpt-4o-mini",
    task_distribution="contract_review_tasks",
    reward_signal="contract_clause_correctness",  # deterministic: does the flagged clause match ground truth?
    tool_schemas=production_tool_registry,
)
rft.train(iterations=500)  # Each iteration: sample tasks → generate traces → score → update
```
RFT teaches *strategies*, not sequences. The model learns that "when you see a data-processing clause, search for prior violations before flagging" — not just the tokens to output. This is where the 9–19 point gains over SFT come from.

**Recipe C — Trace Distillation with Behavioral Decomposition**
```python
# Decompose trajectories into sub-behaviors and distill each separately
from trace_distill import TrajectoryDecomposer

decomposer = TrajectoryDecomposer(trajectories=successful_traces)
behaviors = decomposer.extract(
    behavior_types=["tool_selection", "error_recovery", "planning", "grounding"]
)
# Train separate behavior heads or LoRA adapters per behavior type
for behavior_type, behavior_traces in behaviors.items():
    student.attach_head(behavior_type, behavior_traces, recipe="sft")
```
SWE-RL (Facebook Research, NeurIPS 2025) applies this via reinforcement learning on open software evolution traces. Socratic-SWE (2026) closes the loop by reusing the student's own solving traces as training signal — the student teaches itself where it improved, concentrating on its own weaknesses.

### 4. Validate the Student Before Deployment

Distillation creates a model that has **learned the teacher's distribution**, not the true task distribution. Validate with held-out cases that differ from training tasks:

```python
# Golden set validation — never use training traces
golden_set = load_held_out_eval(
    tasks=200,
    source="production_logs_last_30d",
    exclude_sources=[t["task_id"] for t in training_trajectories]
)

# Run student and compare to teacher on same tasks
results = evaluate_student_vs_teacher(
    student=distilled_student,
    teacher=frontier_model,
    eval_set=golden_set,
    metrics=["task_success_rate", "avg_steps", "cost_per_task", "tool_error_rate"]
)
# Pass threshold: student within 5% of teacher on success rate, at least 5x cheaper
assert results.student_success_rate >= (results.teacher_success_rate * 0.95), "Student regression detected"
assert results.student_cost <= (results.teacher_cost * 0.2), "Cost target not met"
```

### 5. Build a Continuous Distillation Pipeline

Distillation isn't a one-time event — agent behavior drifts as tools change, business logic evolves, and the input distribution shifts. A continuous pipeline:

1. **Collect**: Stream production traces, filter for verified success, tag by task type
2. **Curate**: Run diversity checks (are new traces adding new tool sequences, or just repeating old ones?)
3. **Train**: Re-run fine-tuning weekly or when 500+ new verified traces accumulate
4. **Validate**: Run golden set + adversarial sampling against the previous student version
5. **Deploy**: Canary — route 5% of traffic to the new student, compare success rates, promote if within threshold

## Receipt

> Verified 2026-07-11 — Pattern distilled from: Microsoft Foundry Ignite BRK188 (RFT + SFT recipes, TracesDistillation, 2025); SWE-RL (Facebook Research, NeurIPS 2025, arxiv-based); Socratic-SWE (closed-loop self-evolution via own traces, 2026); Open-SWE-Traces (207K agentic trajectories, arxiv:2606.16038); Zylos Research "Distilling AI Agents" (Apr 2026); Mehta (Snowflake, arxiv:2603.25764, Jun 2026, SWE-bench Verified submit/resolve divergence data); Advani (arxiv:2606.09863, Jun 2026, false success AUROC <0.65); SWE-bench / SWE-bench++ trajectory capture pipelines (Turing Research). Distillation recipes are production-viable and documented by Microsoft Foundry, Facebook Research, and multiple 2026 research groups. Code examples are representative of documented APIs (Foundry, OpenAI fine-tuning, HuggingFace Transformers).

## See also

- [S-362 · Budget-Aware Agents: Cost as First-Class Behavioral Dimension](stacks/s362-budget-aware-agents-cost-as-first-class-behavioral-dimension.md) — inference-time cost control that distillation complements
- [S-643 · The Coordination Layer Is the Product](stacks/s643-the-coordination-layer-is-the-product.md) — multi-agent orchestration where trace distillation often delivers the biggest student gains
- [S-385 · Agent Trajectory Evaluation: Process vs. Outcome Scoring](stacks/s385-agent-trajectory-evaluation-process-vs-outcome-scoring.md) — trajectory evaluation methodology; distillation quality depends on trajectory quality
- [S-430 · Agent Benchmark Gaming: Scores Without Proof](stacks/s430-agent-benchmark-gaming-scores-without-proof.md) — why self-reported success is unreliable for distillation signal
- [S-569 · The Eval Illusion: When Passing Evals Don't Prevent Production Failures](stacks/s569-the-eval-illusion-when-passing-evals-dont-prevent-production-failures.md) — the eval-distribution gap that continuous distillation pipelines must address
