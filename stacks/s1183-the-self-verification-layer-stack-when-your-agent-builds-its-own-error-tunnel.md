# S-1183 · The Self-Verification Layer Stack — When Your Agent Builds Its Own Error Tunnel

Your agent completes a 12-step workflow and returns a confident, coherent answer. You ship it. Three days later the downstream system fails because the agent's step 3 output was subtly wrong — not hallucinated, just imprecise enough to misdirect every subsequent step. The agent never flagged it. Nobody checked. By step 12 the error had compounded into a false conclusion that looked correct because the entire argument chain was internally consistent. This is not a hallucination problem. It's an error accumulation problem, and it is the dominant failure mode in multi-step agentic systems.

## Forces

- **Multi-step accuracy degrades exponentially, not linearly.** UC Berkeley, Carnegie Mellon, and Microsoft Research (late 2025) document error propagation across agentic workflow steps: a 5% per-step error rate yields approximately 60% final accuracy on a 10-step task. Not 95%. The agent isn't failing at the end — it's failing at the beginning and the failure propagates silently.
- **Agents trust their own intermediate outputs.** When step N produces a result, step N+1 treats it as ground truth. This is correct behavior in deterministic systems. In LLM-based systems, every intermediate output carries a non-zero probability of being wrong, and that probability compounds multiplicatively through the pipeline.
- **Traditional eval catches final output quality, not step-level corruption.** Your test suite can verify that the final answer is correct. It cannot tell you that steps 3–7 were each slightly wrong but masked by the final answer's accidental correctness. This is the "confidently wrong" failure mode that post-hoc evaluation completely misses.
- **Human-in-the-loop verification doesn't scale.** Reviewing every intermediate step defeats the purpose of automation. The solution must be architectural — a verification layer that runs automatically at the right grain size.
- **Naive retry amplifies cost without fixing the problem.** Re-running step 8 if step 3 was wrong doesn't help unless step 3 is also re-run. Without propagation-aware retry, you're just re-executing a corrupted pipeline.

## The move

### 1. Insert verification gates at semantic boundaries

Not every step needs verification — only steps whose output becomes a premise for subsequent steps. These are the *semantic boundaries*: points where the agent's output functions as input to another decision. Identify them explicitly:

- Tool call outputs that inform the next tool call's arguments
- Classification or extraction outputs that gate downstream logic branches
- Synthesis steps where multiple intermediate results converge

At each boundary, add a verification prompt: *"Before proceeding, confirm this output is correct. Check for: (1) tool call artifacts left in the text, (2) missing fields, (3) subtle precision loss, (4) instructions followed. Return PASS or FAIL with specific issue."* This is a separate LLM call — a lightweight, fast model is often sufficient.

### 2. Use step-scoped verification, not end-to-end

End-to-end verification (check the final answer) misses step-level corruption. Step-scoped verification (check each intermediate output) catches errors where they originate. The pattern:

```
Step 1: Execute → Output A
Step 2: Verify A → PASS/FAIL
        if FAIL: retry Step 1 with error context
Step 3: Execute using A → Output B
Step 4: Verify B → PASS/FAIL
        if FAIL: retry Step 3 with error context
```

This is analogous to ECC memory: detect and correct at the boundary, not at the end of the pipeline.

### 3. Propagate retry scope, not just step scope

When a verification fails, re-execute the originating step AND all downstream steps that consumed its output. Naive single-step retry without propagation just re-runs a downstream step against the same corrupted premise. Track dependency provenance explicitly — maintain a lightweight DAG of which step outputs fed into which subsequent steps.

### 4. Use a different model for verification than execution

The same model that made the error is poorly positioned to catch it — confirmation bias is well-documented in LLM evaluation. Use a separate verifier model, preferably one with a different training signal or architecture. Even a smaller model with different failure modes provides meaningful orthogonal coverage. AgentMarketCap (April 2026) reports 18–24% accuracy gains from structured self-verification patterns using model-disagreement as the signal.

### 5. Implement verification as a structured interrupt, not a bypass

Don't make verification optional or confidence-threshold-gated in production. Make it a mandatory gate: the pipeline cannot proceed past a boundary until the verifier returns PASS. The cost of a second LLM call per boundary is almost always less than the cost of a downstream error that surfaces hours later in a production system.

### 6. Log the verification decision, not just the result

Store: which step was verified, what the verifier was told to check, what it returned (PASS/FAIL + reasoning), what action was taken. This creates a trace that lets you audit whether your verification gates are calibrated correctly and identify which failure types consistently escape detection.

## Tradeoffs

- **Latency cost:** Every verification gate adds a synchronous LLM call. Budget 10–30% additional latency per verified boundary. Use async verification for non-critical paths, or tier verification by risk (high-risk outputs like financial transactions, data deletions, or external API calls warrant verification; routine internal lookups may not).
- **False-positive retry storms:** If your verifier has high false-positive rate, you'll trigger unnecessary retries that compound cost without improving quality. Calibrate your verifier's threshold against your domain's actual error distribution.
- **Verifier reliability:** The verifier itself can fail or hallucinate. The pattern doesn't eliminate verification — it moves it one layer up. For critical paths, retain human review as the final layer.
- **Not all steps are verifiable.** Some steps produce outputs that are inherently hard to verify automatically (creative writing, nuanced judgment calls). Apply verification selectively to steps with verifiable properties: schema conformance, factual grounding, arithmetic correctness, tool call validity.

## Distinction from related patterns

- **vs. S-1029 (Evaluator Stack):** That entry covers how to measure agent quality at the evaluation level (evals, benchmarks, LLM-as-judge). This entry covers architectural placement of verification *inside* the workflow, at step grain size, to prevent error propagation.
- **vs. S-1138 (Failure Taxon Stack):** That entry classifies failure types after they occur. This entry is a proactive architectural pattern that prevents a specific failure type (error accumulation) from occurring.
- **vs. S-1151 (Behavioral Telemetry Stack):** That entry monitors agent behavior in production to catch silent failures. This entry adds an active verification gate inside the pipeline, not just post-hoc monitoring.
- **vs. S-1160 (Agent-Native CI/CD):** That entry tests agent behavior changes before deployment. This entry operates at runtime, inside an active workflow.
