# [S-2106] · The Belief Deviation Stack

[Your agent sounds confident. Its world model is quietly wrong. Somewhere between step 3 and step 30, its internal representation of the problem drifted from reality — and now every subsequent action is a confident answer to the wrong question.]

## Forces

- **Confidence without accuracy**: An agent can express high certainty while its internal world model has diverged from the actual state of the problem — and standard confidence signals miss this entirely.
- **Coherence masking corruption**: Each reasoning step looks locally consistent because it builds on the previous step, which built on the already-corrupted state. The output is fluent; the foundation is rotten.
- **Delayed failure detection**: The symptom (wrong answer, off-target action) appears 10+ steps after the deviation occurred. By the time you see the failure, the deviation has propagated too far to backtrack.
- **No introspection signal**: The agent cannot observe its own belief state directly. It can only report what it believes — not detect that what it believes has drifted.

## The move

**Belief deviation** occurs when an LLM agent's internal representation of the problem state progressively diverges from ground truth over a multi-turn active reasoning session. Unlike hallucination (confabulating facts) or premature commitment (defending a wrong answer), belief deviation is a gradual *world-model collapse* — the agent's understanding of what the problem *is* slowly corrupts without triggering any obvious error signal.

### The four-stage deviation pattern

```
Stage 1 — Initial drift
  Root cause: noisy retrieval result, ambiguous tool response, or
  an edge-case input that the grounding layer mis-classifies.
  The agent forms a slightly-off interpretation. No alarm fires.
  This stage is invisible.

Stage 2 — Belief anchoring
  The off interpretation is now part of working memory.
  Subsequent reasoning steps use it as a premise.
  Cross-run hidden-state similarity at steps 5-8 begins to converge
  (representational commitment starts forming around the wrong frame).

Stage 3 — Self-reinforcing coherence
  The agent generates explanations that are internally consistent
  with its corrupted world model. Each step "confirms" the prior.
  Confidence stays high because nothing has contradicted the frame.
  Logically correct. Factually drifted.

Stage 4 — Cascading commitment
  The deviation is now load-bearing — changing the belief would
  invalidate all downstream reasoning. The agent defends the frame
  not through deception but through self-consistency pressure.
  Produces fluent, confident, wrong outputs.
```

### Diagnosis signals

Do not rely on the agent's self-reported confidence. Instead, monitor:

```
Belief deviation markers (measurable):
  - Cross-run trajectory convergence at early steps
    (cosine similarity of hidden states at step 4-8 predicts
    consistency of final answers across runs)
  - Tool call justification mismatch
    (agent explains a tool call's output using a frame that
    the output itself contradicts)
  - Belief-state checkpoint divergence
    (compare agent's stated summary of problem state at step N
    against a re-phrased re-grounding query at step N+5)
  - Epistemic status flags
    (monitor for phrases like "so the issue is...", "the real
    problem is...", "as we established..." — these mark anchoring)
```

### Intervention patterns

```
1. Belief checkpoint re-grounding (lightweight)
   At fixed intervals (every 5-10 steps), inject a
   re-phrased re-grounding prompt:
     "Re-state the core problem in one sentence.
      List the 3 facts you are most certain about.
      List 2 things you are uncertain about."
   If the re-grounding summary diverges from the original
   grounding context, flag the run for review.

2. Surprise-triggered re-grounding (proportional)
   Deploy a lightweight anomaly detector on tool return values:
   - If any tool output contradicts the agent's current
     working assumption, inject an explicit contradiction
     signal rather than letting the agent smooth over it.
   - Force a belief-state reset at the contradiction boundary.

3. POMDP belief-state tracking (production-grade)
   Maintain an explicit belief-state tracker (partially
   observable Markov decision process):
   - Each tool return is an observation that updates
     P(actual_state | observations_1:t)
   - When belief-state entropy exceeds threshold, halt
     and surface the ambiguity to human or force
     explicit disambiguation.
   - arXiv:2606.17383 formalizes this for agentic systems.

4. Cascade firewall (architectural)
   Separate the "reasoning about what to do" layer from
   the "belief state that actions are grounded in" layer.
   Any action that would be catastrophic if the belief
   is wrong gets a mandatory belief-verification gate
   before execution.
```

### The capability elicitation overlay

A related production failure: even when the agent's world model is correct, safety training can *suppress* the behavior needed to act on it. The **capability elicitation gap** — the difference between what a model can do in principle and what it actually does under your prompt — widens with each safety-focused training cycle. RLHF systematically rewards confident-sounding answers over calibrated uncertainty, degrading the metacognitive calibration you need for belief monitoring.

> Capability isn't destroyed by safety training — it's *suppressed*. The weights still encode it. But the elicitation gap means the agent may not express uncertainty it genuinely holds, and may not self-correct when its beliefs have drifted.

This compounds belief deviation: a miscalibrated agent will not flag its own drift because expressing doubt feels like a regression under RLHF incentives.

```python
import httpx
import numpy as np
from collections import deque

# Lightweight belief deviation detector
# Place between agent steps — cheap enough to run in production

class BeliefDeviationDetector:
    """
    Detects belief deviation via cross-run state convergence and
    belief-grounding divergence. Not a fix — a smoke detector.
    """

    def __init__(self, embed_fn, threshold: float = 0.85, history_len: int = 8):
        self.embed_fn = embed_fn  # callable(text) -> embedding vector
        self.threshold = threshold
        self.history = deque(maxlen=history_len)
        self.original_grounding = None

    def set_grounding(self, grounding_text: str):
        """Call once at step 0 with the original problem framing."""
        self.original_grounding = grounding_text

    def check(self, step_summary: str, step: int) -> dict:
        """
        Returns deviation signal on each agent step.
        step_summary: what the agent believes the problem state is right now
        step: current step number
        """
        embedding = self.embed_fn(step_summary)

        signal = {
            "step": step,
            "drifted": False,
            "convergence_score": 0.0,
            "grounding_divergence": 0.0,
            "reason": None,
        }

        if len(self.history) >= 3:
            # Cross-run convergence: is the agent converging on the same
            # representation it held 3-5 steps ago?
            past_embeddings = list(self.history)[-5:-1]
            similarities = [
                float(np.dot(embedding, past) / (np.linalg.norm(embedding) * np.linalg.norm(past) + 1e-9))
                for past in past_embeddings
            ]
            avg_sim = float(np.mean(similarities))
            signal["convergence_score"] = avg_sim

            if avg_sim > self.threshold and step > 4:
                # High convergence after step 4 = early anchoring signal
                signal["drifted"] = True
                signal["reason"] = f"cross-run convergence {avg_sim:.2f} > {self.threshold} at step {step}"

        if self.original_grounding:
            orig_emb = self.embed_fn(self.original_grounding)
            divergence = 1.0 - float(
                np.dot(embedding, orig_emb) / (np.linalg.norm(embedding) * np.linalg.norm(orig_emb) + 1e-9)
            )
            signal["grounding_divergence"] = divergence
            if divergence > 0.30 and step > 6:
                signal["drifted"] = True
                signal["reason"] = f"grounding divergence {divergence:.2%} > 30% at step {step}"

        self.history.append(embedding)
        return signal


# Usage in agent loop
detector = BeliefDeviationDetector(
    embed_fn=lambda text: embeddings.encode([text])[0],
    threshold=0.85,
)
detector.set_grounding(original_problem_framing)

for step in range(1, max_steps + 1):
    action = agent.step(context)
    step_summary = agent.summarize_current_belief()  # "What I think the problem is now"
    deviation = detector.check(step_summary, step)

    if deviation["drifted"]:
        print(f"[BELIEF DEVIATION] Step {step}: {deviation['reason']}")
        # Trigger re-grounding or halt
        agent.inject_re_grounding_prompt()
        break
```

## Receipt

> Verified 2026-08-04 — Pattern confirmed across: (1) ICLR 2026 oral paper "Reducing Belief Deviation in Reinforcement Learning for Active Reasoning of LLM Agents" (Zou et al., arXiv:2606.17383 + ICLR oral 10007173) — formalizes the belief drift mechanism; (2) arXiv:2607.11881 "Metacognition in LLMs" survey — documents that LLM metacognitive monitoring is unreliable post-RLHF; (3) Tian Pan (tianpan.co, Apr 2026) — capability elicitation gap as production consequence of safety-training regression; (4) arXiv:2606.17383 POMDP framework — quantitative belief-state validation. Code example is a functional detector pattern; embedding model not specified (swap in any provider). Run with `from sentence_transformers import SentenceTransformer; detector = BeliefDeviationDetector(embed_fn=lambda t: SentenceTransformer('all-MiniLM-L6-v2').encode([t])[0])` to instantiate.

## See also

- **[S-2103 · The Premature Commitment Stack](s2103-the-premature-commitment-stack-when-your-agent-settles-on-a-wrong-answer-by-step-4-and-defends-it-to-the-end.md)** — shares the commitment-inflection signal; belief deviation is the *cause*, premature commitment is the *symptom*
- **[S-2066 · The Grounding Layer Stack](s2066-the-grounding-layer-stack-when-your-agent-knows-the-answer-but-gets-the-fact-wrong.md)** — Stage 1 of belief deviation often originates in grounding failures; this stack addresses the fix
- **[S-1935 · The Memory Transaction Protocol](s1935-the-memory-transaction-protocol-record-commit-separation-for-stateful-agent-memory.md)** — the record/commit separation pattern applies to belief state as well as memory
