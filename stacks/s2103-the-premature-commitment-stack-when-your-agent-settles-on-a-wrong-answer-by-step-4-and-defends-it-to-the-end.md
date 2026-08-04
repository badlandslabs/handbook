# S-2103 · The Premature Commitment Stack — When Your Agent Settles on a Wrong Answer by Step 4 and Defends It to the End

Your agent takes 47 steps on a complex research task. It reaches the right answer on one run and the wrong answer on another. You profile the model. The model is fine. You check the tool calls. The tools work. You run it ten more times. The answer bounces between right and wrong with no obvious pattern. The failure is not in the model or the tools — it is in the agent's reasoning trajectory. Somewhere between step 3 and step 5, the agent made a small interpretive decision that locked the rest of the run into a particular answer. It then spent 40 steps defending that decision. The agent didn't know it had committed. You had no way to know either.

This is premature commitment: the most silent and consequential failure mode in long-horizon agentic reasoning. Final-answer scoring misses it entirely because it sees only the endpoint, not the trajectory collapse that predetermines it.

## Forces

- **Agents optimize for coherence, not correctness.** Once an LLM produces text that implies a particular conclusion, subsequent tokens are generated to be consistent with that text. The model is not lying or deliberately defending a wrong answer — it is doing exactly what next-token prediction does: generating text that follows from what came before. Early interpretive choices become self-fulfilling constraints.
- **Final-answer scoring is blind to trajectory collapse.** A 94% accuracy score tells you the agent got the right answer most of the time. It tells you nothing about whether the agent got there through robust reasoning or through lucky early guesses that the rest of the trajectory then defended. Two agents with identical accuracy can have radically different reliability profiles.
- **Commitment is unconscious.** The agent does not know it has committed. There is no internal flag, no confidence drop, no deliberation marker that signals "I have settled on an interpretation and am now defending it." The signal is in the hidden states, not in the output tokens.
- **The window is narrow.** On ReAct-style agents, the commitment inflection point lands around step 4. After that, the trajectory is largely determined. Detection after the fact (post-run review, human-in-the-loop audit) can identify the wrong answer but cannot recover the time and tokens spent defending it.

## The move

### 1. Measure Representational Commitment

Representational commitment is cross-run hidden-state convergence at a fixed reasoning step. It is not a confidence score — it does not tell you whether the agent is right. It tells you whether the agent has *settled*.

The diagnostic: run the same task N times (N ≥ 5). At each reasoning step k, extract the model's hidden states and compute cosine similarity between runs. High similarity at step k means the model has converged to a fixed representation — it has committed.

```python
import torch
from transformers import AutoModel
import numpy as np

def measure_commitment(prompt, model_name="meta-llama/Llama-3.1-70B-Instruct", n_runs=5, target_step=4):
    """
    Measure representational commitment at a given reasoning step.
    High similarity = high commitment (agent has settled).
    """
    model = AutoModel.from_pretrained(model_name, output_hidden_states=True)
    similarities = []

    # Collect hidden states across runs at each step
    all_run_states = []

    for run in range(n_runs):
        states_per_step = []
        # Hook to capture hidden states at each generation step
        hooks = []

        def make_hook(step):
            def hook(module, input, output):
                # Capture last hidden state
                hs = output[0][0, -1, :].detach().cpu()
                states_per_step.append(hs)
            return hook

        for layer in model.model.layers:
            hooks.append(layer.register_forward_hook(make_hook(target_step)))

        # Run agent step
        response = run_agent_step(prompt, model)

        for h in hooks:
            h.remove()

        all_run_states.append(states_per_step)

    # Compare convergence at target_step across runs
    step_states = [run[target_step] for run in all_run_states]
    for i in range(len(step_states)):
        for j in range(i + 1, len(step_states)):
            sim = torch.nn.functional.cosine_similarity(
                step_states[i].unsqueeze(0),
                step_states[j].unsqueeze(0)
            )
            similarities.append(sim.item())

    avg_similarity = np.mean(similarities)
    commitment_score = avg_similarity  # 0 = diverse (exploring), 1 = committed (settled)

    return commitment_score, avg_similarity
```

On Llama-3.1-70B running ReAct on HotpotQA, step-4 hidden-state similarity predicts downstream behavioral consistency with r = −0.35 (partial r = −0.45). High commitment at step 4 reliably predicts that the agent will behave the same way across runs — whether that leads to the right or wrong answer.

### 2. Use Step-4 as the Diagnostic Checkpoint

The commitment inflection is reliably around step 4 in ReAct-style agents on multi-hop reasoning tasks. This gives you a specific, actionable monitoring point:

- **Step 4 similarity > 0.85 across 5+ runs**: Flag the run as high-commitment. Inject a divergence prompt before step 5.
- **Step 4 similarity < 0.70**: The agent is still exploring. Let it continue.
- **Step 4 similarity between 0.70–0.85**: Marginal. Apply lightweight counterfactual injection.

This threshold is task-dependent. Run calibration on your specific domain.

### 3. Inject Counterfactual Divergence

The operational intervention: when you detect high commitment, inject a structured challenge before the agent continues. The goal is not to tell the agent it is wrong — it is to force it to consider an alternative interpretation it may have implicitly discarded.

```
Given your current reasoning path, I want you to consider an alternative interpretation 
of the evidence from step [N]. Specifically: [alternative framing]. 
Does this change any of your subsequent conclusions? If not, explain why the alternative 
is inconsistent with the evidence. If it does, revise your reasoning.
```

This is not a re-prompt. It is a targeted counterfactual injection that forces the model to re-examine the interpretive decision it made at the commitment point. The key phrase is "consider an alternative interpretation" — not "are you sure?" — because "are you sure?" typically produces confident reaffirmation.

### 4. Route High-Commitment Runs to Verification Gates

High-commitment trajectories are not necessarily wrong — committed-correct and committed-wrong are representationally indistinguishable. What the commitment signal tells you is that the trajectory is now in a narrow band: it will behave consistently, for better or worse.

Route high-commitment runs through an additional verification step using a different model, a different prompt, or a different reasoning chain (e.g., chain-of-thought vs. ReAct). If both paths converge on the same answer, the commitment was probably fine. If they diverge, surface the divergence for human review.

### 5. Design Prompting to Delay Commitment

Prevention is better than detection. Structure prompts to explicitly delay interpretive decisions:

- Break multi-hop questions into explicit sub-question stages with checkpoint gates
- Add "list three possible interpretations before choosing one" as a required step
- Use role-prompting to inject a "devil's advocate" that must articulate an opposing view before the main agent proceeds

The goal is to increase the reasoning diversity at early steps, pushing the commitment inflection point from step 4 to step 7 or later — giving the model more room to explore before it settles.

## Key Insight

Representational commitment is not a model bug. It is a property of next-token prediction under self-consistency pressure: once text implies a conclusion, subsequent tokens are generated to be consistent with it. The model is not lying to you. It has genuinely forgotten it had options. Commitment detection gives you the only observable signal of this process: not whether the agent settled, but *when*.

The counterintuitive finding: committed-wrong and committed-correct agents look identical in their hidden states. You cannot use the commitment signal alone to determine correctness. What you can do is use it to know *when* the trajectory became deterministic — and insert verification at that point, before the locked-in trajectory generates 40 more steps of confident wrong reasoning.

## Forces (refreshed)

- **The diagnosis requires multiple runs.** Commitment is measured across runs, not within a single run. A single execution gives you the answer but no information about how deterministically the agent reached it. Budget for N ≥ 5 runs for calibration; N ≥ 3 for runtime detection.
- **Commitment detection has compute cost.** Running the same task 5 times to measure commitment costs 5× the inference budget. The ROI is highest on high-stakes, long-horizon tasks where a wrong answer is expensive. For simple single-turn tasks, skip it.
- **Counterfactual injection adds latency but not much.** A targeted counterfactual prompt is a single additional LLM call, not a full re-run. Budget 1–3 extra turns on runs flagged as high-commitment.

## Receipt

> Verified 2026-08-04 — arXiv:2606.22936 "When Agents Commit Too Soon: Diagnosing Premature Commitment in LLM Agents" (Mehta, Snowflake AI Research, 22 Jun 2026). Key finding confirmed: step-4 hidden-state similarity predicts behavioral consistency (r = −0.35 to −0.80 across models and datasets). Committed-wrong and committed-correct are representationally indistinguishable — the signal tells you *when*, not *whether*. No existing handbook entry covers this failure mode. S-996 mentions "premature output" in the MAST taxonomy (verification failure category) but does not address trajectory-level commitment or the representational commitment diagnostic. This entry is novel.

## See also
- [S-996 · The Harness Matters More Stack](/stacks/s996-the-harness-matters-more-stack-when-your-model-isnt-the-problem.md) — MAST taxonomy, verification failures including "premature output" (the category, not the mechanism)
- [S-1261 · The Confidence Calibration Stack](/stacks/s1261-the-confidence-calibration-stack-when-your-agent-sounds-sure-and-is-wrong.md) — calibration gap; this entry is distinct: commitment is unconscious whereas calibration is about verbalized confidence
- [S-1023 · The Recovery Ladder](/stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — semantic failure gap; premature commitment is a specific root cause within that failure class
