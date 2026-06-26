# R-07 · Post-Training and RLVR

How 2026 reasoning models are actually made. Pretraining gives a model raw knowledge; **post-training** is where most of its *usable* capability now comes from — and the recipe changed. The reasoning models in [R-02](r02-reasoning-models.md) are the output of this pipeline.

## Forces
- RLHF's reward came from a *learned* model of human preference — expensive to label, and the agent can game the proxy
- Reasoning has a property preference-tuning doesn't exploit: for math and code, correctness is *checkable* by a program, not a vote
- A verifiable reward is cheap, deterministic, and unfakeable — but it only exists where ground truth exists
- Most real-world goals (helpfulness, style, judgment) have no binary checker — that's the open frontier

## The move
- **The modern stack is modular, not one big RL run:**
  1. **SFT** — supervised fine-tuning on demonstrations for instruction-following and format.
  2. **Preference optimization** — DPO / SimPO / KTO to align tone and safety from preference pairs (no separate reward model needed).
  3. **RLVR** — RL from *verifiable* rewards: the reward is a deterministic checker (math answer correct, unit tests pass), not a human or learned model.
- **RLVR is the reasoning lever.** DeepSeek-R1 showed RL against verifiable rewards *alone* can elicit emergent step-by-step reasoning (even from a base model, in the R1-Zero variant).
- **GRPO is the workhorse algorithm.** Group Relative Policy Optimization drops PPO's separate critic/value model: sample a *group* of rollouts per prompt, score each with the verifier, and use the group's mean as the baseline. Cheaper to run than PPO. (Variants: DAPO, etc.)
- **The bottleneck is verifiability.** RLVR shines on math/code where a checker exists; extending it to fuzzy tasks is the active frontier — rubric-as-reward (an LLM judge grades against a rubric, see [F-12](../forward-deployed/f12-llm-as-a-judge.md)) and self-play / self-consistency pseudo-labels ([S-24](../stacks/s24-self-consistency.md)) when no ground truth exists.
- **What this means for you:** you rarely run RLVR yourself, but it explains *why* reasoning models are strong on verifiable domains and shakier off them — and why "give the model a verifier" (tests, schemas) is the single highest-leverage thing you can hand an agent.

## Receipt
> Verified 2026-06-25 — I can't run RL weight updates locally, but the **verifiable reward signal** RLVR optimizes is runnable. 10 rollouts at temperature 1.0 against llama3.2 (Ollama, localhost:11435) on a checkable problem — "distinct arrangements of MISSISSIPPI" (correct = 11!/(4!·4!·2!) = **34650**) — each scored by a deterministic verifier (reward=1 iff answer is 34650).

```
8/10 rollouts earned reward=1 (produced 34650)
2/10 earned reward=0 (no verifiable-correct answer)
single-sample accuracy: 80%   best-of-10: a verified-correct rollout exists
```

The point: a one-line program separated good rollouts from bad ones with **zero human labels** — that is the exact signal RLVR turns into a gradient (GRPO scores a group of rollouts this way and pushes the policy toward the rewarded ones). What I ran is the *reward*, inference-time; the *training* (the weight update) is what DeepSeek-R1 et al. did at scale and is **not reproduced here**. It also shows the limitation in miniature: 2 rollouts earned nothing, and on a problem the model *never* solved the reward would be all-zero — RLVR can only reinforce reasoning the model can already sometimes reach.

## See also
[R-02](r02-reasoning-models.md) · [R-03](r03-fine-tuning-vs-prompting.md) · [S-24](../stacks/s24-self-consistency.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md) · [R-04](r04-small-language-models.md)

## Go deeper
Keywords: `RLVR` · `RLHF` · `GRPO` · `DAPO` · `DPO` · `post-training` · `DeepSeek-R1 arXiv 2501.12948` · `DeepSeekMath GRPO arXiv 2402.03300` · `Tulu 3 arXiv 2411.15124` · `rubrics as rewards` · `verifiable rewards` · `SFT`
